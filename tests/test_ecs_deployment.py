import copy
import importlib.util
import json
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'deploy/ecs/deploy_backend.py'
MODULE = None
if SCRIPT.exists():
    spec = importlib.util.spec_from_file_location('ecs_deployment', SCRIPT)
    MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MODULE)

ACCOUNT = '613538400341'
PREFIX = f'arn:aws:ecs:ap-northeast-2:{ACCOUNT}:task-definition/memme-backend-v2:'
OLD, NEW = PREFIX + '3', PREFIX + '4'
DIGEST = 'sha256:' + '1' * 64
SHA = 'a' * 40
CRONS = ['LOGIN_RATE_LIMIT_CLEANUP_CRON', 'PASSWORD_RESET_RATE_LIMIT_CLEANUP_CRON',
         'SOLUTION_DAILY_CRON', 'SOLUTION_READY_NOTIFICATION_CRON', 'SALES_UPLOAD_REMINDER_CRON']


def definition(arn=OLD):
    return {'taskDefinitionArn': arn, 'revision': int(arn.rsplit(':', 1)[1]), 'status': 'ACTIVE',
            'family': 'memme-backend-v2', 'networkMode': 'awsvpc', 'requiresCompatibilities': ['FARGATE'],
            'cpu': '1024', 'memory': '2048',
            'taskRoleArn': f'arn:aws:iam::{ACCOUNT}:role/MemmeBackendV2TaskRole',
            'executionRoleArn': f'arn:aws:iam::{ACCOUNT}:role/MemmeBackendV2ExecutionRole',
            'containerDefinitions': [{'name': 'backend', 'image': f'{ACCOUNT}.dkr.ecr.ap-northeast-2.amazonaws.com/memme/backend@{DIGEST}',
                'essential': True, 'healthCheck': {'command': ['CMD-SHELL', 'check /health']},
                'environment': [{'name': n, 'value': '-'} for n in CRONS] + [
                    {'name': 'QA_ACCOUNT_ENABLED', 'value': 'false'},
                    {'name': 'SERVER_SERVLET_SESSION_COOKIE_SECURE', 'value': 'true'}],
                'secrets': [{'name': 'DB_PASSWORD', 'valueFrom': 'arn:aws:secretsmanager:ap-northeast-2:613538400341:secret:runtime:DB_PASSWORD::'}]}]}


class FakeAws:
    def __init__(self, functional_failure=False, unhealthy_target=False, broken_baseline=False):
        self.current = OLD
        self.calls = []
        self.definitions = {OLD: definition()}
        self.functional_failure = functional_failure
        self.unhealthy_target = unhealthy_target
        self.broken_baseline = broken_baseline

    def call(self, namespace, operation, **p):
        self.calls.append((namespace, operation, copy.deepcopy(p)))
        if namespace == 'sts':
            return {'Account': ACCOUNT}
        if operation == 'describe-services':
            return {'services': [{'serviceArn': f'arn:aws:ecs:ap-northeast-2:{ACCOUNT}:service/memme-v2/memme-backend-v2',
                'taskDefinition': self.current, 'desiredCount': 2, 'runningCount': 2, 'pendingCount': 0,
                'deploymentConfiguration': {'minimumHealthyPercent': 100, 'maximumPercent': 150,
                    'deploymentCircuitBreaker': {'enable': True, 'rollback': True}},
                'serviceRegistries': [{'registryArn': 'unchanged-discovery'}],
                'loadBalancers': [{'targetGroupArn': 'target-group', 'containerName': 'backend', 'containerPort': 8080}],
                'deployments': [{'status': 'PRIMARY', 'rolloutState': 'COMPLETED', 'taskDefinition': self.current}]}]}
        if operation == 'describe-task-definition':
            return {'taskDefinition': copy.deepcopy(self.definitions[p['taskDefinition']])}
        if operation == 'describe-images':
            return {'imageDetails': [{'imageDigest': DIGEST, 'imageTags': [SHA]}]}
        if operation == 'register-task-definition':
            self.definitions[NEW] = {**copy.deepcopy(p), 'taskDefinitionArn': NEW, 'status': 'ACTIVE'}
            return {'taskDefinition': {'taskDefinitionArn': NEW}}
        if operation == 'update-service':
            self.current = p['taskDefinition']
            return {'service': {}}
        if operation == 'list-tasks':
            return {'taskArns': ['task1', 'task2']}
        if operation == 'describe-tasks':
            return {'tasks': [{'taskArn': n, 'lastStatus': 'RUNNING', 'healthStatus': 'HEALTHY',
                'taskDefinitionArn': self.current, 'containers': [{'imageDigest': DIGEST}],
                'attachments': [{'details': [{'name': 'privateIPv4Address', 'value': f'10.0.1.{i}'}]}]}
                for i, n in enumerate(['task1', 'task2'], 1)]}
        if operation == 'describe-target-health':
            return {'TargetHealthDescriptions': [{'Target': {'Id': f'10.0.1.{i}', 'Port': 8080},
                'TargetHealth': {'State': 'unhealthy' if i == 2 and self.unhealthy_target else 'healthy'}} for i in [1, 2]]}
        if operation == 'send-command':
            return {'Command': {'CommandId': 'smoke-command'}}
        if operation == 'get-command-invocation':
            failed = self.broken_baseline or (self.functional_failure and self.current == NEW)
            return {'Status': 'Success', 'ResponseCode': 0,
                    'StandardOutputContent': json.dumps({'mode': 'smoke', 'pass': not failed,
                        'cases': [{'name': 'cors', 'pass': not failed}]})}
        raise AssertionError((namespace, operation, p))


class EcsDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(MODULE, 'ECS deployment implementation is missing')

    def test_register_payload_preserves_runtime_but_removes_response_fields(self):
        original = definition()
        payload = MODULE.prepare_definition(original, DIGEST, SHA)
        self.assertEqual(payload['containerDefinitions'], original['containerDefinitions'])
        self.assertEqual(payload['taskRoleArn'], original['taskRoleArn'])
        self.assertEqual(payload['executionRoleArn'], original['executionRoleArn'])
        self.assertNotIn('revision', payload)
        self.assertNotIn('taskDefinitionArn', payload)
        self.assertEqual(original, definition())

    def test_rejects_extra_container_or_untrusted_roles_before_registration(self):
        for field in ('taskRoleArn', 'executionRoleArn'):
            td = definition(); td[field] = 'arn:aws:iam::613538400341:role/Administrator'
            with self.assertRaises(MODULE.DeploymentError):
                MODULE.prepare_definition(td, DIGEST, SHA)
        td = definition(); td['containerDefinitions'].append({'name': 'unreviewed-sidecar'})
        with self.assertRaises(MODULE.DeploymentError):
            MODULE.prepare_definition(td, DIGEST, SHA)

    def test_rejects_mutable_image_and_scheduler_enabled(self):
        with self.assertRaises(MODULE.DeploymentError):
            MODULE.prepare_definition(definition(), 'latest', SHA)
        td = definition(); td['containerDefinitions'][0]['environment'][0]['value'] = '0 * * * * *'
        with self.assertRaises(MODULE.DeploymentError):
            MODULE.prepare_definition(td, DIGEST, SHA)

    def test_invalid_input_does_not_call_aws(self):
        aws = FakeAws()
        for mode, sha, revision in [('deploy', 'latest', None), ('rollback', None, PREFIX.replace('memme-backend-v2', 'other') + '3')]:
            with self.assertRaises(MODULE.DeploymentError):
                MODULE.execute(mode, sha, revision, aws=aws)
        self.assertEqual(aws.calls, [])

    def test_service_guard_refuses_scaling_or_disabled_rollback(self):
        service = FakeAws().call('ecs', 'describe-services')['services'][0]
        service['desiredCount'] = 1
        with self.assertRaises(MODULE.DeploymentError):
            MODULE.validate_service(service)
        service['desiredCount'] = 2; service['deploymentConfiguration']['deploymentCircuitBreaker']['rollback'] = False
        with self.assertRaises(MODULE.DeploymentError):
            MODULE.validate_service(service)

    def test_deploy_resolves_digest_then_validates_tasks_targets_and_business(self):
        aws = FakeAws(); result = MODULE.execute('deploy', SHA, None, aws=aws)
        self.assertEqual(result['task_definition'], NEW)
        self.assertEqual(result['rollback_task_definition'], OLD)
        self.assertEqual(result['image_digest'], DIGEST)
        self.assertEqual(result['status'], 'PASS')
        update = next(p for _, op, p in aws.calls if op == 'update-service')
        self.assertEqual(set(update), {'cluster', 'service', 'taskDefinition'})
        smokes = [p for _, op, p in aws.calls if op == 'send-command']
        self.assertEqual(len(smokes), 4)
        self.assertTrue(all(p['DocumentName'] == 'MemmeECSBackendSmoke' and p['DocumentVersion'] == '1' for p in smokes))
        self.assertTrue(all('commands' not in p['Parameters'] for p in smokes))

    def test_healthy_deployment_with_failed_business_smoke_is_failure(self):
        aws = FakeAws(functional_failure=True)
        with self.assertRaises(MODULE.DeploymentError) as failed:
            MODULE.execute('deploy', SHA, None, aws=aws)
        self.assertEqual(failed.exception.report['status'], 'FAIL')
        self.assertEqual(failed.exception.report['rollback_task_definition'], OLD)
        # Health success alone must never cause a success report or implicit rollback claim.
        self.assertEqual(aws.current, NEW)

    def test_broken_baseline_is_rejected_before_any_deployment_mutation(self):
        aws = FakeAws(broken_baseline=True)
        with self.assertRaises(MODULE.DeploymentError):
            MODULE.execute('deploy', SHA, None, aws=aws)
        self.assertFalse(any(op in ['register-task-definition', 'update-service'] for _, op, _ in aws.calls))

    def test_recorded_rollback_never_uses_latest_image_or_registers_a_revision(self):
        aws = FakeAws(); aws.current = NEW; aws.definitions[NEW] = definition(NEW)
        result = MODULE.execute('rollback', None, OLD, aws=aws)
        self.assertEqual(result['task_definition'], OLD)
        self.assertEqual(aws.current, OLD)
        self.assertFalse(any(op in ['describe-images', 'register-task-definition'] for _, op, _ in aws.calls))

    def test_two_running_tasks_with_one_unhealthy_target_timeout(self):
        aws = FakeAws(unhealthy_target=True); ticks = iter(range(0, 1000, 10))
        with self.assertRaises(MODULE.DeploymentError):
            MODULE.execute('deploy', SHA, None, aws=aws, sleep=lambda _: None,
                           clock=lambda: next(ticks), timeout=20)
        self.assertFalse(any(op == 'send-command' for _, op, _ in aws.calls))

    def test_circuit_breaker_return_to_old_revision_is_not_candidate_success(self):
        aws = FakeAws(); original = aws.call
        def call(namespace, op, **p):
            if op == 'describe-services' and any(x[1] == 'update-service' for x in aws.calls):
                aws.current = OLD
            return original(namespace, op, **p)
        aws.call = call
        with self.assertRaises(MODULE.DeploymentError):
            MODULE.execute('deploy', SHA, None, aws=aws, sleep=lambda _: None, clock=iter(range(0, 1000, 10)).__next__, timeout=200)
        self.assertEqual(sum(op == 'send-command' for _, op, _ in aws.calls), 2)


if __name__ == '__main__':
    unittest.main()
