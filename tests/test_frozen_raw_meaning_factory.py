from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from unified_semantic_data.frozen_raw_meaning_factory import (  # noqa: E402
    _extract_fields,
    build_frozen_raw_meaning_factory,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fixture(tmp_path: Path, rows: list[dict]) -> tuple[Path, Path]:
    payload = b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        for row in rows
    )
    artifact_buffer = io.BytesIO()
    payload_path = "collection/reference/meanings.jsonl"
    with zipfile.ZipFile(artifact_buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(payload_path, payload)
    artifact = artifact_buffer.getvalue()
    bundle_member = "artifacts/123-meaning-collection.zip"
    source = {
        "source_id": "japanese-wordnet-1.1",
        "logical_source_id": "japanese-wordnet-1.1",
        "artifact_id": 123,
        "artifact_name": "meaning-collection",
        "workflow_run_id": 456,
        "rights_lane": "C",
        "public_runtime_eligible": True,
        "parser_family": "jsonl",
        "source_roles": ["lexical-definition", "semantic-class"],
        "payloads": [
            {
                "path": payload_path,
                "bytes": len(payload),
                "sha256": _sha(payload),
                "probe_records": len(rows),
            }
        ],
        "parser_probe_records": len(rows),
        "factory_ready": True,
        "full_processing_performed": False,
        "automatic_approval": False,
        "automatic_runtime_promotion": False,
    }
    manifest = {
        "schema_version": "1.0.0",
        "source_intake_schema_version": "1.0.0",
        "freeze_at": "2026-08-13T00:00:00Z",
        "artifact_count": 1,
        "source_count": 1,
        "unique_logical_source_count": 1,
        "factory_ready_source_count": 1,
        "artifacts": [
            {
                "id": 123,
                "name": "meaning-collection",
                "bundle_path": bundle_member,
                "downloaded_zip_sha256": _sha(artifact),
            }
        ],
        "sources": [source],
        "boundaries": {},
    }
    bundle = tmp_path / "bundle.tar"
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode("utf-8")
    with tarfile.open(bundle, "w") as archive:
        info = tarfile.TarInfo("bundle-manifest.json")
        info.size = len(manifest_bytes)
        archive.addfile(info, io.BytesIO(manifest_bytes))
        info = tarfile.TarInfo(bundle_member)
        info.size = len(artifact)
        archive.addfile(info, io.BytesIO(artifact))
    manifest["bundle_sha256"] = hashlib.sha256(bundle.read_bytes()).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return bundle, manifest_path


def _meaning_row() -> dict:
    return {
        "id": "WNJA-1",
        "surface": "銀行",
        "readings": ["ぎんこう"],
        "part_of_speech": ["noun"],
        "meanings": ["預金や融資などを扱う金融機関"],
        "dataset": "Japanese WordNet",
        "version": "1.1",
        "license": "BSD-style",
        "source_id": "synset-1",
        "source_url": "https://example.invalid/wnja",
        "source_sha256": "a" * 64,
        "attribution": "Japanese WordNet",
    }


def test_frozen_bundle_definitions_become_review_only_adapter_lanes(tmp_path: Path) -> None:
    bundle, manifest = _fixture(tmp_path, [_meaning_row()])
    output = tmp_path / "out"
    report = build_frozen_raw_meaning_factory(bundle, manifest, output)

    assert report["lexical_definition_source_count"] == 1
    assert report["adapter_record_count"] == 1
    assert report["unresolved_record_count"] == 0
    assert report["boundaries"]["automatic_approval"] is False
    semantic = json.loads(
        (output / "adapter-output/semantic-reference.jsonl").read_text(
            encoding="utf-8"
        )
    )
    lexical = json.loads(
        (output / "adapter-output/lexical-candidates.jsonl").read_text(
            encoding="utf-8"
        )
    )
    assert semantic["meanings"] == ["預金や融資などを扱う金融機関"]
    assert semantic["source"]["artifact_id"] == 123
    assert semantic["source"]["rights_lane"] == "C"
    assert semantic["source"]["payload_sha256"]
    assert lexical["meaning_candidates"][0]["review_status"] == "needs-evidence"
    assert lexical["automatic_runtime_promotion"] is False


def test_meaning_factory_fails_closed_on_placeholder_definition(tmp_path: Path) -> None:
    row = _meaning_row()
    row["meanings"] = ["pending review"]
    valid = _meaning_row()
    valid["id"] = "WNJA-2"
    valid["surface"] = "証拠"
    bundle, manifest = _fixture(tmp_path, [valid, row])
    output = tmp_path / "out"
    report = build_frozen_raw_meaning_factory(bundle, manifest, output)
    assert report["input_definition_record_count"] == 2
    assert report["adapter_record_count"] == 1
    assert report["unresolved_record_count"] == 1
    assert report["boundaries"]["unresolved_rows_never_enter_meaning_adapter"] is True
    unresolved = (output / "unresolved-meaning-records.jsonl").read_text(
        encoding="utf-8"
    )
    assert "SOURCE_AUTHORED_MEANING_REQUIRED" in unresolved
    unresolved_row = json.loads(unresolved)
    assert unresolved_row["value"]["meanings"] == ["pending review"]
    assert unresolved_row["missing_required_fields"] == ["meanings"]
    assert unresolved_row["base_adapter_record"]["surfaces"] == ["銀行"]
    assert unresolved_row["source_record_sha256"]


def test_j_ono_resolved_evidence_is_not_lost() -> None:
    fields = _extract_fields(
        "j-ono-definitions",
        {
            "hiragana": ["きらきら", "きらっきら"],
            "katakana": ["キラキラ"],
            "romaji": ["kirakira"],
            "resolved_meaning_evidence": [
                {"meaning": "光が細かく繰り返し輝く様子"}
            ],
        },
    )
    assert fields["surfaces"] == ["kirakira", "きらきら", "きらっきら", "キラキラ"]
    assert fields["meanings"] == ["光が細かく繰り返し輝く様子"]


def test_bundle_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    bundle, manifest = _fixture(tmp_path, [_meaning_row()])
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["bundle_sha256"] = "0" * 64
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen bundle checksum mismatch"):
        build_frozen_raw_meaning_factory(bundle, manifest, tmp_path / "out")
