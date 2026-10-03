#!/usr/bin/env bash
set -Eeuo pipefail

source_ref="${DJPMCP_SOURCE_REF:-8cda0ae3f101b4775c1fb43abf26c37a0c38f8ff}"
repo="seigo-gace/Deterministic-Japanese-Parser-MCP"
container="${DJPMCP_CANARY_CONTAINER:-djpmcp-tgserver-canary}"
port="${DJPMCP_CANARY_PORT:-18765}"
tg_url="${DJPMCP_TGS_LOG_URL:-http://127.0.0.1:3000}"
image="djpmcp-http:canary-${source_ref:0:12}"
run_id="vps-canary-$(date -u +%Y%m%dT%H%M%SZ)-${source_ref:0:7}"
tmp="$(mktemp -d)"

cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT

echo 'GACE_DJPMCP_TGS_CANARY_BEGIN'
echo "SOURCE_REF=$source_ref"
echo "CANARY_CONTAINER=$container"
echo "CANARY_PORT=$port"
echo "TGS_URL=$tg_url"
echo "CANARY_RUN_ID=$run_id"

if ! docker inspect djpmcp-http >/dev/null 2>&1; then
  echo 'CURRENT_RUNTIME_FOUND=FALSE'
  exit 2
fi
echo 'CURRENT_RUNTIME_FOUND=TRUE'

tgs_health="$(curl -sS --connect-timeout 2 --max-time 5 -o "$tmp/tgs-health.json" -w '%{http_code}' "$tg_url/health" || true)"
echo "TGS_HEALTH_HTTP=${tgs_health:-000}"
if [[ ! "${tgs_health:-000}" =~ ^2[0-9][0-9]$ ]]; then
  echo 'CANARY_RESULT=BLOCKED_TGS_HEALTH'
  exit 3
fi

if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$port$"; then
  echo "CANARY_RESULT=BLOCKED_PORT_${port}_IN_USE"
  exit 4
fi

curl -fsSL "https://codeload.github.com/${repo}/tar.gz/${source_ref}" -o "$tmp/source.tgz"
tar -xzf "$tmp/source.tgz" -C "$tmp"
src="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d -name 'Deterministic-Japanese-Parser-MCP-*' | head -n1)"
if [ -z "$src" ] || [ ! -f "$src/Dockerfile.http" ]; then
  echo 'CANARY_RESULT=BLOCKED_SOURCE_ARCHIVE'
  exit 5
fi

echo 'BUILD_CANARY_IMAGE=START'
docker build -q -f "$src/Dockerfile.http" -t "$image" "$src" >/tmp/gace-djpmcp-canary-image-id
echo "BUILD_CANARY_IMAGE=PASS"

docker rm -f "$container" >/dev/null 2>&1 || true
docker run -d --name "$container" \
  --network host \
  -e DJPMCP_HTTP_HOST=127.0.0.1 \
  -e "DJPMCP_HTTP_PORT=$port" \
  -e DJPMCP_HTTP_WORKERS=1 \
  -e DJPMCP_HTTP_ALLOW_UNAUTHENTICATED=1 \
  -e "DJPMCP_HTTP_ALLOWED_HOSTS=127.0.0.1:${port},localhost:${port}" \
  -e DJPMCP_HTTP_ALLOWED_ORIGINS= \
  -e DJPMCP_HTTP_MAX_BODY_BYTES=1048576 \
  -e DJPMCP_HARD_DEADLINE_MS=5000 \
  -e DJPMCP_LOG_SINK=tgserver \
  -e "DJPMCP_TGS_LOG_URL=$tg_url" \
  -e DJPMCP_TGS_PROJECT_ID=P006 \
  -e DJPMCP_TGS_SOURCE=deterministic-japanese-parser-mcp \
  -e DJPMCP_TGS_REPO="$repo" \
  -e DJPMCP_TGS_BRANCH=chatgpt-m1-sync-20261003-1852 \
  -e DJPMCP_TGS_WORKFLOW='VPS TGserver Canary' \
  -e DJPMCP_TGS_RUN_ID="$run_id" \
  -e DJPMCP_TGS_MODULE=parser-runtime \
  "$image" >/dev/null

echo 'CANARY_RUNTIME=STARTED'
ready=0
for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:${port}/readyz" -o "$tmp/ready.json"; then
    ready=1
    break
  fi
  running="$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || echo false)"
  if [ "$running" != true ]; then
    break
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo 'CANARY_READY=FALSE'
  docker logs "$container" 2>&1 | tail -n 120 || true
  echo 'CANARY_RESULT=FAIL_RUNTIME_NOT_READY'
  exit 6
fi
echo 'CANARY_READY=TRUE'

curl -fsS \
  -H 'content-type: application/json' \
  --data '{"original_text":"それを変更しろ。","execution_mode":"external_action","analysis_depth":"auto","deadline_ms":50}' \
  "http://127.0.0.1:${port}/v1/analyze" \
  -o "$tmp/analyze.json"
python3 - "$tmp/analyze.json" <<'PY'
import json, sys
x = json.load(open(sys.argv[1], encoding='utf-8'))
status = x.get('overall_status')
if status not in {'PARTIAL','FAILED'}:
    raise SystemExit(f'CANARY_ANALYZE_UNEXPECTED_STATUS={status!r}')
print('CANARY_ANALYZE_STATUS=' + status)
print('CANARY_SEMANTIC_HASH=' + str(x.get('semantic_hash','')))
PY

python3 - "$tmp/search-request.json" "$run_id" <<'PY'
import json, sys
json.dump({
    'query': '',
    'project_id': 'P006',
    'source': 'deterministic-japanese-parser-mcp',
    'repo': 'seigo-gace/Deterministic-Japanese-Parser-MCP',
    'run_id': sys.argv[2],
    'module': 'parser-runtime',
}, open(sys.argv[1], 'w', encoding='utf-8'), ensure_ascii=False)
PY

found=0
for _ in $(seq 1 60); do
  code="$(curl -sS --connect-timeout 2 --max-time 10 \
    -H 'content-type: application/json' \
    --data-binary @"$tmp/search-request.json" \
    -o "$tmp/search.json" -w '%{http_code}' "$tg_url/search" || true)"
  if [[ "$code" =~ ^2[0-9][0-9]$ ]]; then
    if python3 - "$tmp/search.json" "$run_id" <<'PY'
import json, sys
x = json.load(open(sys.argv[1], encoding='utf-8'))
hits = x.get('hits') or []
match = [h for h in hits if h.get('project_id') == 'P006' and h.get('run_id') == sys.argv[2]]
raise SystemExit(0 if match else 1)
PY
    then
      found=1
      break
    fi
  fi
  sleep 0.5
done

if [ "$found" -ne 1 ]; then
  echo 'P006_LOCAL_READBACK=FAIL'
  docker logs "$container" 2>&1 | tail -n 120 || true
  echo 'CANARY_RESULT=FAIL_P006_NOT_INDEXED'
  exit 7
fi

python3 - "$tmp/search.json" "$run_id" <<'PY'
import json, sys
x = json.load(open(sys.argv[1], encoding='utf-8'))
hits = [h for h in (x.get('hits') or []) if h.get('project_id') == 'P006' and h.get('run_id') == sys.argv[2]]
if not hits:
    raise SystemExit('no canary hit')
h = hits[-1]
print('P006_LOCAL_READBACK=PASS')
print('P006_HITS=' + str(len(hits)))
for key in ('project_id','severity','hint','source','repo','branch','workflow','run_id','module'):
    print('P006_' + key.upper() + '=' + str(h.get(key,'')))
PY

echo 'CURRENT_RUNTIME_STATE='"$(docker inspect -f '{{.State.Status}}' djpmcp-http)"
echo 'CURRENT_RUNTIME_UNTOUCHED=TRUE'
echo 'CANARY_RESULT=PASS'
echo 'GACE_DJPMCP_TGS_CANARY_END'
