#!/usr/bin/env bash
# End-to-end packaging smoke: build (if needed) and run the add-on image the
# way Supervisor would, then assert the built UI and API serve. No live HA:
# ha-mcp lists tools without one; /threads and / need no HA.
set -euo pipefail

ADDON_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="concierge-addon-smoke:local"
DATA="$(mktemp -d)"
NAME="concierge-smoke-$$"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$DATA"; }
trap cleanup EXIT

# Fake add-on options: a dummy key so agent construction (eager provider check)
# succeeds; auto_run_tools true keeps the smoke free of approval prompts.
cat > "$DATA/options.json" <<'JSON'
{"provider":"anthropic","model":"claude-sonnet-5","title_model":"","api_key":"dummy-key",
 "base_url":"","auto_run_tools":true,"skills":[],"tracing":false,"log_level":"info"}
JSON

# Build freshness is handled inside the Dockerfile: its project-install step uses
# `uv sync ... --reinstall-package concierge-backend`, which rebuilds the local
# wheel on every build even though the backend's static 0.0.0 version never busts
# uv's cache mount. So a plain cache-enabled build still validates committed
# source here (and `docker build --no-cache` would NOT clear that cache mount
# anyway). Layer caching is left on for speed.
docker build --build-arg BUILD_VERSION=0.1.0.dev1 --build-arg BUILD_ARCH=amd64 \
  -t "$IMAGE" "$ADDON_DIR" >/dev/null

# SUPERVISOR_TOKEN: Supervisor always injects this for hassio_api/homeassistant_api
# add-ons; the smoke mirrors that. run.py maps it to CONCIERGE_HA_TOKEN, which the
# bundled ha-mcp needs non-empty to pass its stdio standard-mode validation and
# start. A bogus non-empty token is fine — Plan 1 Task 11 proved ha-mcp lists
# tools with an unreachable URL + fake token without connecting, and this smoke
# makes no HA-backed calls (/ and /threads don't touch HA).
docker run -d --name "$NAME" -p 8098:8098 -v "$DATA:/data" \
  -e SUPERVISOR_TOKEN=smoke-fake-token "$IMAGE" >/dev/null

# Wait for the server (startup spawns the bundled ha-mcp stdio subprocess).
for i in $(seq 1 30); do
  if curl -sf -o /dev/null "http://127.0.0.1:8098/threads"; then break; fi
  sleep 1
  if [ "$i" -eq 30 ]; then echo "server did not start"; docker logs "$NAME"; exit 1; fi
done

echo "== GET /threads =="
threads=$(curl -sf "http://127.0.0.1:8098/threads")
echo "$threads"
[ "$threads" = "[]" ] || { echo "expected [] from a fresh store"; exit 1; }

echo "== GET / (built UI) =="
curl -sf "http://127.0.0.1:8098/" | grep -qi "concierge" || {
  echo "index.html did not serve the built app"; docker logs "$NAME"; exit 1; }

echo "SMOKE OK: built UI served, /threads returns [] — packaging works."
