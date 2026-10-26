# V2 모니터링 (PLG + CloudWatch)

V2 운영 환경의 지표·로그·알림 구성입니다. 2026-10-22 운영 모니터링 서버(`/opt/monitoring`)의 설정 파일과 대조해 반영했습니다.

## 구성

```
팀원 브라우저 ─ grafana.memme.kr ─ Cloudflare Access(허용 이메일) ─┐
RunPod GPU Pod(Alloy) ─ ingest.memme.kr(Access 서비스 토큰) ───────┤ Cloudflare Tunnel (서버 → 바깥 연결만)
                                                                   ▼
┌──────────── 모니터링 EC2 (t3.small, public 서브넷, 인바운드는 VPC 내부 수집 포트만) ────────────┐
│ cloudflared ─ Grafana ─┬─ Prometheus (15일)  ← AI 서버 Alloy, node_exporter, mysqld_exporter, ProxySQL │
│                        ├─ Loki (14일)        ← AI 서버 Alloy, GPU Pod Alloy                          │
│                        └─ CloudWatch 데이터소스 (ALB·ECS·EC2·Redis 지표, Backend 로그)                 │
└──────────────────────────────────────────────────────────────────────────────────────┘
알림: Grafana 규칙 37개 → Discord / CloudWatch 알람 4개 → SNS → 이메일 (모니터링 서버 장애 대비 백업)
```

## 디렉터리

| 경로 | 내용 |
|---|---|
| `server/` | 모니터링 서버 `/opt/monitoring`에 그대로 두는 파일. compose, Prometheus, Loki, Grafana 프로비저닝(데이터소스, Discord 연락처, 알림 규칙 15개) |
| `alerting-api/gpu-rules.yaml` | Grafana API로 만든 GPU 알림 4개의 기록본(서버 프로비저닝 폴더에 넣지 않음) |
| `alerting-api/aws-rules.yaml` | Grafana API로 만든 AWS 지표(ALB·Redis·EC2) 알림 9개의 요약 기록본 |
| `dashboards/` | Grafana 대시보드 5개: 서비스 개요, BE 앱, AI 서버, DB, GPU. 모두 배포(파랑)·비정상 태스크 중지(빨강) 표시 포함 |
| `alloy/ai-server.alloy` | AI EC2의 `memme-alloy` 컨테이너 설정 (`/opt/alloy/config.alloy`) |
| `alloy/gpu-pod/` | RunPod Pod 수집기 설정·시작 스크립트·AI팀 안내 |
| `cloudwatch/` | CloudWatch 알람·SNS·ECS 중지 이벤트 초기 생성 스크립트 (CloudShell 실행). 2026-10-22 정리 후 알람 4개만 남기고 ECS 중지 이벤트는 삭제했습니다 |
| `ec2/` | 모니터링 EC2 생성 스크립트와 부팅 스크립트, ECS 조회 권한(`ecs-read-policy.json`) |
| `server/ecs-discovery/` | BE ECS 태스크 위치를 Prometheus 대상 파일로 쓰고 배포·태스크 중지를 Grafana 표시로 남기는 스크립트 |

## 수집 대상

| 대상 | 방식 | 저장 |
|---|---|---|
| ALB, ECS, EC2 상태, Redis | AWS 기본 지표 | CloudWatch (Grafana가 직접 조회) |
| Backend 로그 | ECS awslogs `/ecs/memme/backend-v2` | CloudWatch Logs |
| Backend 앱 지표 (API별 지연·오류, DB 연결 풀, Tomcat 스레드, JVM) | Spring Boot Actuator 관리 포트 `8081/actuator/prometheus`(ALB 미연결, 모니터링 SG만 허용). 대상은 `ecs-discovery`가 30초마다 ECS API로 갱신 | Prometheus |
| 배포·태스크 중지 | `ecs-discovery`가 ECS 배포 시작·완료(리비전, 소스 SHA)와 정상 롤링 외 태스크 중지(사유, 종료 코드)를 Grafana 표시로 기록 | Grafana |
| AI 서버 컨테이너 로그·호스트 지표 | AI EC2 `memme-alloy` (서명 URL·토큰 마스킹) | Loki, Prometheus |
| MySQL Primary·Replica | 모니터링 서버 `mysqld-exporter`가 TLS(CA 검증)로 접속, 계정 `memme_monitor@10.0.1.8` | Prometheus |
| ProxySQL | 제어 서버 내장 지표 `:6070/metrics` | Prometheus |
| DB·제어·모니터링 서버 디스크·메모리 | node_exporter 1.9.1 (DB·제어 서버는 systemd, 모니터링 서버는 컨테이너) | Prometheus |
| GPU(A40)·vLLM | Pod 안 Alloy → `ingest.memme.kr` push | Prometheus, Loki |

## 알림

| 영역 | Grafana 규칙 (Discord) |
|---|---|
| ECS | 웹 태스크 부족, 배치 태스크 없음, 웹 CPU·메모리 |
| BE 앱 | 일반 API 1초 99%, 무거운 작업 3초 95%의 빠른(1시간)/느린(6시간) 소진, AI 생성 실패율, 5xx 비율(스캐너 제외), DB 연결 대기 2분, 요청 스레드 80% 이상. BE 지표 배포 전에는 데이터 없음으로 정상 |
| DB | 접속 실패, 쓰기 가능 DB 수 ≠ 1, 복제 중지, 복제 지연 30초, 연결 사용률 |
| ProxySQL | 수집 실패, 쓰기 hostgroup ONLINE 0개, 연결 한도 초과 거부 |
| 서버 | 디스크, 메모리, 지표 수집 중단 |
| GPU | 수집 중단, 온도 85℃, vLLM 대기열 적체, vLLM 요청 거부 |
| AWS | ALB 정상 웹 서버 2개 미만·0개, ALB·백엔드 5xx 비율(1시간 5%), 응답 지연 오류 예산 빠른·느린 소진(SLO 요청 95% 3초 안), Redis 메모리·eviction, EC2 상태 검사(인스턴스별) |

Discord가 기본 경로입니다. CloudWatch 이메일 알람은 모니터링 서버가 멈춰도 알 수 있도록 서비스 전체 중단, DB .185·.65 상태 검사, 모니터링 서버 상태 검사 4개만 남겼습니다. 배포 때마다 오던 ECS 태스크 중지 메일은 삭제했습니다. 기준값은 임시값이며 운영 데이터를 보고 조정합니다.

## 비밀값

저장소에는 비밀값을 넣지 않습니다. 서버의 `/opt/monitoring/.env`(600)와 아래 위치에만 있습니다.

| 값 | 위치 |
|---|---|
| Cloudflare Tunnel 토큰 | SSM `/memme/v2/monitoring/cloudflared-token` |
| Discord 웹훅 | SSM `/memme/v2/monitoring/discord-webhook` |
| MySQL 모니터링 계정 비밀번호 | SSM `/memme/v2/monitoring/mysql-monitor-password` → `mysqld-exporter.cnf`(600, nobody) |
| GPU Pod 서비스 토큰 | SSM 2개, RunPod Secrets |
| Grafana 관리자 비밀번호 | 서버에서 생성, `.env`에만 저장 |

`server/.env.example`에 필요한 변수를 적어 두었습니다. 저장소의 `GF_AUTH_JWT_ROLE_ATTRIBUTE_PATH`는 관리자 이메일을 `GRAFANA_ADMIN_EMAIL` 변수로 바꿔 두었습니다(운영 서버는 이메일을 직접 적은 상태).

## 서버 재구성

1. `ec2/launch-monitoring-ec2.sh`로 EC2를 만듭니다(역할 `memme-v2-monitoring-role`: SSM, CloudWatch 읽기). SSM 엔드포인트 SG에 모니터링 SG 443 허용이 필요합니다.
2. `server/`를 `/opt/monitoring`에 복사하고 `.env`를 채웁니다. Parameter Store 값은 서버에서 `amazon/aws-cli` 컨테이너로 읽어 화면에 출력하지 않습니다.
3. `mysqld-exporter.cnf`를 만들고(`[client] user=memme_monitor`, `password=`, `ssl-ca=/cfg/ca.pem`), 공개 CA를 `mysql-ca.pem`으로 둡니다.
4. `docker compose up -d` 후 대시보드 4개를 Grafana에 가져오고(Import), `alerting-api/`의 GPU·AWS 규칙을 다시 만듭니다.
5. Prometheus 설정을 바꾼 뒤에는 `curl -X POST localhost:9090/-/reload`, 알림·데이터소스 파일을 바꾼 뒤에는 `docker compose up -d --force-recreate grafana`를 실행합니다.

## 남은 일

- Backend 로그 Loki 수집 (Backend 배포 시 FireLens 추가)
- Backend·AI `request_id` 연결
- ProxySQL hostgroup 20 SHUNNED: 쿼리 규칙이 없어 서비스 영향이 없으므로 알림에서 제외했습니다. 1-C 자동 전환 재시험 전에 정리합니다
- 모니터링 서버·수집 구성의 Terraform 반영
