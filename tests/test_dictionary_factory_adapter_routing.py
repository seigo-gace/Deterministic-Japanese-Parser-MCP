from __future__ import annotations

from argparse import Namespace
import gzip
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import unified_semantic_data_pipeline as factory  # noqa: E402


def _args(tmp_path: Path, *, review_seed: Path | None = None) -> Namespace:
    base = tmp_path / "base"
    base.mkdir()
    (base / "existing.jsonl").write_text('{"record_id":"BASE"}\n', encoding="utf-8")
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "lexical-candidates.jsonl").write_text(
        '{"record_id":"ADAPTER-NEW"}\n', encoding="utf-8"
    )
    (adapter / "semantic-reference.jsonl").write_text(
        '{"id":"REF"}\n', encoding="utf-8"
    )
    (adapter / "canonical-evidence.jsonl").write_text(
        '{"evidence_id":"EVIDENCE"}\n', encoding="utf-8"
    )
    return Namespace(
        open_lexicon_root=base,
        adapter_output_root=[adapter],
        semantic_reference_root=[tmp_path / "existing-reference"],
        canonical_evidence_root=[tmp_path / "existing-evidence"],
        output_root=tmp_path / "output",
        review_seed=review_seed,
    )


def test_adapter_outputs_route_to_three_factory_lanes(tmp_path: Path) -> None:
    args = _args(tmp_path)
    semantic = factory._semantic_reference_inputs(args)
    evidence = factory._canonical_evidence_inputs(args)
    assert semantic[-1].name == "semantic-reference.jsonl"
    assert evidence[-1].name == "canonical-evidence.jsonl"

    staged = factory._stage_open_lexicon_root(args)
    files = sorted(path.relative_to(staged).as_posix() for path in staged.rglob("*.jsonl"))
    assert files == ["adapter/001-lexical-candidates.jsonl", "base/existing.jsonl"]
    assert (staged / "adapter/001-lexical-candidates.jsonl").read_text(
        encoding="utf-8"
    ) == '{"record_id":"ADAPTER-NEW"}\n'


def test_adapter_new_words_cannot_use_historical_review_seed_shortcut(tmp_path: Path) -> None:
    seed = tmp_path / "review-seed.jsonl"
    seed.write_text("{}\n", encoding="utf-8")
    args = _args(tmp_path, review_seed=seed)
    try:
        factory._stage_open_lexicon_root(args)
    except ValueError as exc:
        assert "ADAPTER_LEXICAL_REVIEW_BOUNDARY" in str(exc)
    else:
        raise AssertionError("new adapter words must not inherit review-seed lexical approval")


def test_compressed_adapter_outputs_route_without_plain_duplicates(tmp_path: Path) -> None:
    args = _args(tmp_path)
    adapter = args.adapter_output_root[0]
    for name in (
        "lexical-candidates.jsonl",
        "semantic-reference.jsonl",
        "canonical-evidence.jsonl",
    ):
        payload = (adapter / name).read_bytes()
        (adapter / name).unlink()
        with gzip.open(adapter / f"{name}.gz", "wb") as handle:
            handle.write(payload)
    assert factory._semantic_reference_inputs(args)[-1].name.endswith(".jsonl.gz")
    assert factory._canonical_evidence_inputs(args)[-1].name.endswith(".jsonl.gz")
    assert factory._adapter_lexical_inputs(args)[-1].name.endswith(".jsonl.gz")
