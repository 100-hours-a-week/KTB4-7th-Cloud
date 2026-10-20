"""Deploy or restore Memme Backend ECS web and batch without changing network or Secrets."""
import argparse
import copy
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ACCOUNT = '613538400341'
REGION = 'ap-northeast-2'
CLUSTER = 'memme-v2'
# web: ALB behind, rolling one task at a time with surge (100/150) and circuit-breaker rollback.
# batch: single scheduler owner, never overlapping (0/100), no ALB or service discovery.
TARGETS = {
    'web': {'service': 'memme-backend-v2', 'desired': 2, 'min': 100, 'max': 150, 'public': True},
    'batch': {'service': 'memme-backend-batch-v2', 'desired': 1, 'min': 0, 'max': 100, 'public': False},
}
IMAGE_PREFIX = f'{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/memme/backend@'
CRONS = ('LOGIN_RATE_LIMIT_CLEANUP_CRON', 'PASSWORD_RESET_RATE_LIMIT_CLEANUP_CRON',
         'SOLUTION_DAILY_CRON', 'SOLUTION_READY_NOTIFICATION_CRON', 'SALES_UPLOAD_REMINDER_CRON')
REGISTER_FIELDS = ('family', 'taskRoleArn', 'executionRoleArn', 'networkMode',
                   'containerDefinitions', 'volumes', 'placementConstraints',
                   'requiresCompatibilities', 'cpu', 'memory', 'runtimePlatform',
                   'ephemeralStorage', 'proxyConfiguration', 'pidMode', 'ipcMode')


class DeploymentError(RuntimeError):
    def __init__(self, message, report=None):
        super().__init__(message)
        self.report = report or {}


class Aws:
    def call(self, namespace, operation, **parameters):
        command = ['aws', namespace, operation, '--region', REGION, '--output', 'json', '--no-cli-pager']
        if parameters:
            command += ['--cli-input-json', json.dumps(parameters)]
        try:
            result = subprocess.run(command, text=True, capture_output=True, timeout=90)
        except subprocess.TimeoutExpired:
            raise DeploymentError(f'{namespace}:{operation} timed out; inspect AWS state before retrying') from None
        except OSError:
            raise DeploymentError(f'{namespace}:{operation} transport failed') from None
        if result.returncode:
            # Never echo command payloads or raw AWS responses into CI logs.
            code = re.search(r'\((\w+)\)', result.stderr)
            raise DeploymentError(f'{namespace}:{operation} failed ({code.group(1) if code else "AWS_ERROR"})')
        try:
            return json.loads(result.stdout)
        except ValueError:
            raise DeploymentError(f'{namespace}:{operation} returned invalid JSON') from None


def target(kind):
    if kind not in TARGETS:
        raise DeploymentError('Unknown Backend ECS target')
    family = TARGETS[kind]['service']
    return {**TARGETS[kind], 'kind': kind, 'family': family,
            'td_prefix': f'arn:aws:ecs:{REGION}:{ACCOUNT}:task-definition/{family}:',
            'service_arn': f'arn:aws:ecs:{REGION}:{ACCOUNT}:service/{CLUSTER}/{family}'}


def definition_arn(value, kind='web'):
    t = target(kind)
    if value and re.fullmatch(re.escape(t['family']) + r':[1-9]\d*', value):
        value = t['td_prefix'] + value.split(':')[1]
    if not value or not re.fullmatch(re.escape(t['td_prefix']) + r'[1-9]\d*', value):
        raise DeploymentError(f"Specify a recorded {t['family']} revision")
    return value


def validate_definition(td, kind='web'):
    if (td.get('family') != target(kind)['family'] or td.get('networkMode') != 'awsvpc'
            or td.get('requiresCompatibilities') != ['FARGATE']):
        raise DeploymentError('Unexpected Backend task family or execution mode')
    for field, role in [('taskRoleArn', 'MemmeBackendV2TaskRole'),
                        ('executionRoleArn', 'MemmeBackendV2ExecutionRole')]:
        if td.get(field) != f'arn:aws:iam::{ACCOUNT}:role/{role}':
            raise DeploymentError('Unexpected task IAM role')
    containers = td.get('containerDefinitions', [])
    if len(containers) != 1 or (kind == 'web' and containers[0].get('name') != 'backend'):
        raise DeploymentError('Unexpected Backend container configuration')
    container = containers[0]
    if not re.fullmatch(re.escape(IMAGE_PREFIX) + r'sha256:[a-f0-9]{64}', container.get('image', '')):
        raise DeploymentError('Backend image must use an immutable digest in the approved repository')
    if container.get('privileged') or container.get('command') or container.get('entryPoint'):
        raise DeploymentError('Unreviewed container execution override')
    if kind == 'batch':
        # The batch task owns the schedulers; web-only session and scheduler guards do not apply.
        return
    env = {x['name']: x['value'] for x in container.get('environment', [])}
    if any(env.get(n) != '-' for n in CRONS) or env.get('QA_ACCOUNT_ENABLED') != 'false':
        raise DeploymentError('ECS web tasks must keep schedulers and QA seeding disabled')
    if env.get('SERVER_SERVLET_SESSION_COOKIE_SECURE') != 'true' or not container.get('healthCheck'):
        raise DeploymentError('Secure session cookies and container health check are required')


def prepare_definition(td, digest, source_sha, kind='web'):
    validate_definition(td, kind)
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest or '') or not re.fullmatch(r'[a-f0-9]{40}', source_sha or ''):
        raise DeploymentError('Invalid immutable image identity')
    result = {k: copy.deepcopy(td[k]) for k in REGISTER_FIELDS if k in td}
    result['containerDefinitions'][0]['image'] = IMAGE_PREFIX + digest
    result['tags'] = [{'key': 'Project', 'value': 'memme'}, {'key': 'Service', 'value': target(kind)['family']},
                      {'key': 'SourceSha', 'value': source_sha}]
    return result


def validate_service(service, kind='web'):
    t = target(kind)
    config = service.get('deploymentConfiguration', {})
    breaker = config.get('deploymentCircuitBreaker', {})
    if (service.get('serviceArn') != t['service_arn'] or service.get('desiredCount') != t['desired']
            or config.get('minimumHealthyPercent') != t['min'] or config.get('maximumPercent') != t['max']):
        raise DeploymentError(f"Service must retain desired{t['desired']} and rolling{t['min']}/{t['max']}")
    if kind == 'batch':
        # A second batch task would run every scheduler twice.
        if service.get('loadBalancers') or service.get('serviceRegistries'):
            raise DeploymentError('Batch service must stay outside ALB and service discovery')
        return
    if not breaker.get('enable') or not breaker.get('rollback'):
        raise DeploymentError('Service must retain circuit-breaker rollback')
    if len(service.get('loadBalancers', [])) != 1 or len(service.get('serviceRegistries', [])) != 1:
        raise DeploymentError('Expected ALB and private service discovery are required')


def get_service(aws, kind='web'):
    response = aws.call('ecs', 'describe-services', cluster=CLUSTER, services=[target(kind)['service']])
    if response.get('failures') or len(response.get('services', [])) != 1:
        raise DeploymentError('Backend ECS service was not found')
    return response['services'][0]


def wait_healthy(aws, target_arn, digest, before, deadline, sleep, clock, kind='web', require_health=True):
    t = target(kind)
    count = t['desired']
    health = ('HEALTHY',) if require_health else ('HEALTHY', 'UNKNOWN')
    started = clock()
    while clock() < deadline:
        service = get_service(aws, kind)
        validate_service(service, kind)
        if (service['loadBalancers'] != before['loadBalancers']
                or service['serviceRegistries'] != before['serviceRegistries']):
            raise DeploymentError('ALB or discovery changed during deployment')
        primary = next((d for d in service.get('deployments', []) if d['status'] == 'PRIMARY'), {})
        if any(d.get('taskDefinition') == target_arn and d.get('rolloutState') == 'FAILED'
               for d in service.get('deployments', [])):
            raise DeploymentError('Candidate deployment failed; inspect circuit-breaker recovery')
        if service['taskDefinition'] != target_arn and clock() - started >= 30:
            raise DeploymentError('Requested revision is no longer the active deployment')
        ready = (service['taskDefinition'] == target_arn and primary.get('taskDefinition') == target_arn
                 and primary.get('rolloutState') == 'COMPLETED' and len(service.get('deployments', [])) == 1
                 and service.get('runningCount') == count and service.get('pendingCount') == 0)
        if ready:
            arns = aws.call('ecs', 'list-tasks', cluster=CLUSTER, serviceName=t['service'])['taskArns']
            if arns:
                response = aws.call('ecs', 'describe-tasks', cluster=CLUSTER, tasks=arns)
                tasks = response.get('tasks', [])
                task_ok = (not response.get('failures') and len(tasks) == count and all(
                    x.get('lastStatus') == 'RUNNING'
                    and x.get('healthStatus') in health
                    and x.get('taskDefinitionArn') == target_arn and len(x.get('containers', [])) == 1
                    and x['containers'][0].get('imageDigest') == digest for x in tasks))
                if task_ok and not t['public']:
                    return {'task_count': count}
                ips = {d['value'] for x in tasks for a in x.get('attachments', [])
                       for d in a.get('details', []) if d['name'] == 'privateIPv4Address'}
                if task_ok:
                    targets = aws.call('elbv2', 'describe-target-health',
                                       TargetGroupArn=service['loadBalancers'][0]['targetGroupArn'])['TargetHealthDescriptions']
                    healthy_ips = {x['Target']['Id'] for x in targets if x['TargetHealth']['State'] == 'healthy'}
                    if len(ips) == count and ips == healthy_ips:
                        return {'task_count': count, 'healthy_target_count': count}
        sleep(10)
    raise DeploymentError(f'Deployment did not reach {count} healthy task(s) before timeout')


def business_smoke(aws, sleep, clock):
    results = []
    for mode, instance in [('public', 'i-06c4c159ed4155c70'), ('private', 'i-06c4c159ed4155c70')]:
        command = aws.call('ssm', 'send-command', DocumentName='MemmeECSBackendSmoke', DocumentVersion='2',
                           InstanceIds=[instance], Parameters={'Mode': [mode]}, TimeoutSeconds=60,
                           Comment='Read-only Backend ECS business smoke')['Command']['CommandId']
        deadline = clock() + 90
        while clock() < deadline:
            try:
                invocation = aws.call('ssm', 'get-command-invocation', CommandId=command, InstanceId=instance)
            except DeploymentError as error:
                if 'InvocationDoesNotExist' not in str(error):
                    raise
                sleep(2); continue
            state = invocation.get('Status')
            if state == 'Success':
                try:
                    result = json.loads(invocation['StandardOutputContent'])
                except ValueError:
                    raise DeploymentError('Read-only business smoke returned invalid JSON') from None
                if not isinstance(result, dict):
                    raise DeploymentError('Read-only business smoke returned an invalid result')
                results.append({'mode': mode, 'command': command, 'result': result})
                if invocation.get('ResponseCode') != 0 or result.get('pass') is not True:
                    raise DeploymentError('Read-only business smoke failed')
                break
            if state in ['Failed', 'Cancelled', 'TimedOut', 'Cancelling']:
                raise DeploymentError('Read-only business smoke command failed')
            sleep(2)
        else:
            raise DeploymentError('Read-only business smoke timed out')
    return results


def execute(mode, source_sha=None, revision=None, *, kind='web', aws=None, sleep=time.sleep,
            clock=time.monotonic, timeout=1200):
    t = target(kind)
    if mode == 'deploy':
        if not re.fullmatch(r'[a-f0-9]{40}', source_sha or '') or revision:
            raise DeploymentError('Deploy requires only an explicit Backend source SHA')
    elif mode == 'rollback':
        revision = definition_arn(revision, kind)
        if source_sha:
            raise DeploymentError('Rollback uses a recorded revision, never the latest CI image')
    else:
        raise DeploymentError('Unknown deployment mode')
    aws = aws or Aws()
    report = {'mode': mode, 'target': kind, 'status': 'FAIL'}
    started = clock()
    try:
        if aws.call('sts', 'get-caller-identity')['Account'] != ACCOUNT:
            raise DeploymentError('Wrong AWS account')
        before = get_service(aws, kind)
        validate_service(before, kind)
        baseline = definition_arn(before['taskDefinition'], kind)
        report['previous_task_definition'] = baseline
        selected = revision if mode == 'rollback' else baseline
        td = aws.call('ecs', 'describe-task-definition', taskDefinition=selected)['taskDefinition']
        validate_definition(td, kind)
        if td.get('status') != 'ACTIVE':
            raise DeploymentError('Selected task definition must remain ACTIVE')
        digest = td['containerDefinitions'][0]['image'].split('@', 1)[1]
        # Web always has a container health check; batch is judged by it whenever one is defined.
        require_health = t['public'] or bool(td['containerDefinitions'][0].get('healthCheck'))
        if mode == 'deploy':
            primary = next((d for d in before['deployments'] if d['status'] == 'PRIMARY'), {})
            if primary.get('rolloutState') != 'COMPLETED' or before.get('pendingCount') != 0:
                raise DeploymentError('Finish the current deployment before deploying another candidate')
            report['baseline_runtime'] = wait_healthy(aws, baseline, digest, before, started + timeout, sleep, clock, kind, require_health)
            if t['public']:
                report['baseline_smoke'] = business_smoke(aws, sleep, clock)
            report['rollback_task_definition'] = baseline
            images = aws.call('ecr', 'describe-images', repositoryName='memme/backend',
                              imageIds=[{'imageTag': source_sha}])['imageDetails']
            if len(images) != 1 or source_sha not in images[0].get('imageTags', []):
                raise DeploymentError('Explicit source SHA image is missing from ECR')
            digest = images[0]['imageDigest']
            payload = prepare_definition(td, digest, source_sha, kind)
            target_arn = definition_arn(aws.call('ecs', 'register-task-definition', **payload)['taskDefinition']['taskDefinitionArn'], kind)
            report['source_sha'] = source_sha
        else:
            target_arn = revision
        report.update(task_definition=target_arn, image_digest=digest)
        aws.call('ecs', 'update-service', cluster=CLUSTER, service=t['service'], taskDefinition=target_arn)
        report['runtime'] = wait_healthy(aws, target_arn, digest, before, started + timeout, sleep, clock, kind, require_health)
        if t['public']:
            report['smoke'] = business_smoke(aws, sleep, clock)
        if mode == 'rollback':
            report['rollback_task_definition'] = target_arn
        report.update(status='PASS', elapsed_seconds=round(clock() - started, 1))
        return report
    except DeploymentError as error:
        report.update(error=str(error), elapsed_seconds=round(clock() - started, 1))
        error.report = report
        raise


def deploy_all(source_sha, **options):
    """Web first; batch only after every web check passed on the same source SHA."""
    report = {'mode': 'deploy', 'target': 'all', 'status': 'FAIL'}
    for kind in ('web', 'batch'):
        try:
            report[kind] = execute('deploy', source_sha, kind=kind, **options)
        except DeploymentError as error:
            report[kind] = error.report or {'status': 'FAIL', 'error': str(error)}
            if kind == 'web':
                report['batch'] = {'status': 'SKIPPED', 'reason': 'web deployment did not pass'}
            raise DeploymentError(f'{kind} deployment failed', report) from None
    report['status'] = 'PASS'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['deploy', 'rollback'])
    parser.add_argument('--target', choices=['all', 'web', 'batch'], default='web')
    parser.add_argument('--source-sha')
    parser.add_argument('--task-definition')
    parser.add_argument('--report', default='ecs-deployment-result.json')
    args = parser.parse_args()
    try:
        if args.target == 'all':
            if args.mode != 'deploy' or args.task_definition:
                raise DeploymentError('Rollback restores one target at a time with its own recorded revision')
            report = deploy_all(args.source_sha)
        else:
            report = execute(args.mode, args.source_sha, args.task_definition, kind=args.target)
    except DeploymentError as error:
        report = error.report or {'status': 'FAIL', 'error': str(error)}
    Path(args.report).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
