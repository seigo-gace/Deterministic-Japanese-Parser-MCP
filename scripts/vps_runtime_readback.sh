#!/usr/bin/env bash
set -euo pipefail

if [ -n "${DJPMCP_REPO_ROOT:-}" ]; then
  repo_root="$DJPMCP_REPO_ROOT"
elif git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  repo_root="$git_root"
else
  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
container="${DJPMCP_RUNTIME_CONTAINER:-djpmcp-http}"
tg_container="${TGS_RUNTIME_CONTAINER:-tgserver-tgs-1}"
tg_host_url="${TGS_HOST_URL:-http://127.0.0.1:3000}"

redact_env() {
  python3 - "$1" <<'PY'
import json, re, sys
items = json.loads(sys.argv[1])
secret = re.compile(r'(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)', re.I)
for item in items:
    key, _, value = item.partition('=')
    if not key.startswith('DJPMCP_'):
        continue
    if secret.search(key):
        value = '[REDACTED]'
    print(f'ENV_{key}={value}')
PY
}

printf 'GACE_DJPMCP_RUNTIME_READBACK_BEGIN\n'
printf 'READ_ONLY=TRUE\n'
printf 'REPO=%s\n' "$repo_root"
printf 'BRANCH=%s\n' "$(git -C "$repo_root" branch --show-current 2>/dev/null || true)"
printf 'HEAD=%s\n' "$(git -C "$repo_root" rev-parse HEAD 2>/dev/null || true)"
printf '%s\n' '--- GIT_STATUS ---'
git -C "$repo_root" status --short 2>/dev/null || true

if ! docker inspect "$container" >/tmp/gace-djpmcp-inspect.json 2>/dev/null; then
  printf 'DJPMCP_CONTAINER_FOUND=FALSE\n'
  printf 'GACE_DJPMCP_RUNTIME_READBACK_END\n'
  exit 2
fi
printf 'DJPMCP_CONTAINER_FOUND=TRUE\n'
python3 - <<'PY'
import json
x = json.load(open('/tmp/gace-djpmcp-inspect.json'))[0]
cfg = x.get('Config', {})
host = x.get('HostConfig', {})
state = x.get('State', {})
print('CONTAINER=' + x.get('Name', '').lstrip('/'))
print('STATE=' + str(state.get('Status', '')))
print('IMAGE=' + str(cfg.get('Image', '')))
print('IMAGE_ID=' + str(x.get('Image', '')))
print('WORKDIR=' + str(cfg.get('WorkingDir', '')))
print('ENTRYPOINT=' + json.dumps(cfg.get('Entrypoint'), ensure_ascii=False))
print('CMD=' + json.dumps(cfg.get('Cmd'), ensure_ascii=False))
print('RESTART=' + json.dumps(host.get('RestartPolicy'), ensure_ascii=False))
print('PORT_BINDINGS=' + json.dumps(host.get('PortBindings'), ensure_ascii=False, sort_keys=True))
print('NETWORK_MODE=' + str(host.get('NetworkMode', '')))
print('NETWORKS=' + json.dumps(sorted((x.get('NetworkSettings', {}).get('Networks') or {}).keys())))
print('MOUNTS=' + json.dumps([{
    'Type': m.get('Type'), 'Source': m.get('Source'),
    'Destination': m.get('Destination'), 'Mode': m.get('Mode'), 'RW': m.get('RW')
} for m in x.get('Mounts', [])], ensure_ascii=False, sort_keys=True))
PY

env_json="$(python3 - <<'PY'
import json
x = json.load(open('/tmp/gace-djpmcp-inspect.json'))[0]
print(json.dumps(x.get('Config', {}).get('Env') or []))
PY
)"
redact_env "$env_json"
rm -f /tmp/gace-djpmcp-inspect.json

printf '%s\n' '--- TGS_HOST ---'
if command -v curl >/dev/null 2>&1; then
  code="$(curl -sS --connect-timeout 2 --max-time 5 -o /tmp/gace-tgs-health.json -w '%{http_code}' "$tg_host_url/health" || true)"
  printf 'TGS_HOST_URL=%s\n' "$tg_host_url"
  printf 'TGS_HOST_HEALTH_HTTP=%s\n' "${code:-000}"
  if [ -s /tmp/gace-tgs-health.json ]; then
    python3 - <<'PY'
import json
from pathlib import Path
p = Path('/tmp/gace-tgs-health.json')
try:
    x = json.loads(p.read_text())
    keep = {k: x.get(k) for k in ('ok','status','version') if k in x}
    print('TGS_HOST_HEALTH=' + json.dumps(keep, ensure_ascii=False, sort_keys=True))
except Exception:
    print('TGS_HOST_HEALTH=UNPARSEABLE')
PY
  fi
  rm -f /tmp/gace-tgs-health.json
else
  printf 'TGS_HOST_HEALTH_HTTP=CURL_MISSING\n'
fi

printf '%s\n' '--- TGS_CONTAINER ---'
if docker inspect "$tg_container" >/tmp/gace-tgs-inspect.json 2>/dev/null; then
  printf 'TGS_CONTAINER_FOUND=TRUE\n'
  python3 - <<'PY'
import json
x = json.load(open('/tmp/gace-tgs-inspect.json'))[0]
print('TGS_CONTAINER=' + x.get('Name','').lstrip('/'))
print('TGS_CONTAINER_STATE=' + str(x.get('State',{}).get('Status','')))
print('TGS_CONTAINER_IMAGE=' + str(x.get('Config',{}).get('Image','')))
print('TGS_NETWORK_MODE=' + str(x.get('HostConfig',{}).get('NetworkMode','')))
print('TGS_NETWORKS=' + json.dumps(sorted((x.get('NetworkSettings',{}).get('Networks') or {}).keys())))
print('TGS_PORT_BINDINGS=' + json.dumps(x.get('HostConfig',{}).get('PortBindings'), sort_keys=True))
PY
  rm -f /tmp/gace-tgs-inspect.json
else
  printf 'TGS_CONTAINER_FOUND=FALSE\n'
fi

printf '%s\n' '--- DJPMCP_TO_TGS_PROBES ---'
for url in 'http://127.0.0.1:3000/health' 'http://host.docker.internal:3000/health' 'http://tgserver-tgs-1:3000/health' 'http://tgs:3000/health'; do
  code="$(docker exec "$container" python - "$url" <<'PY' 2>/dev/null || true
import sys, urllib.request
url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=2) as r:
        print(r.status)
except Exception:
    print('000')
PY
)"
  printf 'PROBE_%s=%s\n' "$(printf '%s' "$url" | tr '/:.-' '_')" "${code:-000}"
done

printf 'GACE_DJPMCP_RUNTIME_READBACK_END\n'
