# V2 CD 운영 가이드

CI는 각 서비스 저장소의 `dev` push에서 테스트와 이미지 빌드를 하고, Backend와 AI는 커밋 SHA 태그로 ECR에 게시한다. CI 성공만으로 운영에 자동 배포되지는 않는다. CD는 이 저장소 `main`에서 `workflow_dispatch`로만 실행한다.

| 서비스 | 실행 환경 | 배포 방식 | 워크플로 |
| --- | --- | --- | --- |
| Backend 웹 | ECS Fargate 태스크 2개, ALB | Rolling (100/150, circuit breaker rollback) | `Deploy Backend ECS` |
| Backend 배치 | ECS Fargate 태스크 1개, ALB 미등록 | 교체 (0/100, 기존 태스크 중지 후 시작) | `Deploy Backend ECS` |
| AI | EC2 1대 | 같은 EC2 안 Blue/Green | `Deploy service` (`ai`) |
| Frontend | Cloudflare Workers `memme-fe` | Workers 배포 | `Deploy service` (`frontend`) |

V1 Backend EC2는 폐기했다. `Deploy service`에서 `backend` 선택지를 제거했으며 `deploy/backend/`는 V1 기록으로만 남아 있다.

## Backend ECS

절차와 입력은 [deploy/ecs/README.md](../deploy/ecs/README.md)를 따른다. 요약은 다음과 같다.

1. `target=all`이면 웹을 먼저 배포하고, 웹의 태스크·ALB·업무 응답 검사가 모두 통과한 뒤에만 같은 SHA로 배치를 배포한다.
2. 웹은 ECS가 새 태스크를 하나 띄워 ALB healthy를 확인한 뒤 기존 태스크를 하나 빼는 방식으로 한 개씩 교체한다. 기존 태스크는 ALB deregistration delay 동안 진행 중 요청을 마친다.
3. 배치는 스케줄러를 단독으로 소유하므로 두 개가 동시에 돌지 않도록 0/100을 유지한다. 배포 중 잠깐 배치 태스크가 없는 구간이 생긴다.
4. 롤백은 대상 하나씩, 결과 artifact에 기록된 `rollback_task_definition`으로만 한다.

### 배포 차단 조건

저장소 변수 `BACKEND_ECS_CD_ENABLED`가 `true`가 아니면 `mode=deploy`는 시작하지 않는다. 롤백은 항상 허용한다.

2026-10-20 기준 운영 웹 `:16`과 배치 `:7`은 Backend `dev` ba4ff87에 Redis 세션 공유와 DB 풀 보완을 덧붙여 별도 빌드한 이미지다. Backend `dev`에는 이 보완이 아직 없으므로 CI 이미지를 그대로 배포하면 웹 2개 간 세션 공유와 풀 제어가 빠진다. 보완이 `dev`에 머지되고 CI가 이미지를 게시한 뒤 변수를 켠다.

### DB 스키마 변경

Rolling 중에는 이전 버전과 새 버전 웹이 함께 동작한다. 스키마 변경은 이전 버전도 동작하는 호환 변경을 먼저 적용하고, 컬럼·테이블 제거는 새 버전 배포가 끝난 다음 배포로 미룬다.

## AI와 Frontend (`Deploy service`)

현재 서비스 저장소 `dev`의 최신 커밋과 그 커밋의 성공한 push CI를 확인한다. 최신 CI가 진행 중이거나 실패했다면 이전 이미지를 대신 배포하지 않고 중단한다.

AI는 서버가 1대라서 Rolling을 할 수 없으므로 같은 EC2 안 Blue/Green을 유지한다.

1. 해당 SHA 태그의 ECR digest를 조회하고, Cloud 저장소의 현재 commit을 대상 EC2에 고정한다.
2. EC2의 인스턴스 역할로 ECR에 로그인해 digest 이미지를 pull하고, 현재 색상의 반대쪽 컨테이너를 실행한다.
3. 후보 컨테이너의 `/health`와 Nginx 경유 `/health`가 모두 성공하면 Nginx upstream을 후보 색상으로 reload한다.
4. 실패하면 후보 컨테이너만 제거하고 기존 upstream과 컨테이너를 유지한다.

배포 결과는 서버의 `deploy/ai/runtime/current-deployment.json`에 남고, 이전 컨테이너는 다음 배포 전까지 유지된다.

Frontend는 확인된 FE 커밋을 `VITE_API_BASE_URL=https://api.memme.kr`로 빌드해 `memme-fe` Worker에 배포하고, `memme.kr`과 `/password-reset` 응답을 확인한다.

## Cloud Repository Variables

| 이름 | 값 |
| --- | --- |
| `AWS_ACCOUNT_ID` | `613538400341` |
| `AWS_REGION` | `ap-northeast-2` |
| `AWS_ROLE_TO_ASSUME` | AI 배포용 GitHub OIDC 역할 ARN |
| `AI_INSTANCE_ID` | `i-06c4c159ed4155c70` |
| `AI_ECR_REPOSITORY` | `memme/ai` |
| `AI_RUNTIME_SECRET_ID` | `/memme/prod/ai/runtime` |
| `BACKEND_ECS_CD_ENABLED` | Backend ECS 배포 허용 여부. Redis 보완이 `dev`에 들어가기 전에는 비워 둔다 |
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
