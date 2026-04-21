#!/usr/bin/env bash

set -euo pipefail

run_verify=0
run_live=0

for arg in "$@"; do
  case "$arg" in
    --verify)
      run_verify=1
      ;;
    --live)
      run_live=1
      ;;
    --full)
      run_verify=1
      run_live=1
      ;;
    *)
      echo "Uso: scripts/run_readiness_checks.sh [--verify] [--live] [--full]" >&2
      exit 1
      ;;
  esac
done

if [[ "$run_verify" -eq 1 ]]; then
  poetry run verify --agent
fi

poetry run pytest tests/readiness/test_readiness_suite.py --agent

if [[ "$run_live" -eq 1 ]]; then
  poetry run pytest -m "readiness and live" --agent
fi
