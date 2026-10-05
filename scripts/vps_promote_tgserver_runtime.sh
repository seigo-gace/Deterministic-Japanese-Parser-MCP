#!/usr/bin/env bash
set -Eeuo pipefail

source_ref="${DJPMCP_SOURCE_REF:-849ca2f1092899b447586f351b11d0c59aa6991b}"
repo="seigo-gace/Deterministic-Japanese-Parser-MCP"
current="${DJPMCP_RUNTIME_CONTAINER:-djpmcp-http}"
canary="${DJPMCP_CANARY_CONTAINER:-djpmcp-tgserver-canary}"
canary_port="${DJPMCP_CANARY_PORT:-18765}"
prod_port="${DJPMCP_PROD_PORT:-8765}"
tg_url="${DJPMCP_TGS_LOG_URL:-http://127.0.0.1:3000}"
ts="$(date -u +%Y%m%dT%H%M%SZ)"
image="djpmcp-http:p006-${source_ref:0:12}"
canary_run_id="vps-canary-${ts}-${source_ref:0:7}"
prod_run_id="vps-runtime-${ts}-${source_ref:0:7}"
backup="${current}-backup-${ts}"
tmp="$(mktemp -d)"
swapped=0
success=0

wait_ready() {
  local port="$1"
  local name="$2"
  for _ in $(seq 1 90); do
    if curl -fsS "http://127.0.0.1:${port}/readyz" -o /dev/null 2>/dev/null; then
      return 0
    fi
    if [ "$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null || echo false)" != true ]; then
      return 1
    fi
    sleep 1
  done
  return 1
}

search_run() {
  local run_id="$1"
  local out="$2"
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
  for _ in $(seq 1 60); do
    code="$(curl -sS --connect-timeout 2 --max-time 10 \
      -H 'content-type: application/json' \
      --data-binary @"$tmp/search-request.json" \
      -o "$out" -w '%{http_code}' "$tg_url/search" || true)"
    if [[ "$code" =~ ^2[0-9][0-9]$ ]] && python3 - "$out" "$run_id" <<'PY'
import json, sys
x = json.load(open(sys.argv[1], encoding='utf-8'))
hits = x.get('hits') or []
match = [h for h in hits if h.get('project_id') == 'P006' and h.get('run_id') == sys.argv[2]]
raise SystemExit(0 if match else 1)
PY
    then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

print_hit() {
  local file="$1"
  local run_id="$2"
  local prefix="$3"
  python3 - "$file" "$run_id" "$prefix" <<'PY'
import json, sys
x = json.load(open(sys.argv[1], encoding='utf-8'))
hits = [h for h in (x.get('hits') or []) if h.get('project_id') == 'P006' and h.get('run_id') == sys.argv[2]]
if not hits:
    raise SystemExit('missing hit')
h = hits[-1]
p = sys.argv[3]
print(f'{p}_HITS={len(hits)}')
for key in ('project_id','severity','hint','source','repo','branch','workflow','run_id','module'):
    print(f'{p}_{key.upper()}={h.get(key, "")}')
PY
}

rollback() {
  if [ "$swapped" -ne 1 ] || [ "$success" -eq 1 ]; then
    return
  fi
  echo 'ROLLBACK=START'
  docker rm -f "$current" >/dev/null 2>&1 || true
  if docker inspect "$backup" >/dev/null 2>&1; then
    docker rename "$backup" "$current" >/dev/null
    docker start "$current" >/dev/null
    if wait_ready "$prod_port" "$current"; then
      echo 'ROLLBACK=PASS'
    else
      echo 'ROLLBACK=FAILED_OLD_RUNTIME_NOT_READY'
    fi
  else
    echo 'ROLLBACK=FAILED_BACKUP_NOT_FOUND'
  fi
}

cleanup() {
  rc=$?
  docker rm -f "$canary" >/dev/null 2>&1 || true
  rollback || true
  rm -rf "$tmp"
  exit "$rc"
}
trap cleanup EXIT

echo 'GACE_DJPMCP_P006_PROMOTION_BEGIN'
echo "SOURCE_REF=$source_ref"
echo "TGS_URL=$tg_url"
echo "CANARY_RUN_ID=$canary_run_id"
echo "PROD_RUN_ID=$prod_run_id"

if ! docker inspect "$current" >"$tmp/current-inspect.json" 2>/dev/null; then
  echo 'PRECHECK=FAIL_CURRENT_RUNTIME_NOT_FOUND'
  exit 2
fi
python3 - "$tmp/current-inspect.json" <<'PY'
import json, sys
x = json.load(open(sys.argv[1]))[0]
errors = []
if x.get('State',{}).get('Running') is not True:
    errors.append('current_not_running')
if x.get('HostConfig',{}).get('NetworkMode') != 'bridge':
    errors.append('network_mode_changed')
if x.get('Mounts'):
    errors.append('unexpected_mounts')
rp = x.get('HostConfig',{}).get('RestartPolicy',{}).get('Name')
if rp != 'unless-stopped':
    errors.append('restart_policy_changed')
pb = x.get('HostConfig',{}).get('PortBindings') or {}
b = pb.get('8765/tcp') or []
if not any(i.get('HostIp') == '127.0.0.1' and i.get('HostPort') == '8765' for i in b):
    errors.append('localhost_port_binding_changed')
if errors:
    raise SystemExit('PRECHECK_RUNTIME_CONTRACT_CHANGED=' + ','.join(errors))
print('PRECHECK_RUNTIME_CONTRACT=PASS')
PY

tgs_health="$(curl -sS --connect-timeout 2 --max-time 5 -o "$tmp/tgs-health.json" -w '%{http_code}' "$tg_url/health" || true)"
echo "TGS_HEALTH_HTTP=${tgs_health:-000}"
[[ "${tgs_health:-000}" =~ ^2[0-9][0-9]$ ]] || { echo 'PRECHECK=FAIL_TGS_HEALTH'; exit 3; }

if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$canary_port$"; then
  echo "PRECHECK=FAIL_CANARY_PORT_${canary_port}_IN_USE"
  exit 4
fi

curl -fsSL "https://codeload.github.com/${repo}/tar.gz/${source_ref}" -o "$tmp/source.tgz"
tar -xzf "$tmp/source.tgz" -C "$tmp"
src="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d -name 'Deterministic-Japanese-Parser-MCP-*' | head -n1)"
[ -n "$src" ] && [ -f "$src/Dockerfile.http" ] || { echo 'PRECHECK=FAIL_SOURCE_ARCHIVE'; exit 5; }

echo 'BUILD_IMAGE=START'
docker build -q -f "$src/Dockerfile.http" -t "$image" "$src" >/dev/null
echo 'BUILD_IMAGE=PASS'

docker rm -f "$canary" >/dev/null 2>&1 || true
docker run -d --name "$canary" --network host \
  -e DJPMCP_HTTP_HOST=127.0.0.1 \
  -e "DJPMCP_HTTP_PORT=$canary_port" \
  -e DJPMCP_HTTP_WORKERS=1 \
  -e DJPMCP_HTTP_ALLOW_UNAUTHENTICATED=1 \
  -e "DJPMCP_HTTP_ALLOWED_HOSTS=127.0.0.1:${canary_port},localhost:${canary_port}" \
  -e DJPMCP_HTTP_MAX_BODY_BYTES=1048576 \
  -e DJPMCP_HARD_DEADLINE_MS=5000 \
  -e DJPMCP_LOG_SINK=tgserver \
  -e "DJPMCP_TGS_LOG_URL=$tg_url" \
  -e DJPMCP_TGS_PROJECT_ID=P006 \
  -e DJPMCP_TGS_SOURCE=deterministic-japanese-parser-mcp \
  -e DJPMCP_TGS_REPO="$repo" \
  -e DJPMCP_TGS_BRANCH=chatgpt-m1-sync-20261003-1852 \
  -e DJPMCP_TGS_WORKFLOW='VPS Predeploy Canary' \
  -e DJPMCP_TGS_RUN_ID="$canary_run_id" \
  -e DJPMCP_TGS_MODULE=parser-runtime \
  "$image" >/dev/null

if ! wait_ready "$canary_port" "$canary"; then
  echo 'CANARY_READY=FAIL'
  docker logs "$canary" 2>&1 | tail -n 120 || true
  exit 6
fi
echo 'CANARY_READY=PASS'

curl -fsS -H 'content-type: application/json' \
  --data '{"original_text":"それを変更しろ。","execution_mode":"external_action","analysis_depth":"auto","deadline_ms":50}' \
  "http://127.0.0.1:${canary_port}/v1/analyze" -o "$tmp/canary-analyze.json"
python3 - "$tmp/canary-analyze.json" <<'PY'
import json, sys
x = json.load(open(sys.argv[1], encoding='utf-8'))
status = x.get('overall_status')
if status not in {'PARTIAL','FAILED'}:
    raise SystemExit(f'CANARY_ANALYZE_UNEXPECTED={status!r}')
print('CANARY_ANALYZE=' + status)
PY
if ! search_run "$canary_run_id" "$tmp/canary-search.json"; then
  echo 'CANARY_P006_READBACK=FAIL'
  docker logs "$canary" 2>&1 | tail -n 120 || true
  exit 7
fi
echo 'CANARY_P006_READBACK=PASS'
print_hit "$tmp/canary-search.json" "$canary_run_id" CANARY_P006
docker rm -f "$canary" >/dev/null

echo 'PROMOTION_GATE=PASS'

python3 - "$tmp/current-inspect.json" "$tmp/prod.env" "$tg_url" "$prod_run_id" <<'PY'
import json, sys
x = json.load(open(sys.argv[1]))[0]
env = {}
for item in x.get('Config',{}).get('Env') or []:
    key, sep, value = item.partition('=')
    if sep:
        if '\n' in value or '\r' in value:
            raise SystemExit(f'unsupported multiline env: {key}')
        env[key] = value
env.update({
    'DJPMCP_HTTP_HOST': '127.0.0.1',
    'DJPMCP_HTTP_PORT': '8765',
    'DJPMCP_HTTP_ALLOWED_HOSTS': '127.0.0.1:8765,localhost:8765',
    'DJPMCP_LOG_SINK': 'tgserver',
    'DJPMCP_TGS_LOG_URL': sys.argv[3],
    'DJPMCP_TGS_PROJECT_ID': 'P006',
    'DJPMCP_TGS_SOURCE': 'deterministic-japanese-parser-mcp',
    'DJPMCP_TGS_REPO': 'seigo-gace/Deterministic-Japanese-Parser-MCP',
    'DJPMCP_TGS_BRANCH': 'chatgpt-m1-sync-20261003-1852',
    'DJPMCP_TGS_WORKFLOW': 'VPS Persistent Runtime',
    'DJPMCP_TGS_RUN_ID': sys.argv[4],
    'DJPMCP_TGS_MODULE': 'parser-runtime',
})
with open(sys.argv[2], 'w', encoding='utf-8') as f:
    for key in sorted(env):
        f.write(f'{key}={env[key]}\n')
PY
chmod 600 "$tmp/prod.env"

api_key="$(python3 - "$tmp/current-inspect.json" <<'PY'
import json, sys
x = json.load(open(sys.argv[1]))[0]
for item in x.get('Config',{}).get('Env') or []:
    if item.startswith('DJPMCP_HTTP_API_KEY='):
        print(item.split('=',1)[1])
        break
PY
)"
[ -n "$api_key" ] || { echo 'PROMOTION=FAIL_CURRENT_API_KEY_MISSING'; exit 8; }

old_image="$(docker inspect -f '{{.Config.Image}}' "$current")"
echo "OLD_IMAGE=$old_image"
echo "BACKUP_CONTAINER=$backup"

docker stop "$current" >/dev/null
docker rename "$current" "$backup"
swapped=1

docker run -d --name "$current" --network host --restart unless-stopped \
  --env-file "$tmp/prod.env" "$image" >/dev/null

if ! wait_ready "$prod_port" "$current"; then
  echo 'PROD_READY=FAIL'
  docker logs "$current" 2>&1 | tail -n 120 || true
  exit 9
fi
echo 'PROD_READY=PASS'

curl -fsS \
  -H "Authorization: Bearer ${api_key}" \
  -H 'content-type: application/json' \
  --data '{"original_text":"それを変更しろ。","execution_mode":"external_action","analysis_depth":"auto","deadline_ms":50}' \
  "http://127.0.0.1:${prod_port}/v1/analyze" \
  -o "$tmp/prod-analyze.json"
python3 - "$tmp/prod-analyze.json" <<'PY'
import json, sys
x = json.load(open(sys.argv[1], encoding='utf-8'))
status = x.get('overall_status')
if status not in {'PARTIAL','FAILED'}:
    raise SystemExit(f'PROD_ANALYZE_UNEXPECTED={status!r}')
print('PROD_ANALYZE=' + status)
print('PROD_SEMANTIC_HASH=' + str(x.get('semantic_hash','')))
PY

if ! search_run "$prod_run_id" "$tmp/prod-search.json"; then
  echo 'PROD_P006_READBACK=FAIL'
  docker logs "$current" 2>&1 | tail -n 120 || true
  exit 10
fi
echo 'PROD_P006_READBACK=PASS'
print_hit "$tmp/prod-search.json" "$prod_run_id" PROD_P006

new_network="$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$current")"
new_state="$(docker inspect -f '{{.State.Status}}' "$current")"
echo "NEW_NETWORK_MODE=$new_network"
echo "NEW_RUNTIME_STATE=$new_state"
[ "$new_network" = host ] || { echo 'PROD_VERIFY=FAIL_NETWORK_MODE'; exit 11; }
[ "$new_state" = running ] || { echo 'PROD_VERIFY=FAIL_NOT_RUNNING'; exit 12; }

success=1
echo 'ROLLBACK_BACKUP_PRESERVED=TRUE'
echo "ROLLBACK_BACKUP_CONTAINER=$backup"
echo 'PROMOTION_RESULT=PASS'
echo 'GACE_DJPMCP_P006_PROMOTION_END'
