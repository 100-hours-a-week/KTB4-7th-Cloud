"""Read-only ECS metadata audit. Does not resolve Secrets, deploy, or enable Outbox."""
import argparse
import json
from pathlib import Path
from deploy_backend import Aws, DeploymentError, get_service, target, validate_service


def public_environment(td):
    container = td['containerDefinitions'][0]
    entries = container.get('environment', [])
    env = {x['name']: x['value'] for x in entries}
    secrets = {x['name']: x['valueFrom'] for x in container.get('secrets', [])}
    keys = ('SPRING_PROFILES_ACTIVE', 'SALES_OUTBOX_ENABLED', 'SALES_OUTBOX_DISPATCH_ENABLED',
            'SALES_STORAGE_TYPE', 'SALES_STORAGE_S3_BUCKET', 'DB_URL')
    if any(name in env and name in secrets for name in keys):
        raise DeploymentError('Runtime settings overlap environment and Secrets')
    if len(entries) != len(env):
        raise DeploymentError('Duplicate runtime environment names')
    if any(name in secrets for name in keys[:4]):
        raise DeploymentError('Role controls are unresolved Secrets; audit cannot infer their values')
    return env, secrets


def reference(env, secrets, name):
    if env.get(name, '').strip():
        return ('environment', env[name])
    if secrets.get(name):
        return ('secret-reference', secrets[name])
    raise DeploymentError('Required shared runtime reference is missing')


def audit_definitions(web, batch):
    roles = {}
    for kind, td in [('web', web), ('batch', batch)]:
        env, secrets = public_environment(td)
        if any(name.startswith('APP_SALES_OUTBOX_') for name in env.keys() | secrets.keys()):
            raise DeploymentError('Outbox alias override prevents a reliable metadata audit')
        profiles = {p.strip() for p in env.get('SPRING_PROFILES_ACTIVE', '').split(',') if p.strip()}
        if profiles & {'sales-outbox-web', 'sales-outbox-batch'} != {'sales-outbox-' + kind}:
            raise DeploymentError('Runtime Outbox profile does not match the ECS service role')
        if env.get('SALES_OUTBOX_DISPATCH_ENABLED') != ('false' if kind == 'web' else 'true'):
            raise DeploymentError('Runtime Dispatcher setting does not match web/batch separation')
        enabled = env.get('SALES_OUTBOX_ENABLED', 'false')
        if enabled not in ('true', 'false'):
            raise DeploymentError('Outbox activation value must be true or false')
        roles[kind] = (enabled, env, secrets)
    if roles['web'][0] != roles['batch'][0]:
        raise DeploymentError('Web and batch Outbox activation settings differ')
    if roles['web'][0] == 'false':
        return {'status': 'DISABLED', 'roles_match': True, 'outbox_enabled': False,
                'db_route_verified': False, 's3_access_verified': False}
    for _, env, _ in roles.values():
        if env.get('SALES_STORAGE_TYPE') != 's3':
            raise DeploymentError('Enabled ECS Outbox requires shared S3 storage')
    for name in ('DB_URL', 'SALES_STORAGE_S3_BUCKET'):
        if reference(*roles['web'][1:], name) != reference(*roles['batch'][1:], name):
            raise DeploymentError('Web and batch shared DB/S3 references differ; inspect without exposing values')
    for name, default in [('SALES_STORAGE_S3_REGION', 'ap-northeast-2'),
                          ('SALES_STORAGE_S3_ENDPOINT', ''), ('SALES_STORAGE_S3_PATH_STYLE_ACCESS', 'false')]:
        values = [('secret-reference', secrets[name]) if name in secrets
                  else ('environment', env.get(name, default)) for _, env, secrets in roles.values()]
        if values[0] != values[1]:
            raise DeploymentError('Web and batch S3 region/endpoint settings differ')
    return {'status': 'METADATA_PASS', 'roles_match': True, 'outbox_enabled': True,
            'shared_references_match': True, 'db_route_verified': False, 's3_access_verified': False}


def audit_live(aws):
    definitions = {}
    for kind in ('web', 'batch'):
        service = get_service(aws, kind)
        validate_service(service, kind)
        if service.get('runningCount') != target(kind)['desired'] or service.get('pendingCount') != 0:
            raise DeploymentError('ECS tasks are not at their stable web2/batch1 counts')
        if len(service.get('deployments', [])) != 1 or service['deployments'][0].get('rolloutState') != 'COMPLETED':
            raise DeploymentError('Finish the current ECS deployment before runtime audit')
        definitions[kind] = aws.call('ecs', 'describe-task-definition',
                                    taskDefinition=service['taskDefinition'])['taskDefinition']
    return audit_definitions(definitions['web'], definitions['batch'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', default='outbox-runtime-audit.json')
    args = parser.parse_args()
    try:
        report = audit_live(Aws())
    except DeploymentError as error:
        report = {'status': 'FAIL', 'error': str(error)}
    Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] in ('METADATA_PASS', 'DISABLED') else 1


if __name__ == '__main__':
    raise SystemExit(main())
