"""ECS Backend 태스크 위치를 Prometheus file_sd로 쓰고, 배포·태스크 중지를 Grafana 주석으로 남긴다.

표준 라이브러리만 사용한다. 자격 증명은 EC2 인스턴스 역할(IMDSv2), 필요한 권한은
ecs:ListTasks, ecs:DescribeTasks, ecs:DescribeServices, ecs:DescribeTaskDefinition (읽기 전용).
"""
import base64, datetime, hashlib, hmac, json, os, time, urllib.error, urllib.request

REGION = os.environ.get('AWS_REGION', 'ap-northeast-2')
CLUSTER = os.environ.get('ECS_CLUSTER', 'memme-v2')
SERVICES = {'memme-backend-v2': 'web', 'memme-backend-batch-v2': 'batch'}
METRICS_PORT = int(os.environ.get('METRICS_PORT', '8081'))
SD_FILE = os.environ.get('SD_FILE', '/sd/ecs-backend.json')
STATE_FILE = os.environ.get('STATE_FILE', '/state/annotations.json')
GRAFANA = os.environ.get('GRAFANA_URL', 'http://grafana:3000')
GRAFANA_AUTH = 'Basic ' + base64.b64encode(f"admin:{os.environ.get('GRAFANA_PASSWORD', '')}".encode()).decode()
INTERVAL = int(os.environ.get('INTERVAL_SECONDS', '30'))
LABEL = {'web': 'BE 웹', 'batch': 'BE 배치'}

_creds = {'expires': 0}


def http(method, url, body=None, headers=None, timeout=10):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def credentials():
    if _creds['expires'] - time.time() > 300:
        return _creds
    token = http('PUT', 'http://169.254.169.254/latest/api/token',
                 headers={'X-aws-ec2-metadata-token-ttl-seconds': '21600'}).decode()
    meta = {'X-aws-ec2-metadata-token': token}
    base = 'http://169.254.169.254/latest/meta-data/iam/security-credentials/'
    role = http('GET', base, headers=meta).decode().strip()
    c = json.loads(http('GET', base + role, headers=meta))
    expires = datetime.datetime.strptime(c['Expiration'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc)
    _creds.update(key=c['AccessKeyId'], secret=c['SecretAccessKey'], token=c['Token'], expires=expires.timestamp())
    return _creds


def ecs(operation, payload):
    """ECS JSON 1.1 API를 SigV4로 서명해 호출한다."""
    c = credentials()
    host = f'ecs.{REGION}.amazonaws.com'
    body = json.dumps(payload).encode()
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date, day = now.strftime('%Y%m%dT%H%M%SZ'), now.strftime('%Y%m%d')
    headers = {'content-type': 'application/x-amz-json-1.1', 'host': host, 'x-amz-date': amz_date,
               'x-amz-security-token': c['token'],
               'x-amz-target': f'AmazonEC2ContainerServiceV20141113.{operation}'}
    signed = ';'.join(sorted(headers))
    canonical = '\n'.join(['POST', '/', '', ''.join(f'{k}:{headers[k]}\n' for k in sorted(headers)),
                           signed, hashlib.sha256(body).hexdigest()])
    scope = f'{day}/{REGION}/ecs/aws4_request'
    to_sign = '\n'.join(['AWS4-HMAC-SHA256', amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = ('AWS4' + c['secret']).encode()
    for part in (day, REGION, 'ecs', 'aws4_request'):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    headers['authorization'] = (f"AWS4-HMAC-SHA256 Credential={c['key']}/{scope}, "
                                f'SignedHeaders={signed}, Signature={signature}')
    return json.loads(http('POST', f'https://{host}/', body, headers))


def describe_tasks(service, status):
    arns = ecs('ListTasks', {'cluster': CLUSTER, 'serviceName': service, 'desiredStatus': status})['taskArns']
    return ecs('DescribeTasks', {'cluster': CLUSTER, 'tasks': arns})['tasks'] if arns else []


def private_ip(task):
    for attachment in task.get('attachments', []):
        for d in attachment.get('details', []):
            if d['name'] == 'privateIPv4Address':
                return d['value']
    return None


_source_sha = {}


def source_sha(task_definition):
    if task_definition not in _source_sha:
        tags = ecs('DescribeTaskDefinition', {'taskDefinition': task_definition, 'include': ['TAGS']}).get('tags', [])
        _source_sha[task_definition] = next((t['value'][:7] for t in tags if t['key'] == 'SourceSha'), '-')
    return _source_sha[task_definition]


def write_targets(running):
    groups = []
    for service, tasks in running.items():
        for t in tasks:
            ip = private_ip(t)
            if ip and t.get('lastStatus') == 'RUNNING':
                groups.append({'targets': [f'{ip}:{METRICS_PORT}'],
                               'labels': {'service': SERVICES[service], 'instance': ip,
                                          'task': t['taskArn'].rsplit('/', 1)[1][:8],
                                          'revision': t['taskDefinitionArn'].rsplit(':', 1)[1]}})
    tmp = SD_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(sorted(groups, key=lambda g: g['targets']), f, indent=1)
    os.replace(tmp, SD_FILE)


def grafana(method, path, payload):
    return json.loads(http(method, GRAFANA + path, json.dumps(payload).encode(),
                           {'Content-Type': 'application/json', 'Authorization': GRAFANA_AUTH}) or b'{}')


def annotate(state, services, stopped):
    for svc in services:
        kind = SERVICES[svc['serviceName']]
        for d in svc.get('deployments', []):
            entry = state['deployments'].get(d['id'])
            rev = d['taskDefinition'].rsplit(':', 1)[1]
            text = f"{LABEL[kind]} 배포 :{rev} ({source_sha(d['taskDefinition'])})"
            if entry is None:
                created = grafana('POST', '/api/annotations', {
                    'time': int(d['createdAt'] * 1000), 'tags': ['deploy', kind], 'text': text + ' 진행 중'})
                entry = state['deployments'][d['id']] = {'id': created['id'], 'done': False}
            rollout = d.get('rolloutState')
            if not entry['done'] and rollout in ('COMPLETED', 'FAILED'):
                grafana('PATCH', f"/api/annotations/{entry['id']}", {
                    'timeEnd': int(d['updatedAt'] * 1000),
                    'text': f"{text} {'완료' if rollout == 'COMPLETED' else '실패'}"})
                entry['done'] = True
    for service, tasks in stopped.items():
        kind = SERVICES[service]
        for t in tasks:
            reason = t.get('stoppedReason', '')
            if t['taskArn'] in state['stops'] or 'stoppedAt' not in t:
                continue
            state['stops'].append(t['taskArn'])
            if reason.startswith('Scaling activity initiated by (deployment'):
                continue  # 정상 롤링 교체는 배포 주석으로 충분
            exit_codes = ','.join(str(c.get('exitCode', '-')) for c in t.get('containers', []))
            grafana('POST', '/api/annotations', {
                'time': int(t['stoppedAt'] * 1000), 'tags': ['task-stop', kind],
                'text': f"{LABEL[kind]} 태스크 중지 ({t['taskArn'].rsplit('/', 1)[1][:8]}): {reason} / exit {exit_codes}"})
    state['stops'] = state['stops'][-200:]


def main():
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {'deployments': {}, 'stops': []}
    while True:
        try:
            running = {s: describe_tasks(s, 'RUNNING') for s in SERVICES}
            write_targets(running)
            services = ecs('DescribeServices', {'cluster': CLUSTER, 'services': list(SERVICES)})['services']
            stopped = {s: describe_tasks(s, 'STOPPED') for s in SERVICES}
            annotate(state, services, stopped)
            with open(STATE_FILE + '.tmp', 'w') as f:
                json.dump(state, f)
            os.replace(STATE_FILE + '.tmp', STATE_FILE)
        except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
            detail = e.read().decode()[:300] if isinstance(e, urllib.error.HTTPError) else ''
            print(f'{datetime.datetime.now().isoformat()} error: {e} {detail}', flush=True)
        time.sleep(INTERVAL)


if __name__ == '__main__':
    main()
