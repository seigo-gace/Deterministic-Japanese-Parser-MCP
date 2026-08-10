#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import warnings

from unified_semantic_data.canonical_dictionary import (
    compile_canonical_dictionary,
    validate_compiled_dictionary_root,
)
from unified_semantic_data.canonical_distribution import compile_public_dictionary_view
from unified_semantic_data.canonical_evidence import compile_evidence_enriched_dictionary
from unified_semantic_data.canonical_meaning_provenance import compile_meaning_provenance_view
from unified_semantic_data.canonical_runtime_projection import (
    compile_runtime_projection,
    validate_runtime_projection,
)
from unified_semantic_data.factory_foundation import (
    FOUNDATION_VERSION,
    build_foundation_assets,
    can_reuse_pipeline,
    content_fingerprint,
    write_factory_state,
)
from unified_semantic_data.pipeline import build_review_assets, check_determinism, compile_approved
from unified_semantic_data.semantic_labeler import (
    build_semantic_enrichment_queue,
    require_all_meanings_complete,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPEN_LEXICON_ROOT = ROOT / "dictionaries/system/lexicon.d"
DEFAULT_CONTEXT_ROOT = ROOT / "research/context_collection/expansion_v3"
DEFAULT_PACK_ROOTS = (
    ROOT / "dictionaries/domain_packs",
    ROOT / "dictionaries/user_packs",
)
DEFAULT_OUTPUT_ROOT = ROOT / "reports/unified-semantic-data"
DEFAULT_COMPILED_ROOT = ROOT / "dictionaries/system/compiled/semantic_data"
DEFAULT_CANONICAL_DICTIONARY_ROOT = ROOT / "dictionaries/system/compiled/canonical_dictionary"
DEFAULT_PROVENANCE_DICTIONARY_ROOT = ROOT / "dictionaries/system/compiled/canonical_dictionary_provenance"
DEFAULT_CANONICAL_EVIDENCE_ROOT = ROOT / "research/canonical_evidence"
DEFAULT_ENRICHED_DICTIONARY_ROOT = ROOT / "dictionaries/system/compiled/canonical_dictionary_enriched"
DEFAULT_PUBLIC_DICTIONARY_ROOT = ROOT / "dictionaries/system/compiled/canonical_dictionary_public"
DEFAULT_CANONICAL_RUNTIME_ROOT = ROOT / "dictionaries/system/compiled/canonical_dictionary_runtime"
DEFAULT_DECISION_LEDGER = ROOT / "research/semantic_decisions"
DEFAULT_SEMANTIC_REFERENCE_ROOT = ROOT / "tools/unified_semantic_data/reference"


def _adapter_paths(args: argparse.Namespace, filename: str) -> list[Path]:
    return [root / filename for root in args.adapter_output_root if (root / filename).is_file()]


def _semantic_reference_inputs(args: argparse.Namespace) -> list[Path]:
    return [*args.semantic_reference_root, *_adapter_paths(args, "semantic-reference.jsonl")]


def _canonical_evidence_inputs(args: argparse.Namespace) -> list[Path]:
    return [*args.canonical_evidence_root, *_adapter_paths(args, "canonical-evidence.jsonl")]


def _adapter_lexical_inputs(args: argparse.Namespace) -> list[Path]:
    return _adapter_paths(args, "lexical-candidates.jsonl")


def _link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _stage_open_lexicon_root(args: argparse.Namespace) -> Path:
    """Stage existing open lexicon with adapter-generated new-word candidates."""
    adapter_files = _adapter_lexical_inputs(args)
    if not adapter_files:
        return args.open_lexicon_root
    if args.review_seed is not None:
        raise ValueError(
            "ADAPTER_LEXICAL_REVIEW_BOUNDARY: --review-seed cannot be combined with "
            "adapter lexical candidates; new words must pass the normal lexical and "
            "semantic Decision Ledger review lane"
        )
    stage = args.output_root / ".factory-inputs" / "open-lexicon"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True, exist_ok=True)
    if args.open_lexicon_root.exists():
        base_paths = sorted(
            [
                *args.open_lexicon_root.rglob("*.jsonl"),
                *args.open_lexicon_root.rglob("*.jsonl.gz"),
            ],
            key=str,
        )
        for path in base_paths:
            _link_or_copy(path, stage / "base" / path.relative_to(args.open_lexicon_root))
    for index, path in enumerate(sorted(adapter_files, key=str), 1):
        _link_or_copy(path, stage / "adapter" / f"{index:03d}-{path.name}")
    return stage


def _pipeline_fingerprint_inputs(args: argparse.Namespace) -> list[tuple[str, Path]]:
    inputs: list[tuple[str, Path]] = []
    if args.review_seed:
        inputs.append(("review-seed", args.review_seed))
    else:
        inputs.extend([("open-lexicon", args.open_lexicon_root), ("context", args.context_root)])
    inputs.extend((f"pack-{index:02d}", path) for index, path in enumerate(args.pack_root, 1))
    inputs.extend(
        (f"semantic-reference-{index:02d}", path)
        for index, path in enumerate(args.semantic_reference_root, 1)
    )
    inputs.extend(
        (f"canonical-evidence-{index:02d}", path)
        for index, path in enumerate(args.canonical_evidence_root, 1)
    )
    inputs.extend(
        (f"adapter-output-{index:02d}", path)
        for index, path in enumerate(args.adapter_output_root, 1)
    )
    inputs.append(("decision-ledger", args.decision_root))
    inputs.extend(
        [
            ("baseline-metaphors", args.system_root / "metaphors"),
            ("baseline-synonyms", args.system_root / "synonyms.yaml"),
            ("baseline-synonyms-d", args.system_root / "synonyms.d"),
            ("baseline-language-features", args.system_root / "language_features.d"),
            ("code-entrypoint", Path(__file__)),
            ("code-common", ROOT / "tools/unified_semantic_data/common.py"),
            ("code-pipeline", ROOT / "tools/unified_semantic_data/pipeline.py"),
            ("code-review", ROOT / "tools/unified_semantic_data/review.py"),
            ("code-factory-foundation", ROOT / "tools/unified_semantic_data/factory_foundation.py"),
            ("code-semantic-labeler", ROOT / "tools/unified_semantic_data/semantic_labeler.py"),
            ("code-canonical-dictionary", ROOT / "tools/unified_semantic_data/canonical_dictionary.py"),
            ("code-canonical-meaning-provenance", ROOT / "tools/unified_semantic_data/canonical_meaning_provenance.py"),
            ("code-canonical-evidence", ROOT / "tools/unified_semantic_data/canonical_evidence.py"),
            ("code-license-policy", ROOT / "tools/unified_semantic_data/license_policy.py"),
            ("code-canonical-distribution", ROOT / "tools/unified_semantic_data/canonical_distribution.py"),
            ("code-canonical-runtime-projection", ROOT / "tools/unified_semantic_data/canonical_runtime_projection.py"),
            ("code-source-adapter-contract", ROOT / "tools/unified_semantic_data/source_adapter_contract.py"),
            ("code-bulk-review", ROOT / "tools/bulk_review_station.py"),
        ]
    )
    return inputs


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _compile_dictionary_if_needed(args: argparse.Namespace) -> dict:
    if (args.canonical_dictionary_root / "manifest.json").is_file():
        return validate_compiled_dictionary_root(args.canonical_dictionary_root)
    return compile_canonical_dictionary(args.output_root, args.canonical_dictionary_root, shard_size=args.shard_size)


def _compile_provenance_dictionary_if_needed(args: argparse.Namespace) -> dict:
    if (args.provenance_dictionary_root / "manifest.json").is_file():
        manifest = validate_compiled_dictionary_root(args.provenance_dictionary_root)
        if manifest.get("dictionary_view") != "meaning-provenance-refined":
            raise ValueError("canonical meaning-provenance dictionary view mismatch")
        return manifest
    return compile_meaning_provenance_view(
        args.output_root,
        args.canonical_dictionary_root,
        args.provenance_dictionary_root,
        shard_size=args.shard_size,
    )


def _compile_enriched_dictionary_if_needed(args: argparse.Namespace) -> dict:
    if (args.enriched_dictionary_root / "manifest.json").is_file():
        manifest = validate_compiled_dictionary_root(args.enriched_dictionary_root)
        if manifest.get("dictionary_view") != "evidence-enriched":
            raise ValueError("canonical evidence-enriched dictionary view mismatch")
        return manifest
    return compile_evidence_enriched_dictionary(
        args.provenance_dictionary_root,
        _canonical_evidence_inputs(args),
        args.enriched_dictionary_root,
        shard_size=args.shard_size,
    )


def _compile_public_dictionary_if_needed(args: argparse.Namespace) -> dict:
    if (args.public_dictionary_root / "manifest.json").is_file():
        manifest = validate_compiled_dictionary_root(args.public_dictionary_root)
        if manifest.get("distribution_view") != "public-compatible":
            raise ValueError("canonical public dictionary distribution view mismatch")
        return manifest
    return compile_public_dictionary_view(args.enriched_dictionary_root, args.public_dictionary_root, shard_size=args.shard_size)


def _compile_canonical_runtime_if_needed(args: argparse.Namespace) -> dict:
    if (args.canonical_runtime_root / "manifest.json").is_file():
        return validate_runtime_projection(args.canonical_runtime_root)
    return compile_runtime_projection(args.public_dictionary_root, args.canonical_runtime_root, shard_size=args.shard_size)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--open-lexicon-root", type=Path, default=DEFAULT_OPEN_LEXICON_ROOT)
    parser.add_argument("--context-root", type=Path, default=DEFAULT_CONTEXT_ROOT)
    parser.add_argument("--pack-root", type=Path, action="append", default=[])
    parser.add_argument("--semantic-reference-root", type=Path, action="append", default=[])
    parser.add_argument("--canonical-evidence-root", type=Path, action="append", default=[])
    parser.add_argument(
        "--adapter-output-root",
        type=Path,
        action="append",
        default=[],
        help=(
            "output root created by source_adapter_contract.py; lexical candidates, "
            "semantic references and canonical evidence are routed automatically"
        ),
    )
    parser.add_argument("--system-root", type=Path, default=ROOT / "dictionaries/system")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--compiled-root", type=Path, default=DEFAULT_COMPILED_ROOT)
    parser.add_argument("--canonical-dictionary-root", type=Path, default=DEFAULT_CANONICAL_DICTIONARY_ROOT)
    parser.add_argument("--provenance-dictionary-root", type=Path, default=DEFAULT_PROVENANCE_DICTIONARY_ROOT)
    parser.add_argument("--enriched-dictionary-root", type=Path, default=DEFAULT_ENRICHED_DICTIONARY_ROOT)
    parser.add_argument("--public-dictionary-root", type=Path, default=DEFAULT_PUBLIC_DICTIONARY_ROOT)
    parser.add_argument("--canonical-runtime-root", type=Path, default=DEFAULT_CANONICAL_RUNTIME_ROOT)
    parser.add_argument("--shard-size", type=int, default=10000)
    parser.add_argument("--foundation-partitions", type=int, default=256)
    parser.add_argument("--force-rebuild", action="store_true")
    parser.add_argument("--review-batch-size", type=int, default=None)
    parser.add_argument("--bulk-review", action="store_true")
    parser.add_argument("--review-seed", type=Path, help="immutable 125000-record PR #26 Review Queue input")
    parser.add_argument(
        "--decision-ledger",
        "--decision-root",
        dest="decision_root",
        type=Path,
        default=DEFAULT_DECISION_LEDGER,
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--compile-approved", action="store_true")
    parser.add_argument("--require-review-complete", action="store_true")
    args = parser.parse_args()

    if not args.pack_root:
        args.pack_root = list(DEFAULT_PACK_ROOTS)
    if not args.semantic_reference_root:
        args.semantic_reference_root = [DEFAULT_SEMANTIC_REFERENCE_ROOT]
    if not args.canonical_evidence_root:
        args.canonical_evidence_root = [DEFAULT_CANONICAL_EVIDENCE_ROOT]
    if args.shard_size < 100:
        raise ValueError("shard-size must be at least 100")
    if not 1 <= args.foundation_partitions <= 4096:
        raise ValueError("foundation-partitions must be between 1 and 4096")
    if args.bulk_review and args.review_batch_size is not None:
        parser.error("--bulk-review and --review-batch-size cannot be used together")

    legacy_review = args.review_batch_size is not None
    if legacy_review:
        if not 1 <= args.review_batch_size <= 20:
            raise ValueError("review-batch-size must be between 1 and 20")
        warnings.warn(
            "--review-batch-size is deprecated; omit it or use --bulk-review",
            DeprecationWarning,
            stacklevel=2,
        )
    else:
        args.bulk_review = True
        args.review_batch_size = 20

    if args.check:
        result = check_determinism(args)
    else:
        fingerprint = content_fingerprint(
            _pipeline_fingerprint_inputs(args),
            parameters={
                "foundation_version": FOUNDATION_VERSION,
                "shard_size": args.shard_size,
                "foundation_partitions": args.foundation_partitions,
                "bulk_review": args.bulk_review,
                "review_batch_size": args.review_batch_size,
                "compile_approved": args.compile_approved,
                "source_adapter_schema": "1.1.0",
                "canonical_dictionary_schema": "1.0.0",
                "meaning_provenance_view": "1.1.0",
                "canonical_evidence_schema": "1.0.0",
                "public_dictionary_view": "1.2.0",
                "canonical_runtime_projection": "1.0.0",
            },
        )
        state_path = args.output_root / ".factory-state.json"
        if (
            not args.force_rebuild
            and can_reuse_pipeline(
                state_path,
                input_fingerprint=fingerprint,
                review_root=args.output_root,
                compiled_root=args.compiled_root,
                require_compiled=args.compile_approved,
            )
        ):
            review = _load_json(args.output_root / "manifest.json")
            foundation = _load_json(args.output_root / "factory-foundation/manifest.json")
            semantic_enrichment = _load_json(args.output_root / "semantic-enrichment-report.json")
            result = {
                "status": "REUSED",
                "input_fingerprint": fingerprint,
                "review": review,
                "semantic_enrichment": semantic_enrichment,
                "factory_foundation": foundation,
            }
            if args.compile_approved:
                require_all_meanings_complete(semantic_enrichment)
                result["compiled"] = _load_json(args.compiled_root / "manifest.json")
                result["canonical_dictionary"] = _compile_dictionary_if_needed(args)
                result["canonical_dictionary_provenance"] = _compile_provenance_dictionary_if_needed(args)
                result["canonical_dictionary_enriched"] = _compile_enriched_dictionary_if_needed(args)
                result["public_dictionary"] = _compile_public_dictionary_if_needed(args)
                result["canonical_runtime_projection"] = _compile_canonical_runtime_if_needed(args)
        else:
            open_lexicon_root = _stage_open_lexicon_root(args)
            review = build_review_assets(
                open_lexicon_root=open_lexicon_root,
                context_root=args.context_root,
                pack_roots=args.pack_root,
                output_root=args.output_root,
                system_root=args.system_root,
                decision_root=args.decision_root,
                review_batch_size=args.review_batch_size,
                review_seed=args.review_seed,
                bulk_review=args.bulk_review,
            )
            semantic_enrichment = build_semantic_enrichment_queue(
                args.output_root / "review-records.jsonl",
                args.output_root,
                reference_roots=_semantic_reference_inputs(args),
            )
            result = {
                "status": "WRITTEN",
                "input_fingerprint": fingerprint,
                "review": review,
                "semantic_enrichment": semantic_enrichment,
            }
            if args.compile_approved:
                require_all_meanings_complete(semantic_enrichment)
                result["compiled"] = compile_approved(args.output_root, args.compiled_root, shard_size=args.shard_size)
                result["canonical_dictionary"] = compile_canonical_dictionary(
                    args.output_root, args.canonical_dictionary_root, shard_size=args.shard_size
                )
                result["canonical_dictionary_provenance"] = compile_meaning_provenance_view(
                    args.output_root,
                    args.canonical_dictionary_root,
                    args.provenance_dictionary_root,
                    shard_size=args.shard_size,
                )
                result["canonical_dictionary_enriched"] = compile_evidence_enriched_dictionary(
                    args.provenance_dictionary_root,
                    _canonical_evidence_inputs(args),
                    args.enriched_dictionary_root,
                    shard_size=args.shard_size,
                )
                result["public_dictionary"] = compile_public_dictionary_view(
                    args.enriched_dictionary_root, args.public_dictionary_root, shard_size=args.shard_size
                )
                result["canonical_runtime_projection"] = compile_runtime_projection(
                    args.public_dictionary_root, args.canonical_runtime_root, shard_size=args.shard_size
                )
            foundation = build_foundation_assets(args.output_root, partition_count=args.foundation_partitions)
            result["factory_foundation"] = foundation
            write_factory_state(
                state_path,
                input_fingerprint=fingerprint,
                foundation_manifest=foundation,
                compiled=args.compile_approved,
            )

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    review = result.get("review") or {}
    if args.require_review_complete and review.get("review_queue_records", 0):
        if review.get("bulk_review_job_id"):
            print(
                "REVIEW_REQUIRED: "
                f"{review['review_queue_records']} records in bulk review job "
                f"{review['bulk_review_job_id']}; add explicit Decision Ledger entries.",
            )
        else:
            print(
                "REVIEW_REQUIRED: "
                f"{review['review_queue_records']} records in "
                f"{review['review_batch_count']} batches; add explicit Decision Ledger entries.",
            )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
