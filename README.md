# KTB4-7th-Cloud

맴매 서비스의 V1 인프라 운영 및 Backend·AI 배포 구성을 관리하는 Repository입니다.

## Structure

```text
.github/
└── workflows/
    └── deploy.yml                  # Backend·AI 공통 수동 CD (GitHub OIDC → AWS SSM)

deploy/                             # 서비스별 운영 배포 설정
├── backend/
│   ├── compose.yaml                # Backend Blue/Green 컨테이너 및 Nginx
│   ├── deploy.sh                   # Backend 배포 진입점
│   ├── .runtime.env.example        # 런타임 환경변수 예시
│   ├── nginx/
│   │   ├── nginx.conf              # HTTPS·내부 API·CORS 프록시 설정
│   │   └── upstream.default.conf   # 최초 배포용 기본 upstream
│   ├── renew-cert.sh               # Let's Encrypt 인증서 갱신 및 Nginx reload
│   └── systemd/
│       ├── memme-cert-renew.service # 인증서 갱신 실행 서비스
│       └── memme-cert-renew.timer   # 매일 갱신 여부 확인
├── ai/
│   ├── compose.yaml                # AI Blue/Green 컨테이너 및 Nginx
│   ├── deploy.sh                   # AI 배포 진입점
│   ├── .runtime.env.example        # 런타임 환경변수 예시
│   └── nginx/
│       ├── nginx.conf              # AI 요청 프록시 설정
│       └── upstream.default.conf   # 최초 배포용 기본 upstream
├── lib/
│   └── deploy-blue-green.sh        # Secret 주입·이미지 pull·헬스체크·트래픽 전환
└── frontend/                       # 폴더만 확보 (.gitkeep), 배포 설정 미구현

docs/
└── CD.md                           # CD 실행·환경변수·IAM·HTTPS 운영 가이드

terraform/                          # 폴더만 확보 (.gitkeep), IaC 추후 도입 예정
README.md
```

실제 비밀값과 배포 상태는 Git에 저장하지 않습니다. 배포 시 각 EC2에서 `.runtime.env`, Backend의 `.runtime.nginx.conf`, `runtime/` 디렉터리가 생성되며 `.gitignore`로 제외됩니다. `runtime/`에는 활성 색상, Nginx upstream, 현재 배포 기록(`current-deployment.json`)이 저장됩니다.

## V1 운영 구성

| 구성 요소 | 역할 |
| --- | --- |
| Cloudflare Workers Static Assets | Frontend 정적 파일 제공 (`https://memme.kr`) |
| Backend EC2 | Nginx HTTPS 프록시 및 Spring Boot Blue/Green 컨테이너 (`https://api.memme.kr`) |
| AI EC2 | Nginx 및 AI Blue/Green 컨테이너, 8000 포트는 Backend 보안 그룹에서만 접근 |
| RDS MySQL | 애플리케이션 데이터 저장, 사설 네트워크 접근 |
| S3 | 매출 업로드 원본 파일 저장 |
| ECR | CI에서 빌드한 Backend·AI Docker 이미지 저장 |
| Secrets Manager | 서비스별 운영 환경변수·비밀값 보관, EC2에서 런타임 주입 |
| GitHub Actions·SSM | OIDC 인증 후 EC2에서 배포 명령 실행 |

Backend·AI는 각각 EC2 한 대에서 Blue/Green 컨테이너를 운영합니다. 같은 호스트 안에서 트래픽을 전환하므로 호스트 장애까지 대비하는 이중화 구성은 아닙니다.

## CI / CD

1. **애플리케이션 Repository — CI**: Backend·AI의 `dev` 대상 PR에서 테스트·빌드를 실행합니다. `dev` 병합 후에는 Docker 빌드·컨테이너 헬스체크를 거쳐 전체 commit SHA 태그로 ECR에 이미지를 발행합니다.
2. **Cloud Repository — 수동 CD**: Actions의 `Deploy service`에서 `main` 브랜치와 서비스(`backend` / `ai`), 성공한 CI의 `image_digest`, `commit_sha`를 입력합니다. CI 성공만으로 운영에 자동 배포되지는 않습니다.
3. **EC2 배포**: GitHub OIDC 인증 → ECR digest 확인 → SSM 명령 실행 → Secret 주입 → 반대 색상 컨테이너 실행 → 헬스체크 → Nginx upstream 전환 순서로 진행합니다. 후보 컨테이너가 실패하면 기존 트래픽을 유지하고, 전환 검증이 실패하면 이전 upstream으로 복구합니다.
4. **배포 기록**: GitHub Actions 요약과 EC2의 `runtime/current-deployment.json`에서 소스 SHA·이미지 digest·활성 색상·배포 결과를 확인합니다.

Frontend는 현재 Cloudflare에 별도로 수동 배포하며, 이 저장소에는 Frontend 자동 배포 워크플로가 없습니다.

자세한 실행 절차와 필요한 설정은 [CD 운영 가이드](docs/CD.md)를 참고하세요.
