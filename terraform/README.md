# Terraform

기존 Memme 운영 AWS 자원을 관리하는 Terraform 코드입니다.

## 구성

| 실행 폴더 | 관리 대상 | 원격 state key |
|---|---|---|
| `environments/prod` | EC2, RDS, S3, 네트워크, IAM 등 기존 자원 | `memme/prod/terraform.tfstate` |
| `bootstrap` | 전용 state S3 버킷과 관련 설정 | `memme/bootstrap/terraform.tfstate` |

## 실행

AWS 계정에 인증한 뒤 **저장소 루트**에서 실행합니다. 

```sh
terraform -chdir=terraform/environments/prod init
terraform -chdir=terraform/environments/prod fmt -check
terraform -chdir=terraform/environments/prod validate
terraform -chdir=terraform/environments/prod state list
terraform -chdir=terraform/environments/prod plan -out=change.tfplan
```

plan의 생성, 수정, 삭제 대상을 검토한 뒤 저장한 계획을 적용합니다.

```sh
terraform -chdir=terraform/environments/prod apply change.tfplan
```

이미 import한 자원은 다시 연결하지 않습니다. 별도의 로컬 state를 만들지 않고 기존 S3 backend를 사용합니다. 앱 배포는 기존 CI/CD를 사용합니다.


## 범위

현재 운영 환경을 관리하는 코드입니다. Cloudflare와 서버 내부 Docker, Nginx, CloudWatch Agent 설정은 별도로 관리합니다. 일부 기존 자원 ID를 참조하므로 새로운 환경을 만들 때는 참조를 정리해야 합니다. RDS에서 EC2 MySQL로의 데이터 이전과 ECS 또는 Auto Scaling 구성은 아직 포함하지 않았습니다.

## V1 Backend 정리 (2026-10-13)

운영 Backend를 ECS로 전환한 뒤 사용하지 않는 V1 Backend EC2와 고정 IP를 삭제했습니다. 해당 resource, import, output 및 배포 IAM 정책의 이전 EC2 참조를 제거했습니다. 원격 state에서는 `aws_instance.backend_server`와 `aws_eip.eipalloc_0abbf41bc8c1db381`만 제거합니다. AI, RDS와 나머지 자원은 유지합니다. 과거 checkout으로 Terraform을 실행하지 말고 이 변경이 반영된 코드를 사용하세요.
