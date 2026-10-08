"""Deploy or restore Memme Backend ECS without changing its network or Secrets."""
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
SERVICE = 'memme-backend-v2'
FAMILY = SERVICE
TD_PREFIX = f'arn:aws:ecs:{REGION}:{ACCOUNT}:task-definition/{FAMILY}:'
SERVICE_ARN = f'arn:aws:ecs:{REGION}:{ACCOUNT}:service/{CLUSTER}/{SERVICE}'
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
        result = subprocess.run(command, text=True, capture_output=True, timeout=90)
        if result.returncode:
            # Never echo command payloads or raw AWS responses into CI logs.
            code = re.search(r'\((\w+)\)', result.stderr)
            raise DeploymentError(f'{namespace}:{operation} failed ({code.group(1) if code else "AWS_ERROR"})')
        return json.loads(result.stdout)


def definition_arn(value):
    if value and re.fullmatch(re.escape(FAMILY) + r':[1-9]\d*', value):
        value = TD_PREFIX + value.split(':')[1]
    if not value or not re.fullmatch(re.escape(TD_PREFIX) + r'[1-9]\d*', value):
        raise DeploymentError('Specify a recorded memme-backend-v2 revision')
    return value


def validate_definition(td):
    if (td.get('family') != FAMILY or td.get('networkMode') != 'awsvpc'
            or td.get('requiresCompatibilities') != ['FARGATE']):
        raise DeploymentError('Unexpected Backend task family or execution mode')
    for field, role in [('taskRoleArn', 'MemmeBackendV2TaskRole'),
                        ('executionRoleArn', 'MemmeBackendV2ExecutionRole')]:
        if td.get(field) != f'arn:aws:iam::{ACCOUNT}:role/{role}':
            raise DeploymentError('Unexpected task IAM role')
    containers = td.get('containerDefinitions', [])
    if len(containers) != 1 or containers[0].get('name') != 'backend':
        raise DeploymentError('Unexpected Backend container configuration')
    container = containers[0]
    if not re.fullmatch(re.escape(IMAGE_PREFIX) + r'sha256:[a-f0-9]{64}', container.get('image', '')):
        raise DeploymentError('Backend image must use an immutable digest in the approved repository')
    env = {x['name']: x['value'] for x in container.get('environment', [])}
    if any(env.get(n) != '-' for n in CRONS) or env.get('QA_ACCOUNT_ENABLED') != 'false':
        raise DeploymentError('ECS web tasks must keep schedulers and QA seeding disabled')
    if env.get('SERVER_SERVLET_SESSION_COOKIE_SECURE') != 'true' or not container.get('healthCheck'):
        raise DeploymentError('Secure session cookies and container health check are required')
    if container.get('privileged') or container.get('command') or container.get('entryPoint'):
        raise DeploymentError('Unreviewed container execution override')


def prepare_definition(td, digest, source_sha):
    validate_definition(td)
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest or '') or not re.fullmatch(r'[a-f0-9]{40}', source_sha or ''):
        raise DeploymentError('Invalid immutable image identity')
    result = {k: copy.deepcopy(td[k]) for k in REGISTER_FIELDS if k in td}
    result['containerDefinitions'][0]['image'] = IMAGE_PREFIX + digest
    result['tags'] = [{'key': 'Project', 'value': 'memme'}, {'key': 'Service', 'value': FAMILY},
                      {'key': 'SourceSha', 'value': source_sha}]
    return result


def validate_service(service):
    config = service.get('deploymentConfiguration', {})
    breaker = config.get('deploymentCircuitBreaker', {})
    if (service.get('serviceArn') != SERVICE_ARN or service.get('desiredCount') != 2
            or config.get('minimumHealthyPercent') != 100 or config.get('maximumPercent') != 150
            or not breaker.get('enable') or not breaker.get('rollback')):
        raise DeploymentError('Service must retain desired2, rolling100/150 and circuit-breaker rollback')
    if len(service.get('loadBalancers', [])) != 1 or len(service.get('serviceRegistries', [])) != 1:
        raise DeploymentError('Expected ALB and private service discovery are required')


def get_service(aws):
    response = aws.call('ecs', 'describe-services', cluster=CLUSTER, services=[SERVICE])
    if response.get('failures') or len(response.get('services', [])) != 1:
        raise DeploymentError('Backend ECS service was not found')
    return response['services'][0]


def wait_healthy(aws, target, digest, before, deadline, sleep, clock):
    started = clock()
    while clock() < deadline:
        service = get_service(aws)
        validate_service(service)
        if (service['loadBalancers'] != before['loadBalancers']
                or service['serviceRegistries'] != before['serviceRegistries']):
            raise DeploymentError('ALB or discovery changed during deployment')
        primary = next((d for d in service.get('deployments', []) if d['status'] == 'PRIMARY'), {})
        if any(d.get('taskDefinition') == target and d.get('rolloutState') == 'FAILED'
               for d in service.get('deployments', [])):
            raise DeploymentError('Candidate deployment failed; inspect circuit-breaker recovery')
        if service['taskDefinition'] != target and clock() - started >= 30:
            raise DeploymentError('Requested revision is no longer the active deployment')
        ready = (service['taskDefinition'] == target and primary.get('taskDefinition') == target
                 and primary.get('rolloutState') == 'COMPLETED'
                 and service.get('runningCount') == 2 and service.get('pendingCount') == 0)
        if ready:
            arns = aws.call('ecs', 'list-tasks', cluster=CLUSTER, serviceName=SERVICE)['taskArns']
            if arns:
                response = aws.call('ecs', 'describe-tasks', cluster=CLUSTER, tasks=arns)
                tasks = response.get('tasks', [])
                task_ok = (not response.get('failures') and len(tasks) == 2 and all(
                    t.get('lastStatus') == 'RUNNING' and t.get('healthStatus') == 'HEALTHY'
                    and t.get('taskDefinitionArn') == target and len(t.get('containers', [])) == 1
                    and t['containers'][0].get('imageDigest') == digest for t in tasks))
                ips = {d['value'] for t in tasks for a in t.get('attachments', [])
                       for d in a.get('details', []) if d['name'] == 'privateIPv4Address'}
                targets = aws.call('elbv2', 'describe-target-health',
                                   TargetGroupArn=service['loadBalancers'][0]['targetGroupArn'])['TargetHealthDescriptions']
                healthy_ips = {t['Target']['Id'] for t in targets if t['TargetHealth']['State'] == 'healthy'}
                if task_ok and len(ips) == 2 and ips == healthy_ips:
                    return {'task_count': 2, 'healthy_target_count': 2}
        sleep(10)
    raise DeploymentError('Deployment did not reach two healthy tasks and matching ALB targets before timeout')


def business_smoke(aws, sleep, clock):
    results = []
    for mode, instance in [('public', 'i-0ffc5f41db72dac30'), ('private', 'i-06c4c159ed4155c70')]:
        command = aws.call('ssm', 'send-command', DocumentName='MemmeECSBackendSmoke', DocumentVersion='1',
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
                result = json.loads(invocation['StandardOutputContent'])
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


def execute(mode, source_sha=None, revision=None, *, aws=None, sleep=time.sleep, clock=time.monotonic, timeout=1200):
    if mode == 'deploy':
        if not re.fullmatch(r'[a-f0-9]{40}', source_sha or '') or revision:
            raise DeploymentError('Deploy requires only an explicit Backend source SHA')
    elif mode == 'rollback':
        revision = definition_arn(revision)
        if source_sha:
            raise DeploymentError('Rollback uses a recorded revision, never the latest CI image')
    else:
        raise DeploymentError('Unknown deployment mode')
    aws = aws or Aws()
    report = {'mode': mode, 'status': 'FAIL'}
    started = clock()
    try:
        if aws.call('sts', 'get-caller-identity')['Account'] != ACCOUNT:
            raise DeploymentError('Wrong AWS account')
        before = get_service(aws)
        validate_service(before)
        baseline = definition_arn(before['taskDefinition'])
        report['rollback_task_definition'] = baseline
        selected = revision if mode == 'rollback' else baseline
        td = aws.call('ecs', 'describe-task-definition', taskDefinition=selected)['taskDefinition']
        validate_definition(td)
        if td.get('status') != 'ACTIVE':
            raise DeploymentError('Selected task definition must remain ACTIVE')
        digest = td['containerDefinitions'][0]['image'].split('@', 1)[1]
        if mode == 'deploy':
            primary = next((d for d in before['deployments'] if d['status'] == 'PRIMARY'), {})
            if primary.get('rolloutState') != 'COMPLETED' or before.get('pendingCount') != 0:
                raise DeploymentError('Finish the current deployment before deploying another candidate')
            report['baseline_runtime'] = wait_healthy(aws, baseline, digest, before, started + timeout, sleep, clock)
            report['baseline_smoke'] = business_smoke(aws, sleep, clock)
            images = aws.call('ecr', 'describe-images', repositoryName='memme/backend',
                              imageIds=[{'imageTag': source_sha}])['imageDetails']
            if len(images) != 1 or source_sha not in images[0].get('imageTags', []):
                raise DeploymentError('Explicit source SHA image is missing from ECR')
            digest = images[0]['imageDigest']
            payload = prepare_definition(td, digest, source_sha)
            target = definition_arn(aws.call('ecs', 'register-task-definition', **payload)['taskDefinition']['taskDefinitionArn'])
            report['source_sha'] = source_sha
        else:
            target = revision
        report.update(task_definition=target, image_digest=digest)
        aws.call('ecs', 'update-service', cluster=CLUSTER, service=SERVICE, taskDefinition=target)
        report['runtime'] = wait_healthy(aws, target, digest, before, started + timeout, sleep, clock)
        report['smoke'] = business_smoke(aws, sleep, clock)
        report.update(status='PASS', elapsed_seconds=round(clock() - started, 1))
        return report
    except DeploymentError as error:
        report.update(error=str(error), elapsed_seconds=round(clock() - started, 1))
        error.report = report
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['deploy', 'rollback'])
    parser.add_argument('--source-sha')
    parser.add_argument('--task-definition')
    parser.add_argument('--report', default='ecs-deployment-result.json')
    args = parser.parse_args()
    try:
        report = execute(args.mode, args.source_sha, args.task_definition)
    except DeploymentError as error:
        report = error.report or {'status': 'FAIL', 'error': str(error)}
    Path(args.report).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
