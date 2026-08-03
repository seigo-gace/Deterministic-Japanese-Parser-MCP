#!/usr/bin/env python3
"""Transactionally promote approved dictionary proposals into runtime packs."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
for item in (ROOT / "src", TOOLS_ROOT):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from deterministic_japanese_parser_mcp.config import Settings
from deterministic_japanese_parser_mcp.dictionaries import DictionaryBundle
from dictionary_supply.common import LexiconRecord
from dictionary_supply.proposals import load_bundle

_BATCH = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
_PRIVATE_BUCKETS = {"private-review-only", "license-review-required"}


def license_bucket(license_expression: str) -> str:
    value = (license_expression or "").upper()
    if "PRIVATE" in value:
        return "private-review-only"
    if "CC0" in value:
        return "cc0"
    if "APACHE" in value:
        return "apache-2.0"
    if "CC-BY-SA" in value or "CC BY-SA" in value:
        return "cc-by-sa"
    if "GPL" in value or "GFDL" in value or "LGPL" in value:
        return "copyleft-other"
    return "license-review-required"


def semver_patch(value: str) -> str:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ValueError(f"cannot patch non-semver version: {value}")
    major, minor, patch = (int(item) for item in match.groups())
    return f"{major}.{minor}.{patch + 1}"


def evidence_buckets(proposal: dict) -> set[str]:
    evidence = proposal.get("evidence", [])
    if not evidence:
        raise ValueError(
            f"approved proposal has no source evidence: {proposal.get('proposal_id')}"
        )
    buckets: set[str] = set()
    for item in evidence:
        if not item.get("dataset") or not item.get("version"):
            raise ValueError(
                f"source dataset/version is required: {proposal.get('proposal_id')}"
            )
        buckets.add(license_bucket(item.get("license", "")))
    return buckets


def approved_proposals(bundle: dict) -> list[dict]:
    output = [
        item
        for item in bundle.get("proposals", [])
        if item.get("status") == "approved"
    ]
    if not output:
        raise ValueError("review bundle contains no approved proposals")
    for item in output:
        proposal_id = item.get("proposal_id")
        if not item.get("review", {}).get("notes"):
            raise ValueError(
                f"approved proposal has no review notes: {proposal_id}"
            )
        blocked = evidence_buckets(item).intersection(_PRIVATE_BUCKETS)
        if blocked:
            raise ValueError(
                "proposal source cannot enter public runtime dictionaries: "
                f"{proposal_id}: {sorted(blocked)}"
            )
    return output


def source_manifest(batch_id: str, proposals: list[dict]) -> dict:
    sources: dict[tuple, dict] = {}
    licenses = Counter()
    kinds = Counter()
    for proposal in proposals:
        kinds[proposal["kind"]] += 1
        for item in proposal.get("evidence", []):
            key = (
                item.get("dataset"),
                item.get("version"),
                item.get("license"),
                item.get("source_sha256"),
            )
            sources[key] = item
            licenses[item.get("license", "UNKNOWN")] += 1
    return {
        "schema_version": "1.0.0",
        "batch_id": batch_id,
        "proposal_count": len(proposals),
        "proposal_kinds": dict(sorted(kinds.items())),
        "proposal_ids": [item["proposal_id"] for item in proposals],
        "licenses": dict(sorted(licenses.items())),
        "sources": list(sources.values()),
    }


def gold_cases(proposal: dict, sequence_start: int) -> list[dict]:
    review = proposal.get("review", {})
    output: list[dict] = []
    sequence = sequence_start
    for variant, examples in (
        ("positive", review.get("positive_examples", [])),
        ("negative", review.get("negative_examples", [])),
    ):
        for example in examples:
            if isinstance(example, str):
                text = example
                if proposal["kind"] == "metaphor":
                    expected = (
                        {"metaphors": [proposal["payload"]["expression"]]}
                        if variant == "positive"
                        else {"metaphors": []}
                    )
                elif proposal["kind"] == "rule":
                    intent = proposal["payload"]["intent"]
                    expected = (
                        {"intents": [intent]}
                        if variant == "positive"
                        else {"forbidden_task_intents": [intent]}
                    )
                else:
                    continue
                request = {}
            else:
                text = example.get("text", "")
                expected = example.get("expected", {})
                request = example.get("request", {})
            if not text or not expected:
                raise ValueError(
                    f"review example requires text/expected: {proposal['proposal_id']}"
                )
            sequence += 1
            output.append({
                "id": f"AUTO-{sequence:06d}",
                "proposal_id": proposal["proposal_id"],
                "variant": variant,
                "text": text,
                "request": request,
                "expected": expected,
            })
    return output


def prepare_files(
    root: Path,
    batch_id: str,
    proposals: list[dict],
) -> dict[Path, str]:
    files: dict[Path, str] = {}
    lexicon_by_license: dict[str, list[dict]] = {}
    metaphor_entries: list[dict] = []
    rules: dict[str, list[dict]] = {}
    synonym_groups: dict[str, list[str]] = {}
    gold: list[dict] = []

    for proposal in proposals:
        proposal_id = proposal["proposal_id"]
        kind = proposal["kind"]
        payload = proposal.get("payload", {})
        blocked = evidence_buckets(proposal).intersection(_PRIVATE_BUCKETS)
        if blocked:
            raise ValueError(
                f"source cannot be promoted: {proposal_id}: {sorted(blocked)}"
            )

        if kind == "lexicon":
            record = LexiconRecord.from_dict(payload["record"])
            record.review_status = "approved"
            bucket = license_bucket(record.source.license)
            if bucket in _PRIVATE_BUCKETS:
                raise ValueError(
                    "source cannot be promoted to public runtime pack: "
                    f"{record.record_id}: {record.source.license}"
                )
            lexicon_by_license.setdefault(bucket, []).append(record.to_dict())
        elif kind == "metaphor":
            entry = copy.deepcopy(payload)
            entry["version"] = batch_id
            entry["source_proposal_id"] = proposal_id
            entry["source_evidence"] = proposal.get("evidence", [])
            metaphor_entries.append(entry)
            gold.extend(gold_cases(proposal, len(gold)))
        elif kind == "rule":
            intent = payload["intent"]
            rule = copy.deepcopy(payload["rule"])
            rule["source_proposal_id"] = proposal_id
            rule["source_evidence"] = proposal.get("evidence", [])
            rules.setdefault(intent, []).append(rule)
            gold.extend(gold_cases(proposal, len(gold)))
        elif kind == "synonym":
            canonical = payload["canonical"]
            bucket = synonym_groups.setdefault(canonical, [])
            for surface in payload.get("surfaces", []):
                if surface and surface != canonical and surface not in bucket:
                    bucket.append(surface)
        else:
            raise ValueError(f"unsupported promotion kind: {kind}")

    for bucket, records in lexicon_by_license.items():
        path = root / "dictionaries/system/lexicon.d" / bucket / f"{batch_id}.jsonl"
        lines = [
            json.dumps(item, ensure_ascii=False, sort_keys=True)
            for item in records
        ]
        files[path] = "\n".join(lines) + "\n"
    if metaphor_entries:
        path = root / "dictionaries/system/metaphors" / f"generated-{batch_id}.json"
        files[path] = json.dumps(
            {"version": batch_id, "entries": metaphor_entries},
            ensure_ascii=False,
            indent=2,
        ) + "\n"
    if rules:
        path = root / "dictionaries/system/rules" / f"generated-{batch_id}.yaml"
        files[path] = yaml.safe_dump(
            {"version": batch_id, "intents": rules},
            allow_unicode=True,
            sort_keys=False,
        )
    if synonym_groups:
        path = root / "dictionaries/system/synonyms.d" / f"generated-{batch_id}.yaml"
        files[path] = yaml.safe_dump(
            {"version": batch_id, "groups": synonym_groups},
            allow_unicode=True,
            sort_keys=False,
        )
    if gold:
        path = root / "tests/gold" / f"generated-{batch_id}.json"
        files[path] = json.dumps(
            {"version": batch_id, "cases": gold},
            ensure_ascii=False,
            indent=2,
        ) + "\n"

    files[root / "dictionaries/sources" / f"{batch_id}.json"] = (
        json.dumps(
            source_manifest(batch_id, proposals),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    return files


def effective_counts(root: Path) -> dict[str, int]:
    settings = Settings(
        system_dict_dir=root / "dictionaries/system",
        user_dict_dir=root / "dictionaries/user",
        log_path=root / "logs/parser.jsonl",
    )
    bundle = DictionaryBundle(settings.system_dict_dir, settings.user_dict_dir)
    rule_count = sum(
        len(items)
        for items in bundle.rules.get("intents", {}).values()
    )
    gold_ids: set[str] = set()
    for path in sorted((root / "tests/gold").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for item in doc.get("cases", []):
            gold_ids.add(item["id"])
    workflow_count = sum(
        1
        for item in bundle.templates.get("templates", [])
        if item.get("intent") == "workflow"
    )
    return {
        "metaphors": len(bundle.metaphors.get("entries", [])),
        "rules": rule_count,
        "synonym_groups": len(bundle.synonyms.get("groups", {})),
        "templates": len(bundle.templates.get("templates", [])),
        "workflows": workflow_count,
        "gold": len(gold_ids),
        "lexicon_records": len(bundle.lexicon.get("entries", [])),
    }


def patch_version_key(text: str, key: str) -> str:
    pattern = rf'("{re.escape(key)}": ")(\d+\.\d+\.\d+)(")'
    match = re.search(pattern, text)
    if not match:
        raise ValueError(f"version key not found: {key}")
    return re.sub(
        pattern,
        lambda item: item.group(1) + semver_patch(item.group(2)) + item.group(3),
        text,
        count=1,
    )


def sync_notice(root: Path, batch_id: str, proposals: list[dict]) -> None:
    notice_path = root / "NOTICE.md"
    notice = notice_path.read_text(encoding="utf-8")
    marker = f"<!-- dictionary-batch:{batch_id} -->"
    if marker in notice:
        raise ValueError(f"NOTICE already contains batch: {batch_id}")
    manifest = source_manifest(batch_id, proposals)
    lines = [
        "",
        marker,
        f"## Dictionary data batch `{batch_id}`",
        "",
        "This batch contains reviewed data derived from the following sources. "
        "The data remains governed by the recorded source licenses.",
        "",
    ]
    for source in manifest["sources"]:
        lines.append(
            "- "
            + " | ".join(
                str(value)
                for value in (
                    source.get("dataset"),
                    source.get("version"),
                    source.get("license"),
                    source.get("attribution"),
                )
                if value
            )
        )
    notice_path.write_text(
        notice.rstrip() + "\n" + "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def sync_metadata(
    root: Path,
    counts: dict[str, int],
    proposals: list[dict],
    batch_id: str,
) -> None:
    kinds = {item["kind"] for item in proposals}
    manifest_path = root / "dictionaries/system/metaphors/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metaphor_entries"] = counts["metaphors"]
    manifest["intent_patterns"] = counts["rules"]
    manifest["synonym_groups"] = counts["synonym_groups"]
    manifest["task_templates"] = counts["templates"]
    manifest["workflow_templates"] = counts["workflows"]
    manifest["gold_cases"] = counts["gold"]
    manifest["open_lexicon_records"] = counts["lexicon_records"]
    manifest["dictionary_version"] = semver_patch(
        manifest["dictionary_version"]
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    readme_path = root / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    replacements = {
        r"(\| 比喩・慣用・語用表現 \| \*\*)\d+(\*\* \|)": counts["metaphors"],
        r"(\| 決定論的Intent Pattern \| \*\*)\d+(\*\* \|)": counts["rules"],
        r"(\| 類義語Canonical Group \| \*\*)\d+(\*\* \|)": counts["synonym_groups"],
        r"(\| Task / Workflow Template \| \*\*)\d+(\*\* \|)": counts["templates"],
        r"(\| Workflow \| \*\*)\d+(\*\* \|)": counts["workflows"],
        r"(\| Gold Corpus \| \*\*)\d+(\*\* \|)": counts["gold"],
        r"(\| Open lexical records \| \*\*)\d+(\*\* \|)": counts["lexicon_records"],
        r"(\| Metaphor, idiom, and pragmatic expressions \| \*\*)\d+(\*\* \|)": counts["metaphors"],
        r"(\| Deterministic intent patterns \| \*\*)\d+(\*\* \|)": counts["rules"],
        r"(\| Canonical synonym groups \| \*\*)\d+(\*\* \|)": counts["synonym_groups"],
        r"(\| Task / workflow templates \| \*\*)\d+(\*\* \|)": counts["templates"],
        r"(\| Workflows \| \*\*)\d+(\*\* \|)": counts["workflows"],
        r"(\| Gold Corpus cases \| \*\*)\d+(\*\* \|)": counts["gold"],
    }
    for pattern, value in replacements.items():
        readme, changed = re.subn(pattern, rf"\g<1>{value}\g<2>", readme)
        if changed != 1:
            raise ValueError(
                f"README count marker mismatch: {pattern}: changed={changed}"
            )
    readme_path.write_text(readme, encoding="utf-8")

    version_path = root / "src/deterministic_japanese_parser_mcp/version.py"
    version_text = version_path.read_text(encoding="utf-8")
    version_text = patch_version_key(version_text, "dictionary_version")
    if "rule" in kinds:
        version_text = patch_version_key(version_text, "rule_version")
    if "metaphor" in kinds:
        version_text = patch_version_key(
            version_text,
            "metaphor_dictionary_version",
        )
    version_path.write_text(version_text, encoding="utf-8")
    sync_notice(root, batch_id, proposals)


def run_checks(root: Path, *, performance: bool) -> None:
    commands = [
        [sys.executable, "tools/lexicon_validator.py"],
        [sys.executable, "tools/validator.py"],
        [sys.executable, "-m", "pytest"],
        [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "src",
            "tools",
            "scripts",
            "tests",
        ],
    ]
    if performance:
        commands.extend([
            [sys.executable, "scripts/benchmark.py", "--check", "--rounds", "50"],
            [
                sys.executable,
                "scripts/performance_contract.py",
                "--check",
                "--rounds",
                "50",
                "--stdio-rounds",
                "30",
                "--scale",
                "20",
                "--max-ready-ms",
                "10",
            ],
            [
                sys.executable,
                "scripts/astera_latency_contract.py",
                "--check",
                "--rounds",
                "50",
                "--stdio-rounds",
                "30",
                "--target-ms",
                "10",
                "--hard-ms",
                "50",
            ],
        ])
    for command in commands:
        subprocess.run(command, cwd=root, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--performance", action="store_true")
    args = parser.parse_args()
    if not _BATCH.fullmatch(args.batch_id):
        parser.error("batch-id must match [a-z0-9][a-z0-9._-]{1,63}")

    root = args.repo_root.resolve()
    bundle = load_bundle(args.bundle)
    proposals = approved_proposals(bundle)
    files = prepare_files(root, args.batch_id, proposals)
    print(
        "PROMOTION PLAN: "
        f"batch={args.batch_id} approved={len(proposals)} files={len(files)}"
    )
    for path in sorted(files):
        print("-", path.relative_to(root))
    if not args.apply:
        print("DRY RUN ONLY: pass --apply to write and validate")
        return 0

    touched = set(files)
    touched.update({
        root / "dictionaries/system/metaphors/manifest.json",
        root / "README.md",
        root / "NOTICE.md",
        root / "src/deterministic_japanese_parser_mcp/version.py",
    })
    backup: dict[Path, bytes | None] = {
        path: path.read_bytes() if path.exists() else None
        for path in touched
    }
    try:
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                raise ValueError(f"promotion target already exists: {path}")
            path.write_text(content, encoding="utf-8")
        counts = effective_counts(root)
        sync_metadata(root, counts, proposals, args.batch_id)
        run_checks(root, performance=args.performance)
    except Exception:
        for path, content in backup.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        raise

    print(f"PROMOTION OK: batch={args.batch_id} counts={counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
