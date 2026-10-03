from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Mapping

DEFAULT_TGS_URL = "https://tgserver.asterav8.jp"
DEFAULT_PROJECT_ID = "P006"


def severity_for_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized == "success":
        return "info"
    if normalized == "failure":
        return "error"
    if normalized == "cancelled":
        return "warn"
    return "debug"


def build_payload(env: Mapping[str, str], *, now: datetime | None = None) -> dict[str, str]:
    status = env.get("TGS_JOB_STATUS", "unknown").strip().lower() or "unknown"
    repo = env.get("GITHUB_REPOSITORY", "unknown/unknown").strip() or "unknown/unknown"
    workflow = env.get("TGS_WORKFLOW", env.get("GITHUB_WORKFLOW", "unknown")).strip() or "unknown"
    run_id = env.get("GITHUB_RUN_ID", "unknown").strip() or "unknown"
    run_attempt = env.get("GITHUB_RUN_ATTEMPT", "unknown").strip() or "unknown"
    branch = env.get("GITHUB_REF_NAME", "unknown").strip() or "unknown"
    sha = env.get("GITHUB_SHA", "unknown").strip() or "unknown"
    job = env.get("TGS_JOB", "unknown").strip() or "unknown"
    python_version = env.get("TGS_PYTHON_VERSION", "unknown").strip() or "unknown"
    project_id = env.get("TGS_PROJECT_ID", DEFAULT_PROJECT_ID).strip() or DEFAULT_PROJECT_ID

    if not project_id.startswith("P") or not project_id[1:].isdigit():
        raise ValueError("TGS_PROJECT_ID must match P<number>")

    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    run_url = f"https://github.com/{repo}/actions/runs/{run_id}"
    message = (
        "source=github-actions "
        f"repo={repo} branch={branch} workflow={workflow} run_id={run_id} "
        f"run_attempt={run_attempt} job={job} python={python_version} status={status} sha={sha}"
    )
    return {
        "project_id": project_id,
        "severity": severity_for_status(status),
        "message": message,
        "hint": run_url,
        "timestamp": timestamp,
    }


def _configured(env: Mapping[str, str]) -> bool:
    return bool(
        env.get("TGS_CF_ACCESS_CLIENT_ID", "").strip()
        and env.get("TGS_CF_ACCESS_CLIENT_SECRET", "").strip()
    )


def publish(env: Mapping[str, str]) -> tuple[bool, str]:
    if not _configured(env):
        return True, "TGS_INGEST_CONFIGURED=FALSE"

    payload = build_payload(env)
    base = env.get("LEGACY_TGSERVER_URL", DEFAULT_TGS_URL).strip().rstrip("/") or DEFAULT_TGS_URL
    request = urllib.request.Request(
        f"{base}/ingest",
        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "CF-Access-Client-Id": env["TGS_CF_ACCESS_CLIENT_ID"].strip(),
            "CF-Access-Client-Secret": env["TGS_CF_ACCESS_CLIENT_SECRET"].strip(),
            "User-Agent": "djpmcp-github-actions-tgserver-producer/1",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
            http_status = response.status
    except urllib.error.HTTPError as exc:
        return False, f"TGS_INGEST_HTTP={exc.code}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, f"TGS_INGEST_ERROR={type(exc).__name__}"

    result_status = str(body.get("status", "")) if isinstance(body, dict) else ""
    if http_status != 200 or result_status not in {"accepted", "duplicate"}:
        return False, f"TGS_INGEST_HTTP={http_status} TGS_INGEST_STATUS={result_status or 'invalid'}"
    return True, f"TGS_INGEST_HTTP={http_status} TGS_INGEST_STATUS={result_status}"


def main() -> int:
    try:
        ok, summary = publish(os.environ)
    except (KeyError, ValueError) as exc:
        print(f"TGS_INGEST_CONFIG_ERROR={type(exc).__name__}")
        return 2
    print(summary)
    print(f"TGS_PROJECT_ID={os.environ.get('TGS_PROJECT_ID', DEFAULT_PROJECT_ID)}")
    print("TGS_SECRET_OUTPUT=NONE")
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
