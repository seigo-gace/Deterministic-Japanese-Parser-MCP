from __future__ import annotations

import importlib
import json
import sys
import threading
import time
from pathlib import Path


def _fresh_logger(monkeypatch, **overrides):
    monkeypatch.setenv("DJPMCP_LOG_SINK", "tgserver")
    monkeypatch.setenv("DJPMCP_TGS_LOG_URL", "http://127.0.0.1:3000")
    monkeypatch.setenv("DJPMCP_TGS_PROJECT_ID", "P006")
    monkeypatch.setenv("DJPMCP_TGS_LOG_QUEUE_SIZE", "8")
    monkeypatch.setenv("DJPMCP_TGS_LOG_BATCH_SIZE", "8")
    monkeypatch.setenv("DJPMCP_TGS_LOG_TIMEOUT_MS", "50")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)

    name = "deterministic_japanese_parser_mcp.logger"
    if name in sys.modules:
        sys.modules[name].shutdown_logger(0.2)
    import deterministic_japanese_parser_mcp.logger as logger

    module = importlib.reload(logger)
    module.prewarm_logger()
    return module


def test_tgserver_entry_is_p006_searchable_and_masks_nested_sensitive_text(
    monkeypatch,
):
    logger = _fresh_logger(
        monkeypatch,
        DJPMCP_TGS_SOURCE="deterministic-japanese-parser-mcp",
        DJPMCP_TGS_REPO="seigo-gace/Deterministic-Japanese-Parser-MCP",
        DJPMCP_TGS_BRANCH="chatgpt-m1-sync-20261003-1852",
        DJPMCP_TGS_WORKFLOW="runtime-e2e",
        DJPMCP_TGS_RUN_ID="37132435412",
        DJPMCP_TGS_MODULE="parser-runtime",
    )
    entry = logger._build_tgs_entry({
        "overall_status": "PARTIAL",
        "original_text": "mail foo@example.com bearer ABCDEFGHIJKLMNOP",
        "nested": {"secret": "api_key=abcdefghijklmno"},
    })

    assert entry["project_id"] == "P006"
    assert entry["severity"] == "warn"
    assert entry["source"] == "deterministic-japanese-parser-mcp"
    assert entry["repo"] == "seigo-gace/Deterministic-Japanese-Parser-MCP"
    assert entry["branch"] == "chatgpt-m1-sync-20261003-1852"
    assert entry["workflow"] == "runtime-e2e"
    assert entry["run_id"] == "37132435412"
    assert entry["module"] == "parser-runtime"
    assert logger._tgs_bulk_url() == "http://127.0.0.1:3000/ingest/bulk"
    decoded = json.loads(entry["message"])
    assert decoded["original_text"] == "mail <EMAIL> Bearer <TOKEN>"
    assert decoded["nested"]["secret"] == "<SECRET>"
    logger.shutdown_logger(0.2)


def test_invalid_metadata_is_omitted_instead_of_rejecting_log(monkeypatch):
    logger = _fresh_logger(
        monkeypatch,
        DJPMCP_TGS_BRANCH="bad\nbranch",
        DJPMCP_TGS_WORKFLOW="x" * 257,
    )
    entry = logger._build_tgs_entry({"overall_status": "FAILED", "original_text": "x"})

    assert entry["project_id"] == "P006"
    assert entry["severity"] == "error"
    assert "branch" not in entry
    assert "workflow" not in entry
    assert entry["source"] == "deterministic-japanese-parser-mcp"
    assert entry["repo"] == "seigo-gace/Deterministic-Japanese-Parser-MCP"
    assert entry["module"] == "parser-runtime"
    logger.shutdown_logger(0.2)


def test_tgserver_sink_never_blocks_parser_thread(monkeypatch, tmp_path: Path):
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
    logger.shutdown_logger(0.2)


def test_tgserver_queue_is_bounded_and_fail_open(monkeypatch, tmp_path: Path):
    logger = _fresh_logger(
        monkeypatch,
        DJPMCP_TGS_LOG_QUEUE_SIZE="1",
        DJPMCP_TGS_LOG_BATCH_SIZE="1",
    )
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
    logger.shutdown_logger(0.2)


def test_file_sink_remains_available_for_public_self_host(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DJPMCP_LOG_SINK", "file")
    name = "deterministic_japanese_parser_mcp.logger"
    if name in sys.modules:
        sys.modules[name].shutdown_logger(0.2)
    import deterministic_japanese_parser_mcp.logger as logger

    logger = importlib.reload(logger)
    target = tmp_path / "parser.jsonl"
    logger.append_log(target, {
        "overall_status": "PARTIAL",
        "original_text": "mail foo@example.com",
    })

    row = json.loads(target.read_text(encoding="utf-8"))
    assert row["original_text"] == "mail <EMAIL>"
    assert row["overall_status"] == "PARTIAL"
