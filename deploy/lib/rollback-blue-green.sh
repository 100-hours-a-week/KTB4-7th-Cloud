#!/usr/bin/env bash
# Switch traffic back to the color that served before the last deployment. Nothing is pulled or
# rebuilt: the previous container is still running, so only its health is checked before the switch.
set -Eeuo pipefail

service="${1:?service is required}"
app_port="${2:?app port is required}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../${service}" && pwd)"
state_dir="${script_dir}/runtime"
active_file="${state_dir}/active-color"
upstream_file="${state_dir}/upstream.conf"
project="memme-${service}"

active="$(cat "${active_file}" 2>/dev/null || true)"
case "${active}" in
  blue) previous="green" ;;
  green) previous="blue" ;;
  *) echo "No recorded active color; nothing to roll back to." >&2; exit 2 ;;
esac

compose=(docker compose -p "${project}" -f "${script_dir}/compose.yaml")
container="$(IMAGE=unused STATE_DIR="${state_dir}" "${compose[@]}" ps -q "${service}-${previous}")"
if [[ -z "${container}" || "$(docker inspect -f '{{.State.Running}}' "${container}")" != true ]]; then
  echo "Previous ${previous} container is not running; redeploy an earlier image instead." >&2
  exit 1
fi
image="$(docker inspect -f '{{.Config.Image}}' "${container}")"
run() { IMAGE="${image}" STATE_DIR="${state_dir}" "${compose[@]}" "$@"; }

if ! run exec -T nginx wget -qO- "http://${service}-${previous}:${app_port}/health" | grep -q '"status":"ok"'; then
  echo "Previous ${previous} container is not healthy; traffic was not changed." >&2
  exit 1
fi

write_upstream() {
  cat > "${upstream_file}.tmp" <<EOF_UPSTREAM
upstream app_upstream {
    server ${service}-$1:${app_port};
    keepalive 32;
}
EOF_UPSTREAM
  mv "${upstream_file}.tmp" "${upstream_file}"
}

write_upstream "${previous}"
if ! run exec -T nginx nginx -s reload \
  || ! run exec -T nginx wget -qO- "http://127.0.0.1/health" | grep -q '"status":"ok"'; then
  write_upstream "${active}"
  run exec -T nginx nginx -s reload || true
  echo "Traffic switch failed; kept ${active}." >&2
  exit 1
fi

printf '%s\n' "${previous}" > "${active_file}"
# Swap the records so a second rollback returns to the release that was just undone.
records=("${state_dir}/current-deployment.json" "${state_dir}/previous-deployment.json")
if [[ -f "${records[1]}" ]]; then
  mv "${records[0]}" "${records[0]}.tmp"
  mv "${records[1]}" "${records[0]}"
  mv "${records[0]}.tmp" "${records[1]}"
else
  # Releases before rollback support kept no previous record; the commit of the restored color is unknown.
  mv "${records[0]}" "${records[1]}" 2>/dev/null || true
  printf '{"service":"%s","color":"%s","image":"%s","commitSha":"unknown","deployedAt":"%s","health":"ok"}\n' \
    "${service}" "${previous}" "${image}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${records[0]}"
fi
chmod 600 "${records[@]}" 2>/dev/null || true
commit="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("commitSha","unknown"))' "${records[0]}" 2>/dev/null || echo unknown)"
printf 'ROLLED_BACK service=%s color=%s image=%s commit=%s health=ok\n' "${service}" "${previous}" "${image}" "${commit}"
