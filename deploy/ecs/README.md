# Backend ECS 수동 배포와 복구

기존 EC2 CD와 V1 Terraform은 유지한다. 이 경로는 `memme-v2/memme-backend-v2`만 변경하며, 운영 DNS 전환은 포함하지 않는다.

GitHub Actions의 **Deploy Backend ECS**를 main에서 수동 실행한다.

| 입력 | 의미 |
| --- | --- |
| mode=deploy | Backend CI가 이미 올린 이미지로 정상 배포 |
| source_sha | Backend의 전체 40자리 commit SHA. ECR에서 digest를 확인해 고정 |
| mode=rollback | 기록해 둔 정상 task definition으로 복구 |
| task_definition | `memme-backend-v2:3`처럼 정확한 revision. 최신 이미지 재배포를 사용하지 않음 |

정상 배포는 현재 태스크·ALB·업무 응답 확인 → 정상 revision 기록 → 이미지 digest 확인 → 새 revision 등록 → 서비스 갱신 → 태스크 2개와 ALB healthy 2개 확인 → 업무 응답 확인 순서다. 실패 시 Actions artifact의 `rollback_task_definition`을 확인한 뒤 rollback을 실행한다. Container health 성공만으로 업무 기능 성공을 판단하지 않는다. `previous_task_definition`은 실행 전 revision이며 정상 여부를 보장하지 않는다. `rollback_task_definition`은 업무 응답까지 검증한 복구 기준에만 기록한다. 복구 실행이 실패하면 최초 배포 결과의 정상 revision을 기준으로 다시 판단한다.

```sh
# 명시한 소스 commit의 이미지를 배포
python3 deploy/ecs/deploy_backend.py deploy --source-sha 2ba823ded25a10e5b58d144cfca4be4916105ab5
# 이전 검증에서 기록한 정상 revision으로 복구
python3 deploy/ecs/deploy_backend.py rollback --task-definition memme-backend-v2:3
```

서비스의 desired=2, rolling=100/150, circuit-breaker rollback, ALB·Cloud Map 연결을 확인한다. 서비스 갱신은 taskDefinition만 전달한다. Secrets·네트워크·운영 AI 주소는 변경하지 않으며, ECS 웹 태스크의 스케줄러와 QA 시딩은 계속 비활성화한다. 기존 EC2 Backend 배포와 `cd-backend` concurrency를 공유한다.

## 별도 ECS 배포 권한

`GitHubActionsBackendECSDeployRole`은 기존 IaC 관리 역할을 수정하지 않고 별도로 구성한다. `trust-policy.json`은 현재 Cloud 배포 역할의 production/main OIDC 조건을 복사한 값이다. `deploy-policy.json`은 Backend task family·서비스 갱신, 지정한 런타임 역할 2개 PassRole, 이미지·상태 조회를 허용한다. ECS 태스크 중지와 네트워크·Secrets·IAM 변경 권한은 포함하지 않는다.

`smoke-document.json`으로 `MemmeECSBackendSmoke` Command 문서 version 1을 생성한다. 배포 역할은 이 고정 문서만 기존 Backend/AI EC2 두 곳에서 실행할 수 있다. 임의 shell 명령은 입력받지 않는다. 문서 자체 변경은 배포 역할에서 허용하지 않는다.

public 검사는 ECS ALB의 health·CSRF·미인증 응답·내부 API 차단·CORS를 확인한다. private 검사는 AI 서버에서 `backend.memme.internal`의 기존 QA 매출 fixture를 조회한다. 모두 읽기 작업이며 인증 정보·응답 본문은 로그에 남기지 않는다. 로그인·S3·AI·SSE 전체 기능 검증을 대신하지 않으며, 이 항목들은 별도 기능 검증 및 배포 교체 중 검증 결과와 함께 판단한다.

## 검증 시 주의

현재 로그인 세션은 태스크 메모리에 저장된다. 태스크 교체 시 기존 세션이 사라질 수 있고, SSE는 재연결이 필요할 수 있다. 배포·복구 검증 결과에서 오류 수·재로그인·재연결 여부를 기록한 뒤 운영 전환 조건을 결정한다. 운영 트래픽은 검증 동안 기존 EC2로 유지한다.
