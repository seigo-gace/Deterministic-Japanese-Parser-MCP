from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from unified_semantic_data.factory_input_preprocessor import (  # noqa: E402
    build_factory_input_preprocessor,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _source(*, license_name: str = "CC-BY-4.0", digest: str = "a" * 64) -> dict:
    return {
        "dataset": "fixture",
        "version": "1",
        "license": license_name,
        "source_id": "fixture:1",
        "source_url": "https://example.invalid/source",
        "source_sha256": digest,
        "attribution": "fixture",
        "source_record_id": "row-1",
        "source_record_sha256": "b" * 64,
    }


def _resolved_adapter() -> dict:
    return {
        "adapter_record_id": "READY-1",
        "source_role": "lexical-definition",
        "surfaces": ["銀行"],
        "readings": ["ぎんこう"],
        "part_of_speech_list": ["noun"],
        "meanings": ["預金や融資などを扱う金融機関"],
        "payload": {},
        "source": _source(),
    }


def _unresolved_meaning() -> dict:
    source = _source(license_name="")
    return {
        "source_id": "fixture",
        "payload_path": "meaning.jsonl",
        "line": 2,
        "reason": "SOURCE_AUTHORED_MEANING_REQUIRED",
        "source_roles": ["lexical-definition"],
        "source_record_sha256": source["source_record_sha256"],
        "missing_required_fields": ["meanings", "source.license"],
        "base_adapter_record": {
            "adapter_record_id": "PENDING-1",
            "source_role": "lexical-definition",
            "surfaces": ["証拠"],
            "readings": ["しょうこ"],
            "part_of_speech_list": ["noun"],
            "meanings": [],
            "payload": {"source_fields_preserved": []},
            "source": source,
        },
        "value": {"surface": "証拠", "meanings": ["pending review"]},
    }


def test_preprocessor_builds_common_completion_queue_without_factory_leak(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter.jsonl"
    unresolved = tmp_path / "unresolved.jsonl"
    _write_jsonl(adapter, [_resolved_adapter()])
    _write_jsonl(unresolved, [_unresolved_meaning()])

    report = build_factory_input_preprocessor([adapter], [unresolved], tmp_path / "out")

    assert report["status"] == "COMPLETION_REQUIRED"
    assert report["factory_input_complete"] is False
    assert report["validated_adapter_record_count"] == 1
    assert report["remaining_completion_item_count"] == 1
    assert report["unresolved_required_fields"] == 2
    queue = json.loads(
        (tmp_path / "out/factory-input-completion-queue.jsonl").read_text(encoding="utf-8")
    )
    assert queue["original_record"]["meanings"] == ["pending review"]
    assert queue["missing_required_fields"] == ["meanings", "source.license"]
    assert (tmp_path / "out/supplemented-adapter-records.jsonl").read_text() == ""


def test_evidence_bearing_supplement_completes_and_validates_input(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter.jsonl"
    unresolved = tmp_path / "unresolved.jsonl"
    first = tmp_path / "first"
    _write_jsonl(adapter, [_resolved_adapter()])
    _write_jsonl(unresolved, [_unresolved_meaning()])
    build_factory_input_preprocessor([adapter], [unresolved], first)
    queue = json.loads((first / "factory-input-completion-queue.jsonl").read_text())
    supplements = tmp_path / "supplements.jsonl"
    _write_jsonl(supplements, [{
        "completion_id": queue["completion_id"],
        "method": "chatgpt-build-time",
        "patch": {
            "meanings": ["事実を明らかにするための資料や根拠"],
            "source": {"license": "CC-BY-4.0"},
        },
        "evidence": ["fixture:meaning.jsonl:2", "license:fixture-source-lock"],
        "rationale": "元見出しと同一Sourceの確定済み説明・License記録から補足",
    }])

    report = build_factory_input_preprocessor(
        [adapter], [unresolved], tmp_path / "complete",
        supplements_path=supplements,
        require_complete=True,
    )

    assert report["status"] == "READY_FOR_FACTORY"
    assert report["unresolved_required_fields"] == 0
    assert report["factory_input_record_count"] == 2
    completed = json.loads(
        (tmp_path / "complete/supplemented-adapter-records.jsonl").read_text()
    )
    completion = completed["payload"]["factory_input_completion"]
    assert completion["method"] == "chatgpt-build-time"
    assert completion["automatic_approval"] is False
    assert completion["automatic_runtime_promotion"] is False
    assert completed["source"]["source_record_sha256"] == "b" * 64


def test_supplement_cannot_overwrite_existing_fields(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter.jsonl"
    unresolved = tmp_path / "unresolved.jsonl"
    first = tmp_path / "first"
    _write_jsonl(adapter, [_resolved_adapter()])
    _write_jsonl(unresolved, [_unresolved_meaning()])
    build_factory_input_preprocessor([adapter], [unresolved], first)
    queue = json.loads((first / "factory-input-completion-queue.jsonl").read_text())
    supplements = tmp_path / "supplements.jsonl"
    _write_jsonl(supplements, [{
        "completion_id": queue["completion_id"],
        "method": "chatgpt-build-time",
        "patch": {"surfaces": ["改変"], "meanings": ["意味"], "source": {"license": "MIT"}},
        "evidence": ["fixture"],
        "rationale": "invalid overwrite",
    }])
    with pytest.raises(ValueError, match="was not missing"):
        build_factory_input_preprocessor(
            [adapter], [unresolved], tmp_path / "rejected", supplements_path=supplements
        )


def test_completion_outputs_are_byte_deterministic(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter.jsonl"
    unresolved = tmp_path / "unresolved.jsonl"
    _write_jsonl(adapter, [_resolved_adapter()])
    _write_jsonl(unresolved, [_unresolved_meaning()])
    build_factory_input_preprocessor([adapter], [unresolved], tmp_path / "one")
    build_factory_input_preprocessor([adapter], [unresolved], tmp_path / "two")
    for name in (
        "factory-input-completion-queue.jsonl",
        "supplemented-adapter-records.jsonl",
    ):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()
