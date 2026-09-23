# V1 CD 운영 가이드

`Deploy service`는 `workflow_dispatch`로만 실행한다. 배포 시작 전, 배포 후보의 full commit SHA와 ECR image digest를 확인한다. CI가 만든 이미지를 자동으로 운영에 반영하지 않는다.

## 동작

1. Cloud Repository의 현재 commit을 대상 EC2에 고정한다.
2. Cloud workflow가 입력한 digest의 ECR 존재 여부를 확인하고, EC2의 인스턴스 역할로 ECR에 로그인해 해당 이미지를 pull한다.
3. 현재 색상의 반대쪽 Blue/Green 컨테이너를 실행한다.
4. 후보 컨테이너의 `/health`와 Nginx 경유 `/health`를 확인한다.
5. 둘 다 성공하면 Nginx upstream을 후보 색상으로 reload한다.
6. 실패하면 후보 컨테이너만 제거하고 기존 upstream과 기존 컨테이너를 유지한다.

배포가 끝나면 각 서버의 `deploy/<service>/runtime/current-deployment.json`에 서비스, 색상, digest, source SHA, 시각, health 결과가 남는다. 이전 컨테이너는 다음 배포 전까지 유지된다.

## Cloud Repository Variables

| 이름 | 값 |
| --- | --- |
| `AWS_ACCOUNT_ID` | `613538400341` |
| `AWS_REGION` | `ap-northeast-2` |
| `AWS_ROLE_TO_ASSUME` | Cloud Repository 전용 GitHub OIDC 배포 역할 ARN |
| `BACKEND_INSTANCE_ID` | `i-0ffc5f41db72dac30` |
| `AI_INSTANCE_ID` | `i-06c4c159ed4155c70` |
| `BACKEND_ECR_REPOSITORY` | `memme/backend` |
| `AI_ECR_REPOSITORY` | `memme/ai` |
| `BACKEND_RUNTIME_SECRET_ID` | `/memme/prod/backend/runtime` |
| `AI_RUNTIME_SECRET_ID` | `/memme/prod/ai/runtime` |

## AWS Secrets Manager runtime secrets

GitHub Actions나 SSM command payload에 서비스 비밀값을 넣지 않는다. 각 EC2가 배포 시 Secret Manager에서 JSON secret을 읽어 권한 `600`의 `.runtime.env`로 만든다.

`/memme/prod/backend/runtime` JSON 예시:

```json
{
  "DB_URL": "jdbc:mysql://...",
  "DB_USERNAME": "...",
  "DB_PASSWORD": "...",
  "NTS_SERVICE_KEY": "...",
  "JUSO_CONFM_KEY": "..."
}
```

`/memme/prod/ai/runtime` JSON 예시:

```json
{
  "ANTHROPIC_API_KEY": "...",
  "BACKEND_BASE_URL": "http://10.0.1.220:8080",
  "LLM_PROVIDER": "anthropic",
  "LLM_MODEL": "claude-sonnet-4-5",
  "LLM_TIMEOUT_SECONDS": "60",
  "BACKEND_TIMEOUT_SECONDS": "2.0"
}
```

각 값은 한 줄 문자열이어야 한다. AI `BACKEND_BASE_URL`은 Backend EC2의 private IP와 Nginx 포트로 통신한다.

## 필요한 최소 AWS 권한

- Cloud Repository의 GitHub OIDC role: `ssm:SendCommand`는 `AWS-RunShellScript`와 Backend/AI 인스턴스 두 대로만, `ssm:GetCommandInvocation`과 두 ECR repository의 `ecr:DescribeImages`만 허용한다.
- `BackendEC2Role`: Backend runtime secret ARN에 `secretsmanager:GetSecretValue`만 추가한다.
- `AIEC2Role`: AI runtime secret ARN에 `secretsmanager:GetSecretValue`만 추가한다.
- 두 EC2 역할에는 ECR 읽기와 SSM 관리 권한이 이미 연결되어 있다.

AI 보안 그룹은 8000 포트를 Backend 보안 그룹에서만 허용해야 한다. SSM 방식은 SSH 인바운드 규칙이나 SSH private key가 필요 없다.

## Backend HTTPS

`api.memme.kr`은 Backend EC2의 Elastic IP를 가리킨다. Backend 보안 그룹은 80/443만 공개하고 8080은 AI 보안 그룹에서만 접근할 수 있다. Nginx는 HTTP를 HTTPS로 리디렉션하며, `/.well-known/acme-challenge/`만 HTTP로 제공한다. 배포 스크립트의 내부 프록시 검사는 컨테이너 내부 8081 포트를 사용한다.

인증서는 Let's Encrypt의 HTTP-01 webroot 방식으로 `/etc/letsencrypt/live/api.memme.kr/`에 보관한다. 인증 전에는 Backend Nginx가 시작할 수 없으므로, 최초 배포 전에 DNS와 HTTP-01 경로를 준비하고 인증서를 발급한다. Nginx와 Certbot은 `/opt/memme/acme-challenge`를 공유한다. `deploy/backend/systemd/memme-cert-renew.timer`를 Backend EC2에 설치·활성화하면 `renew-cert.sh`가 매일 갱신 가능 여부를 확인하고 Nginx를 reload한다. 최초 발급 뒤 `certbot renew --dry-run`과 `https://api.memme.kr/health`를 확인한다.

현재 허용한 브라우저 출처는 `https://memme-fe.dydwn507.workers.dev` 하나다. Nginx가 preflight와 응답 CORS 헤더를 처리하며, Backend의 로컬 개발용 CORS 설정에 운영 출처를 추가하지 않는다. Frontend 주소를 바꾸면 Nginx의 출처 허용 목록도 함께 수정·배포해야 한다.
