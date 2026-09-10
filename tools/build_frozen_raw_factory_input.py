#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import tempfile
from typing import Any
import zipfile

from unified_semantic_data.raw_intake import (
    INTAKE_SCHEMA_VERSION,
    inspect_collected_artifact,
    load_profiles,
    validate_intake_manifest,
)
from unified_semantic_data.collection_intake import inspect_collection_artifact

SCHEMA_VERSION = "1.0.0"
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def validate_config(config: dict[str, Any]) -> None:
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported frozen raw input config schema")
    policy = config.get("policy") or {}
    required_false = (
        "external_source_network_enabled",
        "new_source_acquisition_enabled",
        "normalization",
        "semantic_enrichment",
        "adapter_conversion",
        "runtime_promotion",
    )
    for key in required_false:
        if policy.get(key) is not False:
            raise ValueError(f"{key} must be false")
    if policy.get("input_origin") != "already-collected-github-actions-artifacts-only":
        raise ValueError("input_origin must be frozen GitHub Actions artifacts only")
    if policy.get("raw_artifact_zip_bytes_preserved") is not True:
        raise ValueError("raw artifact ZIP bytes must be preserved")
    if not config.get("freeze_at"):
        raise ValueError("freeze_at is required")
    if not config.get("workflow_sources"):
        raise ValueError("workflow_sources are required")
    if int(config.get("expected_artifact_count", 0)) < 1:
        raise ValueError("expected_artifact_count is required")
    if int(config.get("expected_source_unit_count", 0)) < 1:
        raise ValueError("expected_source_unit_count is required")
    output = config.get("output") or {}
    if not str(output.get("filename") or "").endswith(".tar"):
        raise ValueError("output filename must be .tar")


def safe_name(value: str) -> str:
    cleaned = SAFE_NAME.sub("_", value).strip("._")
    return cleaned or "artifact"


def _manifest_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def matching_profiles(
    artifact_name: str, profile_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    collection_matches = [
        profile
        for profile in profile_rows
        if profile.get("artifact_kind") == "collection"
        and (
            artifact_name == str(profile["artifact_name"])
            or artifact_name.startswith(f"{profile['artifact_name']}-")
        )
    ]
    if collection_matches:
        return collection_matches
    harvest_matches = [
        profile
        for profile in profile_rows
        if profile.get("artifact_kind", "harvest") != "collection"
        and (
            artifact_name == str(profile["artifact_name"])
            or f"-{profile['artifact_name']}-" in artifact_name
        )
    ]
    if not harvest_matches:
        return []
    longest = max(len(str(profile["artifact_name"])) for profile in harvest_matches)
    return [
        profile
        for profile in harvest_matches
        if len(str(profile["artifact_name"])) == longest
    ]


def build_bundle(
    *,
    config_path: Path,
    selected_path: Path,
    downloads_root: Path,
    output_path: Path,
    manifest_path: Path,
    profiles_path: Path,
) -> dict[str, Any]:
    config = load_json(config_path)
    validate_config(config)
    selected = load_json(selected_path)
    artifacts = selected.get("artifacts") or []
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("selected artifact list is empty")
    profiles = load_profiles(profiles_path)
    expected = int(config["expected_artifact_count"])
    if len(artifacts) != expected:
        raise ValueError(f"artifact count mismatch: expected={expected} actual={len(artifacts)}")
    expected_sources = int(config["expected_source_unit_count"])
    if int(profiles["expected_source_count"]) != expected_sources:
        raise ValueError("config/profile expected source counts differ")
    profile_rows = list(profiles["sources"])

    unmatched = sorted(
        str(item.get("name") or "")
        for item in artifacts
        if not matching_profiles(str(item.get("name") or ""), profile_rows)
    )
    if unmatched:
        raise ValueError(f"artifact has no source payload profile: {unmatched}")

    verified: list[dict[str, Any]] = []
    intake_sources: list[dict[str, Any]] = []
    seen_digests: set[str] = set()

    for item in sorted(
        artifacts,
        key=lambda row: (str(row.get("name")), int(row.get("id", 0))),
    ):
        artifact_id = int(item["id"])
        path = downloads_root / f"{artifact_id}.zip"
        if not path.is_file():
            raise FileNotFoundError(path)
        if not zipfile.is_zipfile(path):
            raise ValueError(f"GitHub artifact is not a ZIP archive: {path}")

        local_digest = sha256_file(path)
        api_digest = str(item.get("digest") or "")
        if api_digest.startswith("sha256:") and local_digest != api_digest.split(":", 1)[1]:
            raise ValueError(f"artifact digest mismatch: {artifact_id}")

        if config["policy"].get("deduplicate_by_artifact_digest") is True:
            if local_digest in seen_digests:
                continue
            seen_digests.add(local_digest)

        copied = dict(item)
        copied["downloaded_zip_sha256"] = local_digest
        copied["downloaded_zip_bytes"] = path.stat().st_size
        copied["bundle_path"] = (
            f"artifacts/{artifact_id}-{safe_name(str(item.get('name') or artifact_id))}.zip"
        )
        matched = matching_profiles(str(item["name"]), profile_rows)
        kinds = {profile.get("artifact_kind", "harvest") for profile in matched}
        if kinds == {"collection"}:
            intake_sources.extend(
                inspect_collection_artifact(
                    path,
                    item,
                    matched,
                    profiles.get("limits") or {},
                )
            )
        elif kinds == {"harvest"} and len(matched) == 1:
            intake_sources.append(
                inspect_collected_artifact(
                    path,
                    item,
                    matched[0],
                    profiles.get("limits") or {},
                )
            )
        else:
            raise ValueError(f"ambiguous artifact profile mapping: {item['name']}")
        verified.append(copied)

    if not verified:
        raise ValueError("all artifacts were deduplicated; bundle would be empty")

    if len(verified) != expected or len(intake_sources) != expected_sources:
        raise ValueError(
            "required factory input missing: "
            f"artifacts={len(verified)}/{expected} sources={len(intake_sources)}/{expected_sources}"
        )
    lane_counts: dict[str, int] = {}
    parser_counts: dict[str, int] = {}
    for source in intake_sources:
        lane_counts[source["rights_lane"]] = lane_counts.get(source["rights_lane"], 0) + 1
        parser_counts[source["parser_family"]] = parser_counts.get(source["parser_family"], 0) + 1

    bundle_manifest = {
        "schema_version": SCHEMA_VERSION,
        "source_intake_schema_version": INTAKE_SCHEMA_VERSION,
        "mode": "frozen-collected-raw-factory-input",
        "change_unit": config.get("change_unit"),
        "freeze_at": config["freeze_at"],
        "repository": config.get("repository"),
        "branch": config.get("branch"),
        "artifact_count": len(verified),
        "source_count": len(intake_sources),
        "unique_logical_source_count": len(
            {source.get("logical_source_id", source["source_id"]) for source in intake_sources}
        ),
        "factory_ready_source_count": sum(
            1 for source in intake_sources if source["factory_ready"]
        ),
        "rights_lane_counts": dict(sorted(lane_counts.items())),
        "parser_family_counts": dict(sorted(parser_counts.items())),
        "selected_runs": selected.get("selected_runs") or [],
        "policy": config["policy"],
        "artifacts": verified,
        "sources": sorted(intake_sources, key=lambda row: row["source_id"]),
        "boundaries": {
            "external_source_network_used_by_bundle_builder": False,
            "raw_artifact_zip_bytes_preserved": True,
            "normalization_performed": False,
            "semantic_enrichment_performed": False,
            "adapter_conversion_performed": False,
            "runtime_promotion_performed": False,
            "all_selected_payload_bytes_hashed": True,
            "all_harvest_payload_records_parsed": True,
            "collection_payload_parser_probe_performed": True,
            "restricted_sources_preserved_for_internal_intake": True,
            "public_runtime_eligibility_is_rights_lane_gated": True,
            "automatic_approval_performed": False,
        },
    }
    validate_intake_manifest(bundle_manifest)
    manifest_bytes = _manifest_bytes(bundle_manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(manifest_bytes)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_path, mode="w", format=tarfile.PAX_FORMAT) as archive:
        info = tarfile.TarInfo("bundle-manifest.json")
        info.size = len(manifest_bytes)
        info.mtime = 0
        info.uid = 0
        info.gid = 0
        info.uname = ""
        info.gname = ""
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(manifest_bytes))

        for item in verified:
            source = downloads_root / f"{int(item['id'])}.zip"
            info = tarfile.TarInfo(item["bundle_path"])
            info.size = source.stat().st_size
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o644
            with source.open("rb") as handle:
                archive.addfile(info, handle)

    bundle_manifest["bundle_sha256"] = sha256_file(output_path)
    bundle_manifest["bundle_bytes"] = output_path.stat().st_size
    manifest_path.write_bytes(_manifest_bytes(bundle_manifest))
    return bundle_manifest


def self_test() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        downloads = root / "downloads"
        downloads.mkdir()
        payloads: dict[int, bytes] = {}
        artifacts = []
        for artifact_id, name, content in (
            (1, "source-a", b"raw-a"),
            (2, "source-b", b"raw-b"),
        ):
            path = downloads / f"{artifact_id}.zip"
            raw_digest = hashlib.sha256(content).hexdigest()
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as handle:
                handle.writestr(
                    "source-lock.json",
                    json.dumps(
                        {
                            "source_id": name,
                            "raw_sha256": raw_digest,
                            "raw_bytes": len(content),
                        }
                    ),
                )
                handle.writestr("raw.txt", content)
            digest = sha256_file(path)
            payloads[artifact_id] = path.read_bytes()
            artifacts.append(
                {
                    "id": artifact_id,
                    "name": name,
                    "digest": f"sha256:{digest}",
                    "workflow_run_id": 100 + artifact_id,
                }
            )

        config = {
            "schema_version": SCHEMA_VERSION,
            "change_unit": "SELF-TEST",
            "freeze_at": "2026-08-10T16:12:23Z",
            "repository": "example/repo",
            "branch": "test",
            "policy": {
                "external_source_network_enabled": False,
                "new_source_acquisition_enabled": False,
                "input_origin": "already-collected-github-actions-artifacts-only",
                "raw_artifact_zip_bytes_preserved": True,
                "normalization": False,
                "semantic_enrichment": False,
                "adapter_conversion": False,
                "runtime_promotion": False,
                "deduplicate_by_artifact_digest": True,
            },
            "workflow_sources": [{"workflow_id": 1}],
            "expected_artifact_count": 2,
            "expected_source_unit_count": 2,
            "output": {"filename": "bundle.tar"},
        }
        profiles_path = root / "profiles.json"
        profiles_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "expected_source_count": 2,
                    "sources": [
                        {
                            "artifact_name": name,
                            "source_id": name,
                            "rights_lane": "C",
                            "public_runtime_eligible": True,
                            "parser_family": "commented-sequence",
                            "payload_globs": ["raw.txt"],
                            "encodings": ["utf-8"],
                            "source_roles": ["usage"],
                        }
                        for name in ("source-a", "source-b")
                    ],
                }
            ),
            encoding="utf-8",
        )
        config_path = root / "config.json"
        selected_path = root / "selected.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        selected_path.write_text(
            json.dumps({"artifacts": artifacts, "selected_runs": [101, 102]}),
            encoding="utf-8",
        )
        output_path = root / "bundle.tar"
        manifest_path = root / "bundle.manifest.json"
        result = build_bundle(
            config_path=config_path,
            selected_path=selected_path,
            downloads_root=downloads,
            output_path=output_path,
            manifest_path=manifest_path,
            profiles_path=profiles_path,
        )
        if result["artifact_count"] != 2:
            raise AssertionError("self-test artifact count mismatch")
        with tarfile.open(output_path, "r") as archive:
            members = {member.name: member for member in archive.getmembers()}
            for artifact in result["artifacts"]:
                member = members[artifact["bundle_path"]]
                bundled = archive.extractfile(member).read()
                if bundled != payloads[int(artifact["id"])]:
                    raise AssertionError("raw artifact ZIP bytes changed inside bundle")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("self-test")

    validate = sub.add_parser("validate-config")
    validate.add_argument("--config", type=Path, required=True)

    build = sub.add_parser("build")
    build.add_argument("--config", type=Path, required=True)
    build.add_argument("--selected-artifacts", type=Path, required=True)
    build.add_argument("--downloads-root", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--manifest", type=Path, required=True)
    build.add_argument("--profiles", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "self-test":
        self_test()
        print('{"status":"SELF_TEST_OK"}')
        return 0
    if args.command == "validate-config":
        validate_config(load_json(args.config))
        print('{"status":"CONFIG_OK"}')
        return 0

    result = build_bundle(
        config_path=args.config,
        selected_path=args.selected_artifacts,
        downloads_root=args.downloads_root,
        output_path=args.output,
        manifest_path=args.manifest,
        profiles_path=args.profiles,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
