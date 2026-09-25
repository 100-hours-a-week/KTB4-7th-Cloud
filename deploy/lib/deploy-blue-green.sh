#!/usr/bin/env bash
set -Eeuo pipefail

service="${1:?service is required}"
app_port="${2:?app port is required}"
expected_repository="${3:?expected ECR repository is required}"
image="${4:?image is required}"
commit_sha="${5:?commit SHA is required}"
secret_id="${6:?runtime secret id is required}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../${service}" && pwd)"
state_dir="${script_dir}/runtime"
runtime_env="${script_dir}/.runtime.env"
runtime_nginx_conf="${script_dir}/.runtime.nginx.conf"
active_file="${state_dir}/active-color"
upstream_file="${state_dir}/upstream.conf"
project="memme-${service}"
registry="${AWS_ACCOUNT_ID:?AWS_ACCOUNT_ID is required}.dkr.ecr.${AWS_REGION:?AWS_REGION is required}.amazonaws.com"
proxy_health_port=80
if [[ "${service}" == backend ]]; then
  proxy_health_port=8081
fi

if [[ ! "${image}" =~ ^${registry//./\\.}/${expected_repository//\//\\/}@sha256:[a-f0-9]{64}$ ]]; then
  echo "Image must be the expected immutable ECR digest." >&2
  exit 2
fi
if [[ ! "${commit_sha}" =~ ^[a-f0-9]{40}$ ]]; then
  echo "Commit SHA must be a full 40-character lowercase SHA." >&2
  exit 2
fi
for command in aws docker python3; do
  command -v "${command}" >/dev/null || { echo "Required command is missing: ${command}" >&2; exit 2; }
done

authenticate_ecr() {
  aws ecr get-login-password --region "${AWS_REGION}" \
    | docker login --username AWS --password-stdin "${registry}" >/dev/null
}

write_runtime_env() {
  local secret_json temp_env
  secret_json="$(aws secretsmanager get-secret-value --secret-id "${secret_id}" --query SecretString --output text --region "${AWS_REGION}")"
  temp_env="$(mktemp "${runtime_env}.XXXXXX")"
  umask 077
  SECRET_JSON="${secret_json}" python3 - "${temp_env}" <<'PY'
import json
import os
import re
import sys

values = json.loads(os.environ["SECRET_JSON"])
if not isinstance(values, dict):
    raise SystemExit("Runtime secret must be a JSON object.")
with open(sys.argv[1], "w", encoding="utf-8") as output:
    for key, value in sorted(values.items()):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise SystemExit(f"Invalid environment variable name: {key}")
        if not isinstance(value, str) or "\n" in value or "\r" in value:
            raise SystemExit(f"Environment variable {key} must be a single-line string.")
        output.write(f"{key}={value}\n")
PY
  chmod 600 "${temp_env}"
  mv "${temp_env}" "${runtime_env}"
}

write_upstream() {
  local color="$1" temp_file
  temp_file="${upstream_file}.tmp"
  cat > "${temp_file}" <<EOF_UPSTREAM
upstream app_upstream {
    server ${service}-${color}:${app_port};
    keepalive 32;
}
EOF_UPSTREAM
  mv "${temp_file}" "${upstream_file}"
}

health_check() {
  local color="$1" attempt response
  for attempt in $(seq 1 24); do
    if response="$(IMAGE="${image}" STATE_DIR="${state_dir}" docker compose -p "${project}" -f "${script_dir}/compose.yaml" exec -T nginx wget -qO- "http://${service}-${color}:${app_port}/health" 2>/dev/null)" \
      && [[ "${response}" == *'"status":"ok"'* ]]; then
      return 0
    fi
    sleep 5
  done
  return 1
}

restore_previous_upstream() {
  local previous="$1"
  if [[ -n "${previous}" ]]; then
    write_upstream "${previous}"
  else
    cp "${script_dir}/nginx/upstream.default.conf" "${upstream_file}"
  fi
  IMAGE="${image}" STATE_DIR="${state_dir}" docker compose -p "${project}" -f "${script_dir}/compose.yaml" exec -T nginx nginx -s reload >/dev/null
}

mkdir -p "${state_dir}"
chmod 700 "${state_dir}"
if [[ ! -f "${upstream_file}" ]]; then
  cp "${script_dir}/nginx/upstream.default.conf" "${upstream_file}"
fi

# Keep the bind mount on one inode across git checkouts. Git replaces tracked
# files, which otherwise leaves the running nginx container with stale config.
if [[ "${service}" == backend ]]; then
  cat "${script_dir}/nginx/nginx.conf" > "${runtime_nginx_conf}"
  chmod 644 "${runtime_nginx_conf}"
fi

write_runtime_env
authenticate_ecr

previous="$(cat "${active_file}" 2>/dev/null || true)"
case "${previous}" in
  blue) candidate="green" ;;
  green) candidate="blue" ;;
  "") candidate="blue" ;;
  *) echo "Invalid active color state: ${previous}" >&2; exit 2 ;;
esac

compose=(docker compose -p "${project}" -f "${script_dir}/compose.yaml")
IMAGE="${image}" STATE_DIR="${state_dir}" "${compose[@]}" up -d nginx
IMAGE="${image}" STATE_DIR="${state_dir}" "${compose[@]}" pull "${service}-${candidate}"
IMAGE="${image}" STATE_DIR="${state_dir}" "${compose[@]}" up -d --no-deps "${service}-${candidate}"

if ! health_check "${candidate}"; then
  IMAGE="${image}" STATE_DIR="${state_dir}" "${compose[@]}" logs --tail 100 "${service}-${candidate}" >&2 || true
  IMAGE="${image}" STATE_DIR="${state_dir}" "${compose[@]}" rm -sf "${service}-${candidate}" || true
  echo "Candidate ${candidate} did not pass health check; existing traffic was not changed." >&2
  exit 1
fi

if ! write_upstream "${candidate}" \
  || ! IMAGE="${image}" STATE_DIR="${state_dir}" "${compose[@]}" exec -T nginx nginx -s reload \
  || ! IMAGE="${image}" STATE_DIR="${state_dir}" "${compose[@]}" exec -T nginx wget -qO- "http://127.0.0.1:${proxy_health_port}/health" | grep -q '"status":"ok"'; then
  restore_previous_upstream "${previous}" || true
  IMAGE="${image}" STATE_DIR="${state_dir}" "${compose[@]}" rm -sf "${service}-${candidate}" || true
  echo "Traffic switch failed; restored the previous upstream." >&2
  exit 1
fi

printf '%s\n' "${candidate}" > "${active_file}"
cat > "${state_dir}/current-deployment.json" <<EOF_RECORD
{"service":"${service}","color":"${candidate}","image":"${image}","commitSha":"${commit_sha}","deployedAt":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","health":"ok"}
EOF_RECORD
chmod 600 "${state_dir}/current-deployment.json"
printf 'DEPLOYED service=%s color=%s image=%s commit=%s health=ok\n' "${service}" "${candidate}" "${image}" "${commit_sha}"
