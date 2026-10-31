import importlib.util
import pathlib
import unittest
from urllib.error import HTTPError

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'deploy' / 'auto_deploy.py'
SPEC = importlib.util.spec_from_file_location('auto_deploy', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

ACCOUNT = '613538400341'
NEW, RUNNING = 'a' * 40, 'b' * 40
DIGEST = 'sha256:' + '1' * 64
IMAGE = f'{ACCOUNT}.dkr.ecr.ap-northeast-2.amazonaws.com/memme/backend@{DIGEST}'


def github(head=NEW, conclusion='success', status='completed', compare_status='ahead', files=()):
    calls = []

    def fetch(path):
        calls.append(path)
        if '/runs?' in path:
            return {'workflow_runs': [{'head_sha': NEW, 'status': status, 'conclusion': conclusion,
                                       'html_url': 'https://github.com/run/1'}]}
        if path.endswith('/branches/dev'):
            return {'commit': {'sha': head}}
        if '/compare/' in path:
            return {'status': compare_status, 'files': [{'filename': name} for name in files]}
        raise AssertionError(path)

    fetch.calls = calls
    return fetch


class FakeAws:
    def __init__(self, tags=(RUNNING,), batch_image=IMAGE):
        self.tags, self.batch_image = list(tags), batch_image

    def call(self, namespace, operation, **parameters):
        if operation == 'describe-services':
            name = parameters['services'][0]
            return {'services': [{'taskDefinition': f'{name}:9'}]}
        if operation == 'describe-task-definition':
            image = self.batch_image if 'batch' in parameters['taskDefinition'] else IMAGE
            return {'taskDefinition': {'containerDefinitions': [{'image': image}]}}
        if operation == 'describe-images':
            return {'imageDetails': [{'imageTags': self.tags}]}
        raise AssertionError(operation)


def no_sleep(_):
    pass


class AutoDeployTest(unittest.TestCase):
    def test_frontend_deploys_current_dev_head_with_successful_ci(self):
        self.assertEqual(MODULE.decide('frontend', NEW, github()), 'https://github.com/run/1')

    def test_rejects_short_or_missing_sha(self):
        with self.assertRaises(MODULE.Blocked):
            MODULE.decide('ai', 'abc123', github())

    def test_skips_when_dev_has_a_newer_commit(self):
        with self.assertRaisesRegex(MODULE.Skip, 'dev moved on'):
            MODULE.decide('ai', NEW, github(head='c' * 40))

    def test_skips_failed_ci(self):
        with self.assertRaisesRegex(MODULE.Skip, 'ended failure'):
            MODULE.decide('ai', NEW, github(conclusion='failure'))

    def test_waits_for_running_ci_then_blocks_after_deadline(self):
        clock = iter(range(0, 10_000, 300))
        with self.assertRaisesRegex(MODULE.Blocked, 'did not finish'):
            MODULE.decide('ai', NEW, github(status='in_progress'), sleep=no_sleep, clock=lambda: next(clock))

    def test_backend_deploys_fast_forward_without_migrations(self):
        fetch = github(files=['src/main/java/App.java', 'docker/Dockerfile'])
        self.assertEqual(MODULE.decide('backend', NEW, fetch, FakeAws()), 'https://github.com/run/1')
        self.assertTrue(any(f'/compare/{RUNNING}...{NEW}' in call for call in fetch.calls))

    def test_backend_blocks_migration_changes(self):
        fetch = github(files=['docker/mysql/migrations/20261031-add-x.sql'])
        with self.assertRaisesRegex(MODULE.Blocked, 'DB migration'):
            MODULE.decide('backend', NEW, fetch, FakeAws())

    def test_backend_skips_when_already_running(self):
        with self.assertRaisesRegex(MODULE.Skip, 'already running'):
            MODULE.decide('backend', NEW, github(), FakeAws(tags=[NEW, 'latest']))

    def test_backend_blocks_image_without_ci_sha_tag(self):
        with self.assertRaisesRegex(MODULE.Blocked, 'no single source SHA'):
            MODULE.decide('backend', NEW, github(), FakeAws(tags=['prod-dev-web-local']))

    def test_backend_blocks_web_and_batch_on_different_images(self):
        other = IMAGE.replace('1' * 64, '2' * 64)
        with self.assertRaisesRegex(MODULE.Blocked, 'different images'):
            MODULE.decide('backend', NEW, github(), FakeAws(batch_image=other))

    def test_backend_blocks_non_fast_forward(self):
        with self.assertRaisesRegex(MODULE.Blocked, 'diverged'):
            MODULE.decide('backend', NEW, github(compare_status='diverged'), FakeAws())

    def test_backend_blocks_running_commit_missing_on_github(self):
        def fetch(path):
            if '/compare/' in path:
                raise HTTPError(path, 404, 'Not Found', None, None)
            return github()(path)

        with self.assertRaisesRegex(MODULE.Blocked, 'may not exist'):
            MODULE.decide('backend', NEW, fetch, FakeAws())

    def test_backend_blocks_ranges_too_large_to_check(self):
        files = [f'src/F{i}.java' for i in range(MODULE.COMPARE_FILE_LIMIT)]
        with self.assertRaisesRegex(MODULE.Blocked, 'too many'):
            MODULE.decide('backend', NEW, github(files=files), FakeAws())


if __name__ == '__main__':
    unittest.main()
