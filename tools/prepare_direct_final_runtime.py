#!/usr/bin/env python3
"""Prepare Direct Final runtime from GitHub Release assets (no Drive)."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.compile_direct_final_runtime import (
    _sha,
    _try_reuse_direct_final_runtime,
    compile_direct_final_runtime,
)

DEFAULT_REPO = "seigo-gace/Deterministic-Japanese-Parser-MCP"
DEFAULT_ASSET_PATTERN = "mcp-runtime-final-*"
DEFAULT_INPUT_ROOT = Path("work/direct-final-release-input")
DEFAULT_SYSTEM_ROOT = Path("work/direct-final-compiled/system")
DEFAULT_WORK_ROOT = Path("work/direct-final-runtime")

_REPO_SYSTEM = _REPO_ROOT / "dictionaries" / "system"
_COMPANION_NAMES = (
    "semantic_profiles.yaml",
    "rules",
    "metaphors",
    "task_templates.yaml",
    "task_templates.d",
    "synonyms.yaml",
    "synonyms.d",
    "language_features.d",
    "lexicon.d",
)


def _link_system_companions(
    *,
    repo_system: Path = _REPO_SYSTEM,
    dest_system_root: Path,
) -> list[str]:
    """Symlink repo system companions into work system_root (skip existing)."""
    dest_system_root.mkdir(parents=True, exist_ok=True)
    linked: list[str] = []
    for name in _COMPANION_NAMES:
        src = repo_system / name
        if not src.exists():
            continue
        dest = dest_system_root / name
        if dest.exists() or dest.is_symlink():
            continue
        dest.symlink_to(src.resolve())
        linked.append(name)
    return linked


def _locate_manifest(input_root: Path) -> Path | None:
    direct = input_root / "manifest.json"
    if direct.is_file():
        return direct
    for path in input_root.rglob("manifest.json"):
        return path
    return None


def _find_manifest(input_root: Path) -> Path:
    manifest_path = _locate_manifest(input_root)
    if manifest_path is None:
        raise FileNotFoundError(f"manifest.json not found under {input_root}")
    return manifest_path


def _extract_archives(input_root: Path) -> None:
    for path in sorted(input_root.glob("*.zip")):
        subprocess.run(["unzip", "-q", str(path), "-d", str(input_root)], check=True)
    for pattern in ("*.tar", "*.tar.gz", "*.tgz"):
        for path in sorted(input_root.glob(pattern)):
            subprocess.run(["tar", "-xf", str(path), "-C", str(input_root)], check=True)


def _manifest_record_count(manifest_path: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validation = manifest.get("validation") or {}
    return int(validation.get("full_json_records_validated", 0))


def _inputs_match_manifest(input_root: Path, manifest_path: Path) -> bool:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest.get("parts") or []:
        path = input_root / str(item["file"])
        if not path.is_file():
            return False
        if path.stat().st_size != int(item["bytes"]):
            return False
        if _sha(path) != str(item["sha256"]):
            return False
    support_meta = manifest.get("support_pack") or {}
    support = input_root / str(support_meta.get("file") or "")
    if not support.is_file():
        return False
    if support.stat().st_size != int(support_meta.get("bytes", -1)):
        return False
    if _sha(support) != str(support_meta.get("sha256") or ""):
        return False
    return True


def _require_gh() -> str:
    gh = shutil.which("gh")
    if not gh:
        raise SystemExit(
            "gh CLI is required to download GitHub Release assets. "
            "Install gh and authenticate, or populate --input-root locally."
        )
    return gh


def _gh_download(
    gh: str,
    *,
    release_tag: str,
    repo: str,
    input_root: Path,
    patterns: list[str],
) -> None:
    input_root.mkdir(parents=True, exist_ok=True)
    cmd = [
        gh,
        "release",
        "download",
        release_tag,
        "--skip-existing",
        "--repo",
        repo,
        "--dir",
        str(input_root),
    ]
    for pattern in patterns:
        cmd.extend(["--pattern", pattern])
    subprocess.run(cmd, check=True)
    _extract_archives(input_root)


def prepare_direct_final_runtime(
    *,
    release_tag: str,
    expected_records: int,
    repo: str = DEFAULT_REPO,
    asset_pattern: str = DEFAULT_ASSET_PATTERN,
    input_root: Path = DEFAULT_INPUT_ROOT,
    system_root: Path = DEFAULT_SYSTEM_ROOT,
    work_root: Path = DEFAULT_WORK_ROOT,
    force_download: bool = False,
    force_recompile: bool = False,
    semantic_shard_size: int = 10000,
) -> dict[str, object]:
    downloaded = False
    gh: str | None = None

    manifest_path = _locate_manifest(input_root)
    if manifest_path is None:
        gh = _require_gh()
        _gh_download(
            gh,
            release_tag=release_tag,
            repo=repo,
            input_root=input_root,
            patterns=["manifest.json"],
        )
        downloaded = True
        manifest_path = _find_manifest(input_root)

    input_root = manifest_path.parent
    record_count = _manifest_record_count(manifest_path)
    if record_count != expected_records:
        raise SystemExit(
            f"expected-records mismatch: expected={expected_records} manifest={record_count}"
        )

    compiled_abi_reusable = (
        not force_recompile
        and _try_reuse_direct_final_runtime(
            manifest_path=manifest_path,
            system_root=system_root,
            force_recompile=False,
        )
        is not None
    )

    if not compiled_abi_reusable:
        if force_download or not _inputs_match_manifest(input_root, manifest_path):
            if gh is None:
                gh = _require_gh()
            _gh_download(
                gh,
                release_tag=release_tag,
                repo=repo,
                input_root=input_root,
                patterns=["manifest.json", asset_pattern, "mcp-runtime-support.jsonl.gz"],
            )
            downloaded = True
            manifest_path = _find_manifest(input_root)
            input_root = manifest_path.parent

    result = compile_direct_final_runtime(
        manifest_path=manifest_path,
        input_root=input_root,
        system_root=system_root,
        work_root=work_root,
        semantic_shard_size=semantic_shard_size,
        force_recompile=force_recompile,
    )
    companions_linked = _link_system_companions(dest_system_root=system_root)
    manifest_sha = _sha(manifest_path)
    system_root_resolved = system_root.resolve()
    return {
        "reused": bool(result.get("reused")),
        "downloaded": downloaded,
        "source_runtime_records": int(result.get("source_runtime_records") or 0),
        "semantic_records": int(result.get("semantic_records") or 0),
        "source_manifest_sha256": manifest_sha,
        "system_root": str(system_root_resolved),
        "DJPMCP_SYSTEM_DICT_DIR": str(system_root_resolved),
        "companions_linked": companions_linked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Direct Final runtime from GitHub Release")
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--expected-records", type=int, required=True)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--asset-pattern", default=DEFAULT_ASSET_PATTERN)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--system-root", type=Path, default=DEFAULT_SYSTEM_ROOT)
    parser.add_argument("--work-root", type=Path, default=DEFAULT_WORK_ROOT)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--force-recompile", action="store_true")
    parser.add_argument("--semantic-shard-size", type=int, default=10000)
    args = parser.parse_args()
    payload = prepare_direct_final_runtime(
        release_tag=args.release_tag,
        expected_records=args.expected_records,
        repo=args.repo,
        asset_pattern=args.asset_pattern,
        input_root=args.input_root,
        system_root=args.system_root,
        work_root=args.work_root,
        force_download=args.force_download,
        force_recompile=args.force_recompile,
        semantic_shard_size=args.semantic_shard_size,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
