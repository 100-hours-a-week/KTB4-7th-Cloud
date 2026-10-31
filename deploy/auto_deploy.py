#!/usr/bin/env python3
"""Decide whether a product dev CI success may start its production deployment.

The dispatch payload is only a hint: the SHA must still be the dev head with a successful push CI, so a
dispatch token can never deploy anything that is not already merged and verified on dev. Backend also
stops when the change since the running image touches DB migrations, which must be applied by hand first.
"""
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEPLOY_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DEPLOY_DIR / 'ecs'))
import deploy_backend  # noqa: E402

_SPEC = importlib.util.spec_from_file_location('resolve_latest_ci', DEPLOY_DIR / 'resolve-latest-ci.py')
_RESOLVE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_RESOLVE)
WORKFLOWS = _RESOLVE.WORKFLOWS

MIGRATION_PREFIX = 'docker/mysql/'
# The compare API lists at most 300 files; a larger range cannot be proven migration-free.
COMPARE_FILE_LIMIT = 300
CI_WAIT_SECONDS = 600
CI_POLL_SECONDS = 20


class Skip(Exception):
    """Nothing to deploy for this dispatch; not an error."""


class Blocked(Exception):
    """A person must look before production changes."""


def github_json(path):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'memme-cloud-auto-deploy'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urlopen(Request(f'https://api.github.com/{path}', headers=headers), timeout=15) as response:
        return json.load(response)


def base(service):
    return f'repos/100-hours-a-week/{WORKFLOWS[service][0]}'


def wait_for_ci(service, sha, fetch, sleep=time.sleep, clock=time.monotonic):
    # The product CI dispatches from its last job, so its own run is usually still finishing.
    workflow = WORKFLOWS[service][1]
    query = f'branch=dev&event=push&head_sha={sha}&per_page=1'
    deadline = clock() + CI_WAIT_SECONDS
    while True:
        runs = fetch(f'{base(service)}/actions/workflows/{workflow}/runs?{query}')['workflow_runs']
        if runs and runs[0]['head_sha'] == sha and runs[0]['status'] == 'completed':
            if runs[0]['conclusion'] != 'success':
                raise Skip(f'dev CI for {sha} ended {runs[0]["conclusion"]}')
            return runs[0]['html_url']
        if clock() >= deadline:
            raise Blocked(f'dev CI for {sha} did not finish within {CI_WAIT_SECONDS} seconds')
        sleep(CI_POLL_SECONDS)


def running_backend_sha(aws):
    digests = set()
    for kind in ('web', 'batch'):
        service = deploy_backend.get_service(aws, kind)
        td = aws.call('ecs', 'describe-task-definition', taskDefinition=service['taskDefinition'])['taskDefinition']
        image = td['containerDefinitions'][0]['image']
        if not image.startswith(deploy_backend.IMAGE_PREFIX):
            raise Blocked(f'{kind} is not running a pinned Backend ECR digest')
        digests.add(image[len(deploy_backend.IMAGE_PREFIX):])
    if len(digests) != 1:
        raise Blocked('web and batch run different images; deploy them together by hand first')
    images = aws.call('ecr', 'describe-images', repositoryName='memme/backend',
                      imageIds=[{'imageDigest': digests.pop()}])['imageDetails']
    shas = {tag for detail in images for tag in detail.get('imageTags', []) if re.fullmatch(r'[0-9a-f]{40}', tag)}
    if len(shas) != 1:
        raise Blocked('the running Backend image has no single source SHA tag; it was not built by dev CI')
    return shas.pop()


def migration_changes(running_sha, sha, fetch):
    try:
        compare = fetch(f"{base('backend')}/compare/{running_sha}...{sha}")
    except HTTPError as error:
        raise Blocked(f'cannot compare running {running_sha} with {sha} ({error.code}); '
                      'the running commit may not exist on GitHub') from None
    if compare['status'] != 'ahead':
        raise Blocked(f"{sha} is {compare['status']} of running {running_sha}, not a fast-forward")
    files = compare.get('files', [])
    if len(files) >= COMPARE_FILE_LIMIT:
        raise Blocked(f'{len(files)} files changed since {running_sha}; too many to check for migrations')
    return [item['filename'] for item in files if item['filename'].startswith(MIGRATION_PREFIX)]


def decide(service, sha, fetch=github_json, aws=None, sleep=time.sleep, clock=time.monotonic):
    if service not in WORKFLOWS:
        raise Blocked(f'unknown service {service!r}')
    if not re.fullmatch(r'[0-9a-f]{40}', sha or ''):
        raise Blocked('dispatch payload must carry a full 40-character SHA')
    ci_url = wait_for_ci(service, sha, fetch, sleep, clock)
    head = fetch(f'{base(service)}/branches/dev')['commit']['sha']
    if head != sha:
        raise Skip(f'dev moved on to {head}; its own CI dispatch deploys it')
    if service == 'backend':
        running = running_backend_sha(aws or deploy_backend.Aws())
        if running == sha:
            raise Skip(f'{sha} is already running')
        migrations = migration_changes(running, sha, fetch)
        if migrations:
            raise Blocked('DB migration files changed since the running image: ' + ', '.join(migrations)
                          + '. Apply them to Primary first, then run Deploy Backend ECS by hand.')
    return ci_url


def main():
    service, sha = sys.argv[1], sys.argv[2]
    try:
        ci_url = decide(service, sha)
    except Skip as reason:
        print(f'::notice title=Auto deploy skipped::{reason}', file=sys.stderr)
        print('deploy=false')
        return 0
    except (Blocked, deploy_backend.DeploymentError, HTTPError, URLError, KeyError) as reason:
        print(f'::error title=Auto deploy blocked::{reason}', file=sys.stderr)
        return 1
    print('deploy=true')
    print(f'ci_run_url={ci_url}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
