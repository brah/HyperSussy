#!/usr/bin/env bash
# Dev orchestrator for HyperSussy — starts backend, frontend, or both.
#
# Usage:
#   ./dev.sh            # both (backend on :8000, frontend on :5173)
#   ./dev.sh backend    # backend only (uv run hypersussy --api)
#   ./dev.sh frontend   # frontend only (npm run dev in ./frontend)
#
# Ctrl+C shuts down every process started by this script.

set -euo pipefail

# Run from the script's own directory so paths are stable regardless of CWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

target="${1:-all}"
pids=()

start_backend() {
    echo ">> Starting backend (uv run hypersussy --api)..."
    uv run hypersussy --api &
    pids+=("$!")
}

start_frontend() {
    echo ">> Starting frontend (npm run dev)..."
    (cd frontend && npm run dev) &
    pids+=("$!")
}

cleaned_up=0
cleanup() {
    # The trap fires on INT, TERM *and* EXIT; guard against re-entry so
    # the "Shutting down" banner only prints once when the signal cascades.
    if [ "$cleaned_up" -eq 1 ]; then
        return
    fi
    cleaned_up=1
    # Nothing was ever launched (bad-arg exit, pre-start error). Quiet path.
    if [ "${#pids[@]}" -eq 0 ]; then
        return
    fi
    echo ""
    echo ">> Shutting down..."
    for pid in "${pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

case "$target" in
    backend)  start_backend ;;
    frontend) start_frontend ;;
    all)      start_backend; start_frontend ;;
    *)
        echo "Usage: $0 [backend|frontend]" >&2
        exit 2
        ;;
esac

wait
