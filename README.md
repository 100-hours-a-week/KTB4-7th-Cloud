# KTB4-7th-Cloud

맴매 서비스의 인프라 및 배포 구성을 관리하는 Repository

## Structure

```text
deploy/              # 서비스별 운영 배포 설정
├── frontend/        # Frontend 배포 설정
├── backend/
│   ├── compose.yaml # Backend 운영 배포용 Docker Compose
│   ├── deploy.sh    # 배포 스크립트
│   └── nginx/       # Nginx 설정
└── ai/
    ├── compose.yaml # AI 운영 배포용 Docker Compose
    └── deploy.sh    # 배포 스크립트

terraform/           # AWS 인프라 IaC (추후 도입 예정)

.github/
└── workflows/
    ├── deploy-frontend.yml
    ├── deploy-backend.yml
    └── deploy-ai.yml
```

- 각 애플리케이션 Repository: CI 관리
- Cloud Repository: 배포 설정 및 CD Workflow 관리