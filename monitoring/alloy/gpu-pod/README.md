# RunPod GPU Pod 관측 설정 (AI팀 적용 안내)

vLLM `/metrics`, nvidia-smi GPU 수치, vLLM 로그를 클라우드팀 모니터링(grafana.memme.kr)으로 보내는 설정입니다. 수집기는 Grafana Alloy v1.5.1이며, 처음 기동할 때 GitHub 공식 릴리스를 받아 sha256을 검증합니다.

## 파일

| 파일 | 내용 |
|---|---|
| `start-observability.sh` | GPU 수치 기록 루프와 Alloy를 백그라운드로 띄우고 바로 끝납니다. 실패해도 vLLM 기동을 막지 않습니다 |
| `config.alloy` | 수집·전송 설정. 토큰은 환경변수로만 읽습니다 |

## 적용 순서

1. Pod 볼륨에 두 파일을 복사합니다.
   ```bash
   scp -P <ssh-port> -i ~/.ssh/id_ed25519 start-observability.sh config.alloy root@<pod-ip>:/workspace/memme-obs/
   ```
2. RunPod → Secrets에 `memme_cf_client_id`, `memme_cf_client_secret`을 등록합니다. 값은 클라우드팀이 따로 전달합니다.
3. Pod(또는 템플릿)의 Environment Variables에 아래를 추가합니다.
   | 이름 | 값 |
   |---|---|
   | `CF_ACCESS_CLIENT_ID` | `{{ RUNPOD_SECRET_memme_cf_client_id }}` |
   | `CF_ACCESS_CLIENT_SECRET` | `{{ RUNPOD_SECRET_memme_cf_client_secret }}` |
4. Container Start Command에서 **기존 watchdog 실행 앞에 한 줄만 추가**합니다. vLLM·watchdog 구조와 로그 파일은 그대로 둡니다.
   ```bash
   bash -c "/start.sh & MEMME_OBS_LOG_FILE=/root/vllm_serve.log bash /workspace/memme-obs/start-observability.sh; <기존 watchdog 실행 그대로>"
   ```
   - `MEMME_OBS_LOG_FILE`: 수집할 vLLM 로그 파일 경로입니다. 지정하지 않으면 `/tmp/memme-obs/logs/vllm.log`를 씁니다. 경로 제약은 없습니다.
   - 지정한 파일은 **읽기만 하고 비우거나 회전하지 않습니다.** 크기 관리는 기존 방식대로 해 주세요.
   - 처음 보는 파일은 끝에서부터 읽습니다. 기존에 쌓인 로그는 보내지 않고, 기동 이후 새로 쓰인 줄만 보냅니다.
   - 이미 실행 중이면 다시 띄우지 않으므로, 실수로 두 번 실행해도 수집기는 하나만 돕니다. watchdog 루프 **안**이 아니라 Pod 시작 때 한 번 실행되는 위치에 두면 됩니다.
5. Pod를 재시작한 뒤 확인합니다.
   ```bash
   tail /tmp/memme-obs/observability.log
   cat /tmp/memme-obs/textfile/gpu.prom
   ```
   `Alloy v1.5.1 기동` 줄이 보이고, 이후 오류가 반복되지 않으면 정상입니다. 수신 확인은 클라우드팀이 Grafana에서 합니다.

## 확인 부탁

- **프롬프트 로그:** 사용 중인 vLLM 버전이 요청마다 `Received request ... prompt: ...`를 남기는지 확인해 주세요. 남긴다면 `--disable-log-requests`를 추가해 주세요(최신 버전은 기본으로 꺼져 있습니다). 수집기에서도 해당 줄을 한 번 더 버리도록 설정했습니다.
- **`/metrics` 공개 여부:** 공개 proxy URL로 `/metrics`가 인증 없이 열리는지 확인해 주세요. 수집은 localhost에서만 하므로 외부에 열 필요는 없습니다.

## 자원 사용과 동작

| 항목 | 값 |
|---|---|
| Alloy 메모리 | 로컬 시험에서 약 240MB(amd64 에뮬레이션 기준이며 실제는 더 작을 수 있습니다) |
| 디스크 | Alloy 바이너리 약 300MB를 `/workspace/memme-obs/cache`에 저장하고 재시작 때 다시 씁니다 |
| 네트워크 | 15초마다 지표 전송, 로그는 생길 때 전송. HTTPS(443) 아웃바운드만 사용합니다 |
| vLLM 로그 파일 | 기본 경로(`/tmp/memme-obs/logs/vllm.log`)일 때만 100MB를 넘으면 비웁니다. `MEMME_OBS_LOG_FILE`로 지정한 파일은 건드리지 않습니다 |
| 토큰이 없을 때 | 수집을 시작하지 않고 종료 코드 0으로 끝납니다 (vLLM은 정상 기동) |

## 끄기

- Start Command에서 `bash /workspace/memme-obs/start-observability.sh;`를 빼고 재시작합니다.
- 실행 중에 바로 멈추려면 `pkill -f start-observability.sh; pkill -f alloy-v1.5.1`을 실행합니다. 재시작 루프를 먼저 끄고 Alloy를 멈추는 순서입니다.
