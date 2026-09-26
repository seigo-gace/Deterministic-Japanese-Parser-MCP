from __future__ import annotations

import importlib
import json
import os
import threading
import time
from pathlib import Path


def _fresh_logger(monkeypatch):
    monkeypatch.setenv("DJPMCP_LOG_SINK", "tgserver")
    monkeypatch.setenv("DJPMCP_TGS_LOG_URL", "http://127.0.0.1:3000/ingest")
    monkeypatch.setenv("DJPMCP_TGS_PROJECT_ID", "P006")
    if "DJPMCP_TGS_LOG_QUEUE_SIZE" not in os.environ:
        monkeypatch.setenv("DJPMCP_TGS_LOG_QUEUE_SIZE", "8")
    monkeypatch.setenv("DJPMCP_TGS_LOG_BATCH_SIZE", "8")
    monkeypatch.setenv("DJPMCP_TGS_LOG_TIMEOUT_MS", "50")
    import deterministic_japanese_parser_mcp.logger as logger

    return importlib.reload(logger)


def test_tgserver_entry_masks_nested_sensitive_text(monkeypatch):
    logger = _fresh_logger(monkeypatch)
    entry = logger._build_tgs_entry({
        "overall_status": "PARTIAL",
        "original_text": "mail foo@example.com bearer ABCDEFGHIJKLMNOP",
        "nested": {"secret": "api_key=abcdefghijklmno"},
    })
    assert entry["project_id"] == "P006"
    assert entry["severity"] == "warn"
    decoded = json.loads(entry["message"])
    assert decoded["original_text"] == "mail <EMAIL> Bearer <TOKEN>"
    assert decoded["nested"]["secret"] == "<SECRET>"
    assert logger._tgs_bulk_url() == "http://127.0.0.1:3000/ingest/bulk"


def test_tgserver_sink_never_blocks_parser_thread(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DJPMCP_TGS_LOG_QUEUE_SIZE", "8")
    logger = _fresh_logger(monkeypatch)
    release = threading.Event()
    started = threading.Event()

    def slow_post(_entries):
        started.set()
        release.wait(0.3)

    monkeypatch.setattr(logger, "_post_tgs_bulk", slow_post)
    path = tmp_path / "parser.jsonl"
    t0 = time.perf_counter()
    logger.append_log(path, {
        "overall_status": "PARTIAL",
        "original_text": "それを変更しろ。",
    })
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert elapsed_ms < 100
    assert started.wait(0.2)
    assert not path.exists()

    release.set()
    assert logger.flush_logs(0.5)
    stats = logger.get_log_stats()
    assert stats["enqueued"] == 1
    assert stats["sent"] == 1
    assert stats["batches"] == 1


def test_tgserver_sink_defers_sanitization_and_serialization(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DJPMCP_TGS_LOG_QUEUE_SIZE", "8")
    logger = _fresh_logger(monkeypatch)
    release = threading.Event()
    started = threading.Event()
    real_build = logger._build_tgs_entry

    def slow_build(payload):
        started.set()
        release.wait(0.3)
        return real_build(payload)

    monkeypatch.setattr(logger, "_build_tgs_entry", slow_build)
    monkeypatch.setattr(logger, "_post_tgs_bulk", lambda _entries: None)
    path = tmp_path / "parser.jsonl"

    t0 = time.perf_counter()
    logger.append_log(path, {
        "overall_status": "PARTIAL",
        "original_text": "mail foo@example.com",
    })
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert elapsed_ms < 100
    assert started.wait(0.2)
    assert not path.exists()
    release.set()
    assert logger.flush_logs(0.5)
    assert logger.get_log_stats()["sent"] == 1


def test_worker_batches_pending_logs_into_one_tgserver_call(monkeypatch):
    monkeypatch.setenv("DJPMCP_TGS_LOG_QUEUE_SIZE", "16")
    monkeypatch.setenv("DJPMCP_TGS_LOG_BATCH_SIZE", "8")
    logger = _fresh_logger(monkeypatch)
    received: list[list[dict]] = []
    release = threading.Event()
    first_started = threading.Event()

    def capture(entries):
        received.append(entries)
        first_started.set()
        release.wait(0.3)

    monkeypatch.setattr(logger, "_post_tgs_bulk", capture)
    logger.append_log(Path("unused"), {"overall_status": "PARTIAL", "original_text": "one"})
    assert first_started.wait(0.2)
    for value in ("two", "three", "four", "five"):
        logger.append_log(Path("unused"), {"overall_status": "PARTIAL", "original_text": value})
    release.set()
    assert logger.flush_logs(1.0)
    assert sum(len(batch) for batch in received) == 5
    assert len(received) <= 2
    assert logger.get_log_stats()["sent"] == 5


def test_tgserver_queue_is_bounded_and_does_not_spill_to_disk(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DJPMCP_TGS_LOG_QUEUE_SIZE", "1")
    monkeypatch.setenv("DJPMCP_TGS_LOG_BATCH_SIZE", "1")
    logger = _fresh_logger(monkeypatch)
    release = threading.Event()
    started = threading.Event()

    def blocked_post(_entries):
        started.set()
        release.wait(0.5)

    monkeypatch.setattr(logger, "_post_tgs_bulk", blocked_post)
    path = tmp_path / "parser.jsonl"

    logger.append_log(path, {"overall_status": "PARTIAL", "original_text": "one"})
    assert started.wait(0.2)
    for value in ("two", "three", "four"):
        logger.append_log(path, {"overall_status": "PARTIAL", "original_text": value})

    assert not path.exists()
    assert logger.get_log_stats()["dropped"] >= 1
    release.set()
    assert logger.flush_logs(1.0)
