from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.source_authored_meaning_release_contract import validate


def _write_zip(path: Path, members: dict[str, str | bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def _json_line(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"


def _sha(data: str | bytes) -> str:
    import hashlib

    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def test_source_authored_meaning_release_contract_accepts_valid_assets(tmp_path: Path) -> None:
    semantic = _json_line(
        {
            "meaning_origin": "source-authored",
            "meanings": ["meaning"],
            "source": {
                "license": "CC0",
                "logical_source_id": "fixture",
                "source_id": "fixture:1",
                "source_record_sha256": "abc",
            },
            "surface": "語",
            "surfaces": ["語"],
        }
    )
    lexical = _json_line(
        {
            "automatic_runtime_promotion": False,
            "meaning_candidates": [{"label": "meaning"}],
            "record_id": "r1",
            "surfaces": ["語"],
        }
    )
    evidence = ""
    source = _json_line({"meanings": ["meaning"], "source_role": "lexical-definition", "surfaces": ["語"]})
    unresolved = ""
    manifest = {
        "boundaries": {"runtime_promotion": False},
        "canonical_evidence_record_count": 0,
        "lexical_candidate_record_count": 1,
        "mode": "mcp-universal-source-adapter-contract",
        "outputs": {
            "canonical-evidence.jsonl": {"sha256": _sha(evidence)},
            "lexical-candidates.jsonl": {"sha256": _sha(lexical)},
            "semantic-reference.jsonl": {"sha256": _sha(semantic)},
        },
        "semantic_reference_record_count": 1,
    }
    report = {
        "adapter_record_count": 1,
        "boundaries": {"automatic_runtime_promotion": False, "source_authored_meanings_only": True},
        "files": {
            "source_adapter_records": {"sha256": _sha(source)},
            "unresolved": {"sha256": _sha(unresolved)},
        },
        "mode": "frozen-raw-source-authored-meaning-factory",
        "unresolved_record_count": 0,
    }
    _write_zip(
        tmp_path / "mcp-source-authored-meaning-factory-v1.zip",
        {
            "meaning-factory/adapter-output/manifest.json": json.dumps(manifest),
            "meaning-factory/meaning-factory-report.json": json.dumps(report),
            "meaning-factory/adapter-output/semantic-reference.jsonl": semantic,
            "meaning-factory/adapter-output/lexical-candidates.jsonl": lexical,
            "meaning-factory/adapter-output/canonical-evidence.jsonl": evidence,
            "meaning-factory/source-adapter-records.jsonl": source,
            "meaning-factory/unresolved-meaning-records.jsonl": unresolved,
        },
    )
    _write_zip(tmp_path / "mcp-auxiliary-source-role-shard-0-v1.zip", {"roles-0.jsonl": ""})
    _write_zip(tmp_path / "mcp-auxiliary-source-role-shard-1-v1.zip", {"roles-1.jsonl": ""})
    (tmp_path / "mcp-collected-raw-factory-input-v1.zip.part-00").write_bytes(b"raw-")
    (tmp_path / "mcp-collected-raw-factory-input-v1.zip.part-01").write_bytes(b"factory-")
    (tmp_path / "mcp-collected-raw-factory-input-v1.zip.part-02").write_bytes(b"input")

    result = validate(
        tmp_path,
        require_role_shards=True,
        require_raw_factory_input=True,
        expected_raw_factory_input_sha256=_sha(b"raw-factory-input"),
    )

    assert result["status"] == "pass"
    assert result["counts"]["semantic_reference_records"] == 1
    assert result["raw_factory_input_reconstructed_sha256"] == _sha(b"raw-factory-input")
    assert result["direct_final_runtime_ready"] is False
    assert result["boundaries"]["drive_source_of_truth"] is False


def test_source_authored_meaning_release_contract_rejects_generated_meaning(tmp_path: Path) -> None:
    semantic = _json_line(
        {
            "meaning_origin": "generated",
            "meanings": ["meaning"],
            "source": {
                "license": "CC0",
                "logical_source_id": "fixture",
                "source_id": "fixture:1",
                "source_record_sha256": "abc",
            },
            "surface": "語",
        }
    )
    lexical = _json_line(
        {
            "automatic_runtime_promotion": False,
            "meaning_candidates": [{"label": "meaning"}],
            "record_id": "r1",
            "surfaces": ["語"],
        }
    )
    manifest = {
        "boundaries": {"runtime_promotion": False},
        "canonical_evidence_record_count": 0,
        "lexical_candidate_record_count": 1,
        "mode": "mcp-universal-source-adapter-contract",
        "outputs": {
            "canonical-evidence.jsonl": {"sha256": _sha("")},
            "lexical-candidates.jsonl": {"sha256": _sha(lexical)},
            "semantic-reference.jsonl": {"sha256": _sha(semantic)},
        },
        "semantic_reference_record_count": 1,
    }
    report = {
        "adapter_record_count": 1,
        "boundaries": {"automatic_runtime_promotion": False, "source_authored_meanings_only": True},
        "files": {
            "source_adapter_records": {"sha256": _sha(_json_line({"meanings": ["meaning"], "source_role": "lexical-definition", "surfaces": ["語"]}))},
            "unresolved": {"sha256": _sha("")},
        },
        "mode": "frozen-raw-source-authored-meaning-factory",
        "unresolved_record_count": 0,
    }
    _write_zip(
        tmp_path / "mcp-source-authored-meaning-factory-v1.zip",
        {
            "meaning-factory/adapter-output/manifest.json": json.dumps(manifest),
            "meaning-factory/meaning-factory-report.json": json.dumps(report),
            "meaning-factory/adapter-output/semantic-reference.jsonl": semantic,
            "meaning-factory/adapter-output/lexical-candidates.jsonl": lexical,
            "meaning-factory/adapter-output/canonical-evidence.jsonl": "",
            "meaning-factory/source-adapter-records.jsonl": _json_line({"meanings": ["meaning"], "source_role": "lexical-definition", "surfaces": ["語"]}),
            "meaning-factory/unresolved-meaning-records.jsonl": "",
        },
    )

    with pytest.raises(ValueError, match="meaning_origin"):
        validate(tmp_path)



def test_source_authored_meaning_release_contract_requires_raw_factory_parts(tmp_path: Path) -> None:
    _write_zip(tmp_path / "mcp-source-authored-meaning-factory-v1.zip", {})

    with pytest.raises(ValueError, match="missing raw factory input parts"):
        validate(tmp_path, require_raw_factory_input=True, deep_scan=False)
