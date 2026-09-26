from __future__ import annotations

import atexit
import json
import os
import queue
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

_EMAIL = re.compile(r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{12,}")
_API_KEY = re.compile(r"(?i)(?:api[_-]?key|token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{8,}")
_LONG_NUMBER = re.compile(r"(?<!\d)\d{12,19}(?!\d)")

_DEFAULT_TGS_URL = ""
_DEFAULT_TGS_PROJECT_ID = "P006"
_DEFAULT_QUEUE_SIZE = 2048
_DEFAULT_TIMEOUT_MS = 250
_MAX_RETRIES = 2

_queue: queue.Queue[dict[str, Any]] | None = None
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()
_stop_event = threading.Event()
_stats_lock = threading.Lock()
_stats = {
    "enqueued": 0,
    "sent": 0,
    "failed": 0,
    "dropped": 0,
}


def mask_sensitive_text(text: str) -> str:
    value = _EMAIL.sub("<EMAIL>", text)
    value = _BEARER.sub("Bearer <TOKEN>", value)
    value = _API_KEY.sub("<SECRET>", value)
    value = _LONG_NUMBER.sub("<LONG_NUMBER>", value)
    return value


def _mask_value(value: Any) -> Any:
    if isinstance(value, str):
        return mask_sensitive_text(value)
    if isinstance(value, dict):
        return {str(key): _mask_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask_value(item) for item in value]
    if isinstance(value, tuple):
        return [_mask_value(item) for item in value]
    return value


def _sink_mode() -> str:
    explicit = os.getenv("DJPMCP_LOG_SINK", "auto").strip().lower()
    if explicit not in {"auto", "tgserver", "file", "none"}:
        raise ValueError("DJPMCP_LOG_SINK must be auto, tgserver, file, or none")
    if explicit != "auto":
        return explicit
    return "tgserver" if _tgs_url() else "file"


def _tgs_url() -> str:
    return os.getenv("DJPMCP_TGS_LOG_URL", _DEFAULT_TGS_URL).strip()


def _tgs_project_id() -> str:
    value = os.getenv("DJPMCP_TGS_PROJECT_ID", _DEFAULT_TGS_PROJECT_ID).strip()
    if not re.fullmatch(r"P\d+", value):
        raise ValueError("DJPMCP_TGS_PROJECT_ID must match P<number>")
    return value


def _queue_size() -> int:
    try:
        value = int(os.getenv("DJPMCP_TGS_LOG_QUEUE_SIZE", str(_DEFAULT_QUEUE_SIZE)))
    except ValueError as exc:
        raise ValueError("DJPMCP_TGS_LOG_QUEUE_SIZE must be an integer") from exc
    if value < 1:
        raise ValueError("DJPMCP_TGS_LOG_QUEUE_SIZE must be at least 1")
    return value


def _timeout_seconds() -> float:
    try:
        timeout_ms = int(os.getenv("DJPMCP_TGS_LOG_TIMEOUT_MS", str(_DEFAULT_TIMEOUT_MS)))
    except ValueError as exc:
        raise ValueError("DJPMCP_TGS_LOG_TIMEOUT_MS must be an integer") from exc
    if timeout_ms < 1:
        raise ValueError("DJPMCP_TGS_LOG_TIMEOUT_MS must be at least 1")
    return timeout_ms / 1000


def _severity(payload: dict[str, Any]) -> str:
    status = str(payload.get("overall_status", "")).upper()
    if status == "FAILED":
        return "error"
    if status == "PARTIAL":
        return "warn"
    return "info"


def _increment(name: str, amount: int = 1) -> None:
    with _stats_lock:
        _stats[name] += amount


def get_log_stats() -> dict[str, int]:
    with _stats_lock:
        return dict(_stats)


def _build_tgs_entry(payload: dict[str, Any]) -> dict[str, Any]:
    safe_payload = _mask_value(payload)
    return {
        "project_id": _tgs_project_id(),
        "severity": _severity(safe_payload),
        "message": json.dumps(
            safe_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        "hint": "djpmcp-runtime",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _post_tgs(entry: dict[str, Any]) -> None:
    url = _tgs_url()
    if not url:
        raise RuntimeError("DJPMCP_TGS_LOG_URL is required for tgserver log sink")
    body = json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=_timeout_seconds()) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"TGserver ingest returned HTTP {response.status}")


def _worker_loop() -> None:
    assert _queue is not None
    while not _stop_event.is_set() or not _queue.empty():
        try:
            entry = _queue.get(timeout=0.05)
        except queue.Empty:
            continue
        try:
            sent = False
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    _post_tgs(entry)
                    _increment("sent")
                    sent = True
                    break
                except (OSError, RuntimeError, urllib_error.URLError):
                    if attempt < _MAX_RETRIES:
                        time.sleep(0.05 * (2 ** attempt))
            if not sent:
                _increment("failed")
        finally:
            _queue.task_done()


def _ensure_worker() -> queue.Queue[dict[str, Any]]:
    global _queue, _worker
    if _queue is not None and _worker is not None and _worker.is_alive():
        return _queue
    with _worker_lock:
        if _queue is None:
            _queue = queue.Queue(maxsize=_queue_size())
        if _worker is None or not _worker.is_alive():
            _stop_event.clear()
            _worker = threading.Thread(
                target=_worker_loop,
                name="djpmcp-tgserver-log-sink",
                daemon=True,
            )
            _worker.start()
    return _queue


def _enqueue_tgs(payload: dict[str, Any]) -> None:
    target = _ensure_worker()
    entry = _build_tgs_entry(payload)
    try:
        target.put_nowait(entry)
        _increment("enqueued")
        return
    except queue.Full:
        pass

    # Keep the parser non-blocking under a stalled TGserver. Prefer the newest
    # evidence and account for the discarded item instead of writing to disk.
    try:
        target.get_nowait()
        target.task_done()
        _increment("dropped")
    except queue.Empty:
        _increment("dropped")
    try:
        target.put_nowait(entry)
        _increment("enqueued")
    except queue.Full:
        _increment("dropped")


def _append_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = _mask_value(payload)
    row = {"timestamp": datetime.now(timezone.utc).isoformat(), **safe}
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_log(path: Path, payload: dict[str, Any]) -> None:
    """Emit parser evidence without letting log I/O dominate parser latency.

    Astera/server deployments set DJPMCP_LOG_SINK=tgserver and send through the
    bounded in-memory worker to TGserver POST /ingest. The parser thread never
    waits for the network and never spills TGserver failures to persistent disk.
    Public/self-hosted users can retain the legacy file sink explicitly or by
    leaving TGserver unconfigured.
    """

    mode = _sink_mode()
    if mode == "none":
        return
    if mode == "tgserver":
        _enqueue_tgs(payload)
        return
    _append_file(path, payload)


def flush_logs(timeout: float = 1.0) -> bool:
    """Best-effort drain for tests and orderly shutdown; not used on request path."""

    target = _queue
    if target is None:
        return True
    deadline = time.monotonic() + max(timeout, 0.0)
    while target.unfinished_tasks and time.monotonic() < deadline:
        time.sleep(0.01)
    return target.unfinished_tasks == 0


def shutdown_logger(timeout: float = 0.5) -> None:
    _stop_event.set()
    flush_logs(timeout)


atexit.register(shutdown_logger)
