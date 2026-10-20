# Backend ECS 수동 배포와 복구

이 경로는 `memme-v2` 클러스터의 웹 `memme-backend-v2`와 배치 `memme-backend-batch-v2`만 변경한다. 네트워크·Secrets·운영 DNS는 바꾸지 않는다.

GitHub Actions의 **Deploy Backend ECS**를 main에서 수동 실행한다.

| 입력 | 의미 |
| --- | --- |
| mode=deploy | Backend CI가 이미 올린 이미지로 정상 배포. 저장소 변수 `BACKEND_ECS_CD_ENABLED=true`일 때만 실행 |
| mode=rollback | 기록해 둔 정상 task definition으로 복구 |
| target | `all`은 웹 → 배치 순서로 배포(롤백 불가). `web`·`batch`는 그 서비스만 |
| source_sha | Backend의 전체 40자리 commit SHA. 기본값 없음. ECR에서 digest를 확인해 고정 |
| task_definition | `memme-backend-v2:16`, `memme-backend-batch-v2:7`처럼 선택한 대상의 정확한 revision. 최신 이미지 재배포를 사용하지 않음 |

`BACKEND_ECS_CD_ENABLED`는 운영 이미지의 Redis 세션·DB 풀 보완이 Backend `dev`에 머지되고 CI 이미지가 게시된 뒤에 켠다. 그 전에 CI 이미지를 배포하면 보완이 빠진다.

정상 배포는 현재 태스크·ALB·업무 응답 확인 → 정상 revision 기록 → 이미지 digest 확인 → 새 revision 등록 → 서비스 갱신 → 태스크 2개와 ALB healthy 2개 확인 → 업무 응답 확인 순서다. 실패 시 Actions artifact의 `rollback_task_definition`을 확인한 뒤 rollback을 실행한다. Container health 성공만으로 업무 기능 성공을 판단하지 않는다. `previous_task_definition`은 실행 전 revision이며 정상 여부를 보장하지 않는다. `rollback_task_definition`은 업무 응답까지 검증한 복구 기준에만 기록한다. 복구 실행이 실패하면 최초 배포 결과의 정상 revision을 기준으로 다시 판단한다.

```sh
# 웹을 배포하고, 통과하면 같은 SHA로 배치를 배포
python3 deploy/ecs/deploy_backend.py deploy --target all --source-sha <40자리 SHA>
# 이전 검증에서 기록한 정상 revision으로 대상별 복구
python3 deploy/ecs/deploy_backend.py rollback --target web --task-definition memme-backend-v2:16
python3 deploy/ecs/deploy_backend.py rollback --target batch --task-definition memme-backend-batch-v2:7
```

웹은 서비스의 desired=2, rolling=100/200, circuit-breaker rollback, ALB·Cloud Map 연결을 확인한다. 서비스 갱신은 taskDefinition만 전달한다. Secrets·네트워크·운영 AI 주소는 변경하지 않으며, ECS 웹 태스크의 스케줄러와 QA 시딩은 계속 비활성화한다. `cd-backend` concurrency로 Backend 배포를 한 번에 하나만 실행한다.

## 배치

배치는 스케줄러 5개를 단독으로 실행한다. 웹 태스크는 스케줄러가 비활성(`-`)이어야 하고, 배치는 두 개가 동시에 돌면 같은 작업이 두 번 실행된다.

- 서비스가 desired=1, 0/100, ALB·Cloud Map 미등록이 아니면 변경 전에 중단한다. 0/100이면 ECS가 기존 태스크를 멈춘 뒤 새 태스크를 시작한다.
- ALB가 없으므로 업무 응답 검사 대신 태스크 1개가 새 revision·digest로 RUNNING이고, health check가 정의되어 있으면 HEALTHY인지 확인한다.
- 웹과 같은 런타임 역할을 사용한다. 컨테이너 이름과 웹 전용 환경변수 검사는 적용하지 않는다.
- 첫 배포 전에 실제 서비스의 deploymentConfiguration과 health check 유무를 읽기 전용으로 확인한다. 2026-10-20 기준 미확인이다.

## 별도 ECS 배포 권한

`GitHubActionsBackendECSDeployRole`은 기존 IaC 관리 역할을 수정하지 않고 별도로 구성한다. `trust-policy.json`은 현재 Cloud 배포 역할의 production/main OIDC 조건을 복사한 값이다. `deploy-policy.json`은 Backend 웹·배치 task family 등록과 두 서비스 갱신, 지정한 런타임 역할 2개 PassRole, 이미지·상태 조회를 허용한다. ECS 태스크 중지와 네트워크·Secrets·IAM 변경 권한은 포함하지 않는다.

`smoke-document.json`으로 `MemmeECSBackendSmoke` Command 문서 version 2을 생성한다. 배포 역할은 이 고정 문서만 기존 허용 대상인 AI EC2에서 실행한다. 임의 shell 명령은 입력받지 않는다. 문서 자체 변경은 배포 역할에서 허용하지 않는다.

public 검사는 https://api.memme.kr의 health·CSRF·미인증 응답·내부 API 차단·CORS를 확인한다. private 검사는 AI 서버에서 `backend.memme.internal`의 기존 QA 매출 fixture를 조회한다. 모두 읽기 작업이며 인증 정보·응답 본문은 로그에 남기지 않는다. 로그인·S3·AI·SSE 전체 기능 검증을 대신하지 않으며, 이 항목들은 별도 기능 검증 및 배포 교체 중 검증 결과와 함께 판단한다.

## 검증 시 주의

현재 로그인 세션은 태스크 메모리에 저장된다. 태스크 교체 시 기존 세션이 사라질 수 있고, SSE는 재연결이 필요할 수 있다. 배포·복구 검증 결과에서 오류 수·재로그인·재연결 여부를 기록한 뒤 운영 전환 조건을 결정한다. 운영 트래픽은 검증 동안 기존 EC2로 유지한다.
