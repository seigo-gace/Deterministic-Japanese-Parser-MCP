from __future__ import annotations

import hashlib
import gzip
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

from unified_semantic_data.frozen_raw_role_factory import (  # noqa: E402
    _iter_records,
    _project_identity,
    build_frozen_raw_role_factory,
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fixture(tmp_path: Path, rows: list[dict]) -> tuple[Path, Path, Path]:
    payload = b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        for row in rows
    )
    payload_path = "collection/usage.jsonl"
    artifact_buffer = io.BytesIO()
    with zipfile.ZipFile(artifact_buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(payload_path, payload)
    artifact = artifact_buffer.getvalue()
    member = "artifacts/321-role-collection.zip"
    source = {
        "source_id": "role-source",
        "logical_source_id": "role-source",
        "artifact_id": 321,
        "artifact_name": "role-collection",
        "workflow_run_id": 654,
        "rights_lane": "C",
        "public_runtime_eligible": True,
        "parser_family": "jsonl",
        "source_roles": ["usage"],
        "payloads": [{
            "path": payload_path, "bytes": len(payload), "sha256": _sha(payload),
            "probe_records": len(rows),
        }],
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
        "artifacts": [{
            "id": 321, "name": "role-collection", "bundle_path": member,
            "downloaded_zip_sha256": _sha(artifact),
        }],
        "sources": [source],
    }
    bundle = tmp_path / "bundle.tar"
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode("utf-8")
    with tarfile.open(bundle, "w") as archive:
        info = tarfile.TarInfo("bundle-manifest.json")
        info.size = len(manifest_bytes)
        archive.addfile(info, io.BytesIO(manifest_bytes))
        info = tarfile.TarInfo(member)
        info.size = len(artifact)
        archive.addfile(info, io.BytesIO(artifact))
    manifest["bundle_sha256"] = _sha(bundle.read_bytes())
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    profiles = {
        "schema_version": "1.0.0",
        "expected_source_count": 1,
        "limits": {},
        "sources": [{
            "artifact_name": "role-collection",
            "artifact_kind": "collection",
            "source_id": "role-source",
            "rights_lane": "C",
            "public_runtime_eligible": True,
            "parser_family": "jsonl",
            "payload_globs": [payload_path],
            "source_roles": ["usage"],
            "encodings": ["utf-8"],
        }],
    }
    profiles_path = tmp_path / "profiles.json"
    profiles_path.write_text(json.dumps(profiles), encoding="utf-8")
    return bundle, manifest_path, profiles_path


def _usage(label: str) -> dict:
    return {
        "surface": "はし", "reading": "はし", "usage_label": label,
        "dataset": "usage-test", "version": "1", "license": "CC0-1.0",
    }


def test_exact_replay_is_deduplicated_but_same_surface_different_evidence_survives(
    tmp_path: Path,
) -> None:
    bridge = _usage("bridge")
    bundle, manifest, profiles = _fixture(
        tmp_path, [bridge, dict(bridge), _usage("chopsticks")]
    )
    output = tmp_path / "out"
    report = build_frozen_raw_role_factory(bundle, manifest, profiles, output)

    assert report["input_record_count"] == 3
    assert report["role_projection_count"] == 3
    assert report["unique_adapter_record_count"] == 2
    assert report["exact_replay_duplicate_count"] == 1
    assert report["unresolved_input_record_count"] == 0
    assert report["boundaries"]["same_surface_different_payload_preserved"] is True

    records = [
        json.loads(line)
        for line in gzip.open(output / "source-role-records.jsonl.gz", "rt", encoding="utf-8")
    ]
    assert len(records) == 2
    assert {row["payload"]["source_value"]["usage_label"] for row in records} == {
        "bridge", "chopsticks"
    }
    assert sorted(row["payload"]["exact_replay_count"] for row in records) == [1, 2]
    assert all(row["surfaces"] == ["はし"] for row in records)
    evidence = [
        json.loads(line)
        for line in (output / "adapter-output/canonical-evidence.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert all(row["source"]["artifact_id"] == 321 for row in evidence)
    assert all(row["source"]["payload_sha256"] for row in evidence)
    assert all(row["source"]["license_metadata_complete"] is True for row in evidence)

    second = tmp_path / "out-second"
    second_report = build_frozen_raw_role_factory(bundle, manifest, profiles, second)
    assert second_report == report
    for relative in (
        "source-role-records.jsonl.gz",
        "unresolved-source-role-records.jsonl",
        "adapter-output/canonical-evidence.jsonl",
        "adapter-output/manifest.json",
        "role-factory-report.json",
    ):
        assert (second / relative).read_bytes() == (output / relative).read_bytes()


def test_missing_license_is_retained_but_not_marked_public_runtime_eligible(
    tmp_path: Path,
) -> None:
    bundle, manifest, profiles = _fixture(
        tmp_path, [{"surface": "証拠", "usage_label": "formal"}]
    )
    output = tmp_path / "out"
    report = build_frozen_raw_role_factory(bundle, manifest, profiles, output)
    with gzip.open(output / "source-role-records.jsonl.gz", "rt", encoding="utf-8") as handle:
        record = json.load(handle)
    assert report["license_metadata_pending_record_count"] == 1
    assert record["source"]["public_runtime_eligible"] is False
    assert "LICENSE-EXPRESSION-PENDING" in record["source"]["license"]


def test_record_without_lexical_surface_is_preserved_with_full_lineage(
    tmp_path: Path,
) -> None:
    bundle, manifest, profiles = _fixture(
        tmp_path,
        [{"id": "metadata-only", "dataset": "usage-test", "version": "1", "license": "CC0-1.0"}],
    )
    output = tmp_path / "out"
    report = build_frozen_raw_role_factory(bundle, manifest, profiles, output)
    unresolved = json.loads(
        (output / "unresolved-source-role-records.jsonl").read_text(encoding="utf-8")
    )
    assert report["input_record_count"] == 1
    assert report["unresolved_input_record_count"] == 1
    assert report["unique_adapter_record_count"] == 0
    assert unresolved["reason"] == "EXPLICIT_SURFACE_NOT_FOUND"
    assert unresolved["value"]["id"] == "metadata-only"
    assert unresolved["source"]["artifact_id"] == 321
    assert unresolved["source"]["payload_sha256"]


@pytest.mark.parametrize(
    ("family", "payload", "extra"),
    [
        ("jsonl", b'{"surface":"\xe8\xaa\x9e"}\n', {}),
        ("json-corpus", b'[{"surface":"\xe8\xaa\x9e"}]', {}),
        ("delimited-table", "語,名詞\n".encode(), {"delimiter": ","}),
        ("conllu", "1\t語\t語\tNOUN\t名詞\t_\t0\troot\t_\t_\n".encode(), {}),
        ("skk", "ご /語/\n".encode(), {}),
        ("commented-sequence", b"1F600 ; Basic_Emoji # face\n", {}),
        ("knp", "語 ご 名詞 6 普通名詞 1 * 0 * 0\nEOS\n".encode(), {}),
    ],
)
def test_line_oriented_parser_families_emit_real_records(
    tmp_path: Path, family: str, payload: bytes, extra: dict,
) -> None:
    path = tmp_path / "payload"
    path.write_bytes(payload)
    profile = {"parser_family": family, "encodings": ["utf-8"], **extra}
    records = list(_iter_records(path, profile))
    assert records
    assert _project_identity(records[0], family)["surfaces"]


def test_streaming_xml_preserves_target_children_for_lexical_projection(tmp_path: Path) -> None:
    path = tmp_path / "names.xml"
    path.write_text(
        "<root><entry><k_ele><keb>橋</keb></k_ele><r_ele><reb>はし</reb></r_ele></entry></root>",
        encoding="utf-8",
    )
    profile = {"parser_family": "streaming-xml", "xml_target_tags": ["entry"]}
    records = list(_iter_records(path, profile))
    identity = _project_identity(records[0], "streaming-xml")
    assert identity["surfaces"] == ["橋"]
    assert identity["readings"] == ["はし"]


def test_archive_index_preserves_text_members(tmp_path: Path) -> None:
    path = tmp_path / "ranking.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ranking.txt", "対話例\n")
    records = list(_iter_records(path, {"parser_family": "archive-index", "encodings": ["utf-8"]}))
    assert records == [{"archive_member": "ranking.txt", "line": 1, "text": "対話例"}]
    assert _project_identity(records[0], "archive-index")["surfaces"] == ["対話例"]
