#!/usr/bin/env bash

set -euo pipefail

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
API_URL="http://${HOST}:${PORT}/query"
HEALTH_URL="http://${HOST}:${PORT}/health"
SERVER_LOG="$(mktemp -t media-traffic-api.XXXXXX.log)"

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

poetry run fastapi dev --host "${HOST}" --port "${PORT}" >"${SERVER_LOG}" 2>&1 &
SERVER_PID=$!

python3 - "${HEALTH_URL}" "${SERVER_PID}" "${SERVER_LOG}" <<'PY'
import sys
import time
import urllib.error
import urllib.request

health_url, pid, log_path = sys.argv[1], int(sys.argv[2]), sys.argv[3]

for _ in range(60):
    try:
        with urllib.request.urlopen(health_url, timeout=1) as response:
            if response.status == 200:
                sys.exit(0)
    except (urllib.error.URLError, TimeoutError):
        pass

    time.sleep(0.5)

print("Nao foi possivel iniciar a API local.", file=sys.stderr)
print(f"Veja o log em: {log_path}", file=sys.stderr)
sys.exit(1)
PY

echo "API local pronta em ${API_URL}"
echo "Log da API: ${SERVER_LOG}"
echo "Abrindo CLI com --debug..."

poetry run analyst-chat --api-url "${API_URL}" --debug "$@"
