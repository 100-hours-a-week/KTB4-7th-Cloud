# Terraform

기존 Memme 운영 AWS 자원을 관리하는 Terraform 코드입니다.

## 구성

| 실행 폴더 | 관리 대상 | 원격 state key |
|---|---|---|
| `environments/prod` | EC2, RDS, S3, 네트워크, IAM 등 기존 자원 | `memme/prod/terraform.tfstate` |
| `bootstrap` | 전용 state S3 버킷과 관련 설정 | `memme/bootstrap/terraform.tfstate` |

운영 코드는 관리 영역별 파일로 나눴습니다. `imports.tf`는 기존 자원의 연결 기록이고, `backend.tf`는 이미 구성한 S3 원격 state를 사용합니다. 두 실행 폴더의 `.terraform.lock.hcl`을 함께 관리합니다.

state 저장소는 암호화, 버전 관리, 공개 차단, HTTPS 강제 정책과 S3 lockfile을 사용합니다. state는 Git에 포함하지 않습니다. 코드에는 Secret 값, DB 데이터와 S3 업로드 파일이 없습니다.

## 실행

AWS 계정에 인증한 뒤 **저장소 루트**에서 실행합니다. 해당 자원과 원격 state에 접근할 권한이 필요합니다. Terraform은 1.14 이상, 2.0 미만을 사용하며 AWS provider는 6.67.0으로 고정했습니다.

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

모든 자원에 `prevent_destroy=true`가 있으나 resource 구문을 삭제하면 이 보호도 사라집니다. RDS 삭제 보호와 S3의 `force_destroy=false`도 유지하며, 변경 작업마다 plan을 확인합니다.

## 범위

현재 운영 환경을 관리하는 코드입니다. Cloudflare와 서버 내부 Docker, Nginx, CloudWatch Agent 설정은 별도로 관리합니다. 일부 기존 자원 ID를 참조하므로 새로운 환경을 만들 때는 참조를 정리해야 합니다. RDS에서 EC2 MySQL로의 데이터 이전과 ECS 또는 Auto Scaling 구성은 아직 포함하지 않았습니다.
