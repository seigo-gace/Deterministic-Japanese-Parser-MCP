from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _collected_entry() -> dict:
    return {
        "entries": [
            {
                "entry_id": "TEST-SLANG-001",
                "feature_type": "slang",
                "surfaces": [
                    {"value": "テスト語", "match_mode": "token"}
                ],
                "interpretations": [
                    {
                        "interpretation_id": "test-slang.meaning",
                        "label": "検証用の意味",
                        "parameters": {
                            "polarity": "neutral",
                            "intensity": 1,
                        },
                    }
                ],
                "register": {
                    "labels": ["slang"],
                    "formality": "casual",
                },
                "fallback_status": "AMBIGUOUS",
                "risk_class": "social",
                "evidence_score": 80,
                "evidence": [
                    {
                        "evidence_id": "TEST-EVIDENCE-001",
                        "dataset": "test dataset",
                        "version": "1",
                        "license": "CC0-1.0",
                        "source_id": "row-1",
                    }
                ],
            }
        ]
    }


def _build_bundle(tmp_path: Path) -> Path:
    source = tmp_path / "collected.yaml"
    bundle = tmp_path / "bundle.yaml"
    source.write_text(
        yaml.safe_dump(_collected_entry(), allow_unicode=True),
        encoding="utf-8",
    )
    subprocess.run(
        [
            sys.executable,
            "tools/language_supply.py",
            "--input",
            str(source),
            "--batch-id",
            "test-language-batch",
            "--out",
            str(bundle),
        ],
        cwd=ROOT,
        check=True,
    )
    return bundle


def test_collected_language_data_becomes_review_only_proposal(
    tmp_path: Path,
) -> None:
    bundle = yaml.safe_load(_build_bundle(tmp_path).read_text(encoding="utf-8"))
    assert bundle["counts"] == {"language_feature": 1}
    proposal = bundle["proposals"][0]
    assert proposal["kind"] == "language_feature"
    assert proposal["status"] == "needs_review"
    assert proposal["payload"]["entry_id"] == "TEST-SLANG-001"
    assert proposal["evidence"][0]["license"] == "CC0-1.0"


def test_social_language_feature_requires_boundary_and_action_review(
    tmp_path: Path,
) -> None:
    bundle_path = _build_bundle(tmp_path)
    proposal_id = yaml.safe_load(
        bundle_path.read_text(encoding="utf-8")
    )["proposals"][0]["proposal_id"]
    decisions = tmp_path / "decisions.yaml"
    decisions.write_text(
        yaml.safe_dump({
            "decisions": [
                {
                    "proposal_id": proposal_id,
                    "status": "approved",
                    "notes": ["reviewed"],
                    "positive_examples": ["テスト語だ。"],
                    "negative_examples": ["通常語だ。"],
                }
            ]
        }, allow_unicode=True),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "tools/reviewer.py",
            "--bundle",
            str(bundle_path),
            "--decisions",
            str(decisions),
            "--out",
            str(tmp_path / "reviewed.yaml"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "boundary_examples are required" in result.stderr


def test_complete_language_feature_review_is_accepted(tmp_path: Path) -> None:
    bundle_path = _build_bundle(tmp_path)
    proposal_id = yaml.safe_load(
        bundle_path.read_text(encoding="utf-8")
    )["proposals"][0]["proposal_id"]
    decisions = tmp_path / "decisions.yaml"
    reviewed = tmp_path / "reviewed.yaml"
    decisions.write_text(
        yaml.safe_dump({
            "decisions": [
                {
                    "proposal_id": proposal_id,
                    "status": "approved",
                    "notes": ["meaning and context reviewed"],
                    "positive_examples": ["テスト語だ。"],
                    "negative_examples": ["通常語だ。"],
                    "boundary_examples": ["テスト語かもしれない。"],
                    "external_action_reviewed": True,
                }
            ]
        }, allow_unicode=True),
        encoding="utf-8",
    )
    subprocess.run(
        [
            sys.executable,
            "tools/reviewer.py",
            "--bundle",
            str(bundle_path),
            "--decisions",
            str(decisions),
            "--out",
            str(reviewed),
            "--require-all-decided",
        ],
        cwd=ROOT,
        check=True,
    )
    result = yaml.safe_load(reviewed.read_text(encoding="utf-8"))
    assert result["status"] == "reviewed"
    assert result["proposals"][0]["status"] == "approved"


def test_compiler_rejects_unapproved_language_fragment(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "compiled"
    source_dir.mkdir()
    fragment = source_dir / "fragment.yaml"
    document = _collected_entry()
    document["schema_version"] = "1.0.0"
    fragment.write_text(
        yaml.safe_dump(document, allow_unicode=True),
        encoding="utf-8",
    )
    (source_dir / "approvals.yaml").write_text(
        yaml.safe_dump({
            "schema_version": "1.0.0",
            "approved_fragments": {
                "fragment.yaml": {
                    "status": "needs_review",
                    "source_sha256": "0" * 64,
                    "review_id": "not-approved",
                }
            },
        }),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "tools/compile_language_features.py",
            "--source-dir",
            str(source_dir),
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "unapproved language feature fragment" in result.stderr
