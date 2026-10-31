# V2 CD 운영 가이드

CI는 각 서비스 저장소의 `dev` push에서 테스트와 이미지 빌드를 하고, Backend와 AI는 커밋 SHA 태그로 ECR에 게시한다. CD는 이 저장소 `main`의 워크플로가 실행한다. 서비스별 자동 배포 스위치를 켜면 `dev` CI 성공 후 자동으로 시작하고, 끄면 지금처럼 `workflow_dispatch`로만 실행한다. 자동과 수동은 같은 배포 워크플로를 쓴다.

| 서비스 | 실행 환경 | 배포 방식 | 워크플로 |
| --- | --- | --- | --- |
| Backend 웹 | ECS Fargate 태스크 2개, ALB | Rolling (100/200, circuit breaker rollback) | `Deploy Backend ECS` |
| Backend 배치 | ECS Fargate 태스크 1개, ALB 미등록 | 교체 (0/100, 기존 태스크 중지 후 시작) | `Deploy Backend ECS` |
| AI | EC2 1대 | 같은 EC2 안 Blue/Green | `Deploy service` (`ai`) |
| Frontend | Cloudflare Workers `memme-fe` | Workers 배포 | `Deploy service` (`frontend`) |

V1 Backend EC2는 폐기했다. `Deploy service`에서 `backend` 선택지를 제거했으며 `deploy/backend/`는 V1 기록으로만 남아 있다.

## Backend ECS

절차와 입력은 [deploy/ecs/README.md](../deploy/ecs/README.md)를 따른다. 요약은 다음과 같다.

1. `target=all`이면 웹과 배치를 같은 SHA로 동시에 배포한다. 웹이 실패하면 이미 바뀐 배치를 이전 revision으로 되돌린다.
2. 웹은 ECS가 새 태스크 2개를 함께 띄워 ALB healthy를 확인한 뒤 기존 태스크를 뺀다. 기존 태스크는 ALB deregistration delay(30초) 동안 진행 중 요청을 마친다. 대상 그룹 health check는 10초 간격, 연속 2회다.
3. 배치는 스케줄러를 단독으로 소유하므로 두 개가 동시에 돌지 않도록 0/100을 유지한다. 배포 중 잠깐 배치 태스크가 없는 구간이 생긴다.
4. 롤백은 대상 하나씩, 결과 artifact에 기록된 `rollback_task_definition`으로만 한다.

### 배포 차단 조건

저장소 변수 `BACKEND_ECS_CD_ENABLED`가 `true`가 아니면 `mode=deploy`는 시작하지 않는다. 롤백은 항상 허용한다.

Redis 세션 공유와 DB 풀 보완은 Backend `dev`(PR #532)에 반영돼 2026-10-22부터 변수를 켜 두었다.

### DB 스키마 변경

Rolling 중에는 이전 버전과 새 버전 웹이 함께 동작한다. 스키마 변경은 이전 버전도 동작하는 호환 변경을 먼저 적용하고, 컬럼·테이블 제거는 새 버전 배포가 끝난 다음 배포로 미룬다.

## 자동 배포 (`Auto deploy`)

각 서비스 저장소의 `dev` push CI가 마지막 job에서 이 저장소로 `repository_dispatch`(`backend-ci-success`, `ai-ci-success`, `frontend-ci-success`, `client_payload.sha`)를 보낸다. `Auto deploy`는 판단만 하고, 배포는 위의 수동 워크플로를 같은 입력으로 실행한다.

| 순서 | 확인 | 결과 |
| --- | --- | --- |
| 1 | `AUTO_DEPLOY_<서비스>` 변수가 `true` | 아니면 건너뜀 |
| 2 | 전달된 SHA의 `dev` push CI가 성공으로 끝남 (최대 10분 대기) | 실패면 건너뜀 |
| 3 | 그 SHA가 지금도 `dev` 최신 커밋 | 더 새 커밋이 있으면 건너뜀. 그 커밋의 CI가 다시 보낸다 |
| 4 | Backend: 웹·배치가 같은 이미지이고, 그 이미지에 CI가 붙인 SHA 태그가 있음 | 아니면 중단(수동 확인) |
| 5 | Backend: 실행 중 SHA에서 새 SHA로 fast-forward이고 `docker/mysql/` 변경이 없음 | 변경이 있으면 중단. DB에 먼저 적용한 뒤 수동으로 배포한다 |
| 6 | Backend는 `Deploy Backend ECS`(`target=all`), AI·Frontend는 `Deploy service` 실행 | |

중단은 실패한 run으로 남아 GitHub 알림이 간다. 전달 토큰은 판단 대상만 알려 줄 뿐이며, `dev`에 머지되고 CI를 통과한 커밋만 배포된다.

서비스 저장소에는 Actions Secret `CLOUD_DEPLOY_DISPATCH_TOKEN`이 필요하다. 이 저장소(`KTB4-7th-Cloud`)에만 `Contents: Read and write` 권한을 준 fine-grained 토큰을 쓴다. Secret이 없으면 CI는 전달 단계만 건너뛰고 성공한다.

## AI와 Frontend (`Deploy service`)

현재 서비스 저장소 `dev`의 최신 커밋과 그 커밋의 성공한 push CI를 확인한다. 최신 CI가 진행 중이거나 실패했다면 이전 이미지를 대신 배포하지 않고 중단한다.

AI는 서버가 1대라서 Rolling을 할 수 없으므로 같은 EC2 안 Blue/Green을 유지한다.

1. 해당 SHA 태그의 ECR digest를 조회하고, Cloud 저장소의 현재 commit을 대상 EC2에 고정한다.
2. EC2의 인스턴스 역할로 ECR에 로그인해 digest 이미지를 pull하고, 현재 색상의 반대쪽 컨테이너를 실행한다.
3. 후보 컨테이너의 `/health`와 Nginx 경유 `/health`가 모두 성공하면 Nginx upstream을 후보 색상으로 reload한다.
4. 실패하면 후보 컨테이너만 제거하고 기존 upstream과 컨테이너를 유지한다.

배포 결과는 서버의 `deploy/ai/runtime/current-deployment.json`에 남고, 이전 컨테이너는 다음 배포 전까지 유지된다.

Frontend는 확인된 FE 커밋을 `VITE_API_BASE_URL=https://api.memme.kr`로 빌드해 `memme-fe` Worker에 배포하고, `memme.kr`과 `/password-reset` 응답을 확인한다.

## 롤백 (문제가 생긴 배포 되돌리기)

자동 배포 뒤 문제가 생기면 먼저 해당 `AUTO_DEPLOY_<서비스>` 변수를 비워 다음 머지가 다시 배포되지 않게 하고, 아래 버튼으로 직전 버전으로 되돌린다.

| 서비스 | 실행 | 되돌리는 방식 | 소요 |
| --- | --- | --- | --- |
| Backend | `Deploy Backend ECS`, `mode=previous`, `target=all` | 웹의 이전 revision에서 직전 이미지 SHA를 찾아, 현재 설정 그대로 웹·배치를 그 이미지로 동시 롤링한다. 문제가 된 버전 자체의 사전 검사는 건너뛴다 | 약 4분 |
| AI | `Deploy service`, `service=ai`, `action=rollback` | 직전 색상 컨테이너가 아직 떠 있으므로 health 확인 후 Nginx upstream만 되돌린다. 이미지를 다시 받지 않는다 | 1분 이내 |
| Frontend | `Deploy service`, `service=frontend`, `action=rollback` | `wrangler rollback`으로 직전 Worker 버전에 트래픽 100%를 돌린다. 다시 빌드하지 않는다 | 1분 이내 |

```bash
gh workflow run deploy-ecs.yml -R 100-hours-a-week/KTB4-7th-Cloud --ref main -f mode=previous -f target=all
gh workflow run deploy.yml -R 100-hours-a-week/KTB4-7th-Cloud --ref main -f service=ai -f action=rollback
gh workflow run deploy.yml -R 100-hours-a-week/KTB4-7th-Cloud --ref main -f service=frontend -f action=rollback
```

주의할 점은 다음과 같다.

- Backend `previous`는 DB 스키마를 되돌리지 않는다. 직전 배포에 마이그레이션이 있었다면 앱만 되돌리면 안 된다.
- 한 번 더 실행하면 Backend·Frontend는 더 이전 버전으로 간다. AI는 두 색상만 있으므로 방금 되돌린 버전으로 다시 돌아온다.
- Backend에서 특정 revision으로 되돌려야 하면 기존처럼 `mode=rollback`에 대상 하나와 revision을 지정한다.
- 원인을 고친 커밋이 `dev`에 머지되고 변수를 다시 켜면 자동 배포가 이어진다.

## Cloud Repository Variables

| 이름 | 값 |
| --- | --- |
| `AWS_ACCOUNT_ID` | `613538400341` |
| `AWS_REGION` | `ap-northeast-2` |
| `AWS_ROLE_TO_ASSUME` | AI 배포용 GitHub OIDC 역할 ARN |
| `AI_INSTANCE_ID` | `i-06c4c159ed4155c70` |
| `AI_ECR_REPOSITORY` | `memme/ai` |
| `AI_RUNTIME_SECRET_ID` | `/memme/prod/ai/runtime` |
| `BACKEND_ECS_CD_ENABLED` | Backend ECS 배포 허용 여부. 현재 `true`. 배포를 막아야 할 때만 비운다 |
| `AUTO_DEPLOY_BACKEND`, `AUTO_DEPLOY_AI`, `AUTO_DEPLOY_FRONTEND` | `true`면 해당 서비스 자동 배포. 비우면 수동만 |
| `CLOUDFLARE_ACCOUNT_ID` | `memme-fe` Worker가 속한 Cloudflare 계정 ID |

`BACKEND_INSTANCE_ID`, `BACKEND_ECR_REPOSITORY`, `BACKEND_RUNTIME_SECRET_ID`는 V1용이며 더 이상 읽지 않는다. Actions Secret `CLOUDFLARE_API_TOKEN`에는 `memme-fe` Worker 배포와 `memme.kr` Custom Domain 관리가 가능한 토큰을 등록한다.

## 런타임 비밀값

GitHub Actions나 SSM command payload에 서비스 비밀값을 넣지 않는다.

- Backend ECS: 태스크 정의의 `secrets`가 Secrets Manager를 참조한다. 배포 스크립트는 이미지 digest만 바꾸고 `secrets`와 환경변수는 기존 revision에서 그대로 복사한다.
- AI EC2: 배포 시 EC2가 `/memme/prod/ai/runtime`을 읽어 권한 `600`의 `.runtime.env`로 만든다. 각 값은 한 줄 문자열이어야 한다.

## 필요한 최소 AWS 권한

- `AWS_ROLE_TO_ASSUME`(AI): `AWS-RunShellScript`를 AI 인스턴스로만 `ssm:SendCommand`, `ssm:GetCommandInvocation`, `memme/ai`의 `ecr:DescribeImages`.
- `GitHubActionsBackendECSDeployRole`: [deploy/ecs/deploy-policy.json](../deploy/ecs/deploy-policy.json). 웹·배치 task family 등록과 두 서비스 갱신, 런타임 역할 2개 PassRole, 고정 읽기 전용 검사 문서 실행만 허용한다.
- `AIEC2Role`: AI runtime secret ARN에 `secretsmanager:GetSecretValue`, ECR 읽기, SSM 관리 권한.
