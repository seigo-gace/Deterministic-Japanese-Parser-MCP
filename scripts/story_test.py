from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine


DEFAULT_CORPUS = Path("tests/data/story_test_corpus.jsonl")
DEFAULT_OUTPUT = Path("tests/results/mcp_actual.jsonl")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            item = json.loads(raw)
            story_id = item.get("id")
            if not isinstance(story_id, str) or not story_id:
                raise ValueError(f"{path}:{line_number}: missing story id")
            if story_id in seen:
                raise ValueError(f"{path}:{line_number}: duplicate story id {story_id}")
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"{path}:{line_number}: missing story text")
            seen.add(story_id)
            items.append(item)
    if not items:
        raise ValueError(f"{path}: corpus is empty")
    return items


def _model_json(value: Any) -> Any:
    if value is None:
        return None
    return value.model_dump(mode="json")


def _language_feature_view(graph: Any) -> list[dict[str, Any]]:
    return [
        {
            "entry_id": item.entry_id,
            "feature_type": item.feature_type,
            "surface": item.surface,
            "interpretation_id": item.interpretation_id,
            "interpretation": item.interpretation,
            "parameters": item.parameters,
            "register_profile": item.register_profile,
            "status": item.status.value,
            "candidate_ids": item.candidate_ids,
            "evidence_ids": item.evidence_ids,
            "risk_class": item.risk_class,
        }
        for item in graph.language_features
    ]


def _semantic_sense_view(graph: Any) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for item in graph.propositions:
        if item.sense_id is None and not item.sense_candidates:
            continue
        values.append(
            {
                "proposition_id": item.proposition_id,
                "predicate": item.predicate,
                "value": item.value,
                "source_text": item.source_span.source_text,
                "sense_id": item.sense_id,
                "sense_label": item.sense_label,
                "sense_confidence": item.sense_confidence,
                "sense_candidates": [
                    candidate.model_dump(mode="json")
                    for candidate in item.sense_candidates
                ],
                "status": item.status.value,
                "inference_sources": item.inference_sources,
            }
        )
    return values


def _lexical_resolution_view(graph: Any) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for item in graph.lexical_nodes:
        selected = next(
            (
                candidate
                for candidate in item.candidates
                if candidate.record_id == item.selected_record_id
            ),
            None,
        )
        values.append(
            {
                "surface": item.surface,
                "normalized": item.normalized,
                "reading": item.reading,
                "status": item.status.value,
                "selected_record_id": item.selected_record_id,
                "selected_lemma": selected.lemma if selected else None,
                "selected_source_dataset": (
                    selected.source_dataset if selected else None
                ),
                "resolution_reason": item.resolution_reason,
                "resolution_confidence": item.resolution_confidence,
                "candidate_count": len(item.candidates),
            }
        )
    return values


def analyze_story(
    engine: ParserEngine,
    item: dict[str, Any],
    *,
    deadline_ms: int = 5000,
) -> dict[str, Any]:
    story_id = item["id"]
    text = item["text"]
    response = engine.analyze(
        AnalyzeRequest(original_text=text, deadline_ms=deadline_ms)
    )
    graph = response.meaning_graph
    reading = graph.reading_analysis
    semantic_senses = _semantic_sense_view(graph)
    language_features = _language_feature_view(graph)

    semantic_pack = {
        key: value
        for key, value in graph.quality_annotations.items()
        if key.startswith("semantic_data_")
    }

    return {
        "id": story_id,
        "overall_status": response.overall_status.value,
        "analysis_path": response.analysis_path,
        "paragraph_structure": _model_json(reading.paragraph_structure),
        "summary": _model_json(reading.summary),
        "argumentation": _model_json(reading.argumentation),
        "slang_meaning": {
            "language_features": language_features,
            "semantic_senses": semantic_senses,
        },
        "context_dependent_sense": {
            "semantic_senses": semantic_senses,
            "lexical_resolution": _lexical_resolution_view(graph),
            "unresolved": graph.unresolved,
        },
        "semantic_pack": semantic_pack,
        "unsupported_elements": response.unsupported_elements,
        "timeouts": response.timeouts,
    }


def run_story_test(
    corpus_path: Path = DEFAULT_CORPUS,
    output_path: Path = DEFAULT_OUTPUT,
    *,
    deadline_ms: int = 5000,
) -> list[dict[str, Any]]:
    corpus = load_jsonl(corpus_path)
    engine = ParserEngine()
    results: list[dict[str, Any]] = []
    errors = 0

    for item in corpus:
        story_id = item["id"]
        print(f"Processing: {story_id}")
        try:
            result = analyze_story(engine, item, deadline_ms=deadline_ms)
        except Exception as exc:  # Preserve evaluator-visible runtime failures.
            errors += 1
            result = {
                "id": story_id,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }
        results.append(result)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for result in results:
            handle.write(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )

    print(
        "Story-test actual results saved: "
        f"path={output_path} records={len(results)} errors={errors}"
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run deterministic MCP story-test corpus and save actual output."
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--deadline-ms", type=int, default=5000)
    args = parser.parse_args()

    run_story_test(
        args.corpus,
        args.output,
        deadline_ms=args.deadline_ms,
    )


if __name__ == "__main__":
    main()
