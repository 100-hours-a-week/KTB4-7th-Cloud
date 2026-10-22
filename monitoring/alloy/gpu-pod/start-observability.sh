#!/usr/bin/env bash
# memme-v2 RunPod GPU Pod 관측 시작 스크립트
# - nvidia-smi 수치를 15초마다 textfile(.prom)로 기록
# - Grafana Alloy로 vLLM /metrics·GPU 수치·vLLM 로그를 모니터링 서버에 전송
# - 모든 작업은 백그라운드로 띄우고 바로 끝난다. 실패해도 vLLM 기동을 막지 않는다
#
# 필요 환경변수 (RunPod 시크릿으로 주입): CF_ACCESS_CLIENT_ID, CF_ACCESS_CLIENT_SECRET
# 선택 환경변수: MEMME_OBS_LOG_FILE  수집할 vLLM 로그 파일 (기본 /tmp/memme-obs/logs/vllm.log)
#                                   기본 경로가 아니면 파일 크기 관리는 하지 않는다 (기존 운영 파일은 건드리지 않음)
# 이미 실행 중이면 다시 띄우지 않으므로, vLLM watchdog 루프 밖에서 Pod 시작 때 한 번 실행하면 된다
# 사용 예 (Container Start Command, watchdog 구조는 그대로 두고 앞에 한 줄 추가):
#   bash -c "/start.sh & MEMME_OBS_LOG_FILE=/root/vllm_serve.log bash /workspace/memme-obs/start-observability.sh; <기존 watchdog 실행>"

set -u

ALLOY_VERSION="v1.5.1"
ALLOY_ZIP_SHA256="c324374c3aa9c1220b50ede6b61df7e47c02979111201195faf6338909512ae4"
ALLOY_URL="https://github.com/grafana/alloy/releases/download/${ALLOY_VERSION}/alloy-linux-amd64.zip"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_DIR="${MEMME_OBS_CACHE_DIR:-/workspace/memme-obs/cache}"   # Pod 볼륨: 재시작 때 다시 받지 않도록
RUN_DIR="${MEMME_OBS_RUN_DIR:-/tmp/memme-obs}"

export MEMME_INGEST_URL="${MEMME_INGEST_URL:-https://ingest.memme.kr}"
export VLLM_METRICS_ADDR="${VLLM_METRICS_ADDR:-localhost:8000}"
export MEMME_OBS_TEXTFILE_DIR="${RUN_DIR}/textfile"
DEFAULT_LOG_FILE="${RUN_DIR}/logs/vllm.log"
export MEMME_OBS_LOG_FILE="${MEMME_OBS_LOG_FILE:-$DEFAULT_LOG_FILE}"
export RUNPOD_POD_ID="${RUNPOD_POD_ID:-unknown}"

LOG_MAX_BYTES=$((100 * 1024 * 1024))   # 기본 로그 파일 상한. 넘으면 비운다 (Alloy가 이미 보낸 내용)
OBS_LOG="${RUN_DIR}/observability.log"
LOCK_FILE="${RUN_DIR}/observability.lock"

mkdir -p "$CACHE_DIR" "$MEMME_OBS_TEXTFILE_DIR" "$(dirname "$MEMME_OBS_LOG_FILE")"
touch "$MEMME_OBS_LOG_FILE"

log() { echo "$(date -u +%FT%TZ) [memme-obs] $*" | tee -a "$OBS_LOG" >&2; }   # stdout은 함수 반환값용

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  else python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; fi
}

download() {
  if command -v curl >/dev/null 2>&1; then curl -fsSL --retry 3 -o "$2" "$1"
  elif command -v wget >/dev/null 2>&1; then wget -q -O "$2" "$1"
  else python3 -c 'import urllib.request,sys; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' "$1" "$2"; fi
}

install_alloy() {
  local bin="${CACHE_DIR}/alloy-${ALLOY_VERSION}"
  if [ -x "$bin" ]; then echo "$bin"; return 0; fi
  local zip="${CACHE_DIR}/alloy-${ALLOY_VERSION}.zip"
  download "$ALLOY_URL" "$zip" || { log "Alloy 내려받기 실패"; return 1; }
  if [ "$(sha256_of "$zip")" != "$ALLOY_ZIP_SHA256" ]; then
    log "Alloy sha256 불일치, 삭제"; rm -f "$zip"; return 1
  fi
  python3 -c 'import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extract("alloy-linux-amd64", sys.argv[2])' "$zip" "$CACHE_DIR" \
    && mv "${CACHE_DIR}/alloy-linux-amd64" "$bin" && chmod 0755 "$bin" && rm -f "$zip" \
    || { log "Alloy 압축 해제 실패"; return 1; }
  echo "$bin"
}

# nvidia-smi → Prometheus textfile. 실패하면 memme_gpu_up 0
gpu_loop() {
  local out="${MEMME_OBS_TEXTFILE_DIR}/gpu.prom"
  while true; do
    local tmp="${out}.$$"
    {
      echo "# HELP memme_gpu_up nvidia-smi 조회 성공 여부"
      echo "# TYPE memme_gpu_up gauge"
      if q=$(nvidia-smi --query-gpu=index,uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw,power.limit,clocks.sm,clocks.mem \
               --format=csv,noheader,nounits 2>/dev/null) && [ -n "$q" ]; then
        echo "memme_gpu_up 1"
        echo "$q" | awk -F', *' '
          function num(v) { return (v ~ /^[0-9.]+$/) }
          function m(name, v, scale) { if (num(v)) printf "%s{%s} %s\n", name, l, v * scale }
          {
            gsub(/"/, "", $3)
            l = sprintf("gpu=\"%s\",uuid=\"%s\",name=\"%s\"", $1, $2, $3)
            m("memme_gpu_utilization_percent", $4, 1)
            m("memme_gpu_memory_utilization_percent", $5, 1)
            m("memme_gpu_memory_used_bytes", $6, 1048576)
            m("memme_gpu_memory_total_bytes", $7, 1048576)
            m("memme_gpu_temperature_celsius", $8, 1)
            m("memme_gpu_power_draw_watts", $9, 1)
            m("memme_gpu_power_limit_watts", $10, 1)
            m("memme_gpu_sm_clock_mhz", $11, 1)
            m("memme_gpu_memory_clock_mhz", $12, 1)
          }'
      else
        echo "memme_gpu_up 0"
      fi
    } > "$tmp" && mv -f "$tmp" "$out"

    # 기본 경로의 vLLM 로그만 크기 관리 (tee -a로 쓰므로 비워도 이어서 기록된다)
    if [ "$MEMME_OBS_LOG_FILE" = "$DEFAULT_LOG_FILE" ] \
       && [ "$(stat -c %s "$MEMME_OBS_LOG_FILE" 2>/dev/null || echo 0)" -gt "$LOG_MAX_BYTES" ]; then
      : > "$MEMME_OBS_LOG_FILE"
    fi
    sleep 15
  done
}

alloy_loop() {
  local bin="$1"
  while true; do
    "$bin" run "${SCRIPT_DIR}/config.alloy" \
      --storage.path="${RUN_DIR}/alloy-data" \
      --server.http.listen-addr=127.0.0.1:12345 \
      --disable-reporting >> "$OBS_LOG" 2>&1
    log "Alloy 종료(코드 $?), 30초 후 재시작"
    sleep 30
  done
}

main() {
  if [ -z "${CF_ACCESS_CLIENT_ID:-}" ] || [ -z "${CF_ACCESS_CLIENT_SECRET:-}" ]; then
    log "CF_ACCESS_CLIENT_ID/SECRET 없음: 수집을 시작하지 않습니다"; return 0
  fi
  [ -f "${SCRIPT_DIR}/config.alloy" ] || { log "config.alloy 없음: ${SCRIPT_DIR}"; return 0; }

  # 중복 기동 방지: 잠금을 쥔 채로 백그라운드 루프가 살아 있는 동안 유지된다
  if command -v flock >/dev/null 2>&1; then
    exec 9>"$LOCK_FILE"
    if ! flock -n 9; then
      log "이미 실행 중: 새로 띄우지 않습니다"; return 0
    fi
  elif pgrep -f "alloy-${ALLOY_VERSION} run" >/dev/null 2>&1; then
    log "이미 실행 중(Alloy 프로세스 확인): 새로 띄우지 않습니다"; return 0
  fi
  log "수집 로그 파일 ${MEMME_OBS_LOG_FILE}"

  gpu_loop >/dev/null 2>&1 &
  log "GPU 수치 기록 시작 (pid $!)"

  # Alloy 설치·기동은 내려받기 시간이 걸리므로 통째로 백그라운드
  (
    bin=$(install_alloy) || exit 0
    log "Alloy ${ALLOY_VERSION} 기동, 전송 대상 ${MEMME_INGEST_URL}, pod ${RUNPOD_POD_ID}"
    alloy_loop "$bin"
  ) >/dev/null 2>&1 &
  disown -a 2>/dev/null || true
}

main
exit 0
