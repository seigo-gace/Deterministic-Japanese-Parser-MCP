from __future__ import annotations

import json
from pathlib import Path

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine


README_RESPONSE_FIELDS = (
    "overall_status",
    "execution_allowed",
    "blocked_reasons",
    "analysis_path",
    "ambiguities",
    "contradictions",
    "missing_information",
    "unsupported_elements",
)


def _dump_response(engine: ParserEngine, request: AnalyzeRequest) -> dict:
    response = engine.analyze(request)
    return response.model_dump(mode="json")


def _compact_example(request: AnalyzeRequest, response: dict) -> dict:
    compact_response = {
        field: response[field]
        for field in README_RESPONSE_FIELDS
    }
    compact_response["semantic_hash"] = response["meaning_graph"]["semantic_hash"]
    compact_response["task_count"] = len(response["task_graph"]["tasks"])
    compact_response["proposition_count"] = len(response["meaning_graph"]["propositions"])
    return {
        "request": request.model_dump(mode="json"),
        "response": compact_response,
    }


def main() -> None:
    engine = ParserEngine()

    requests = {
        "complete": AnalyzeRequest(
            original_text="UIは維持する。APIだけ変更しろ。",
            protected_elements=["UI"],
            execution_mode="external_action",
        ),
        "partial": AnalyzeRequest(
            original_text="それを変更しろ。",
            execution_mode="external_action",
        ),
        "fail_closed": AnalyzeRequest(
            original_text="UIを変更しろ。",
            protected_elements=["UI"],
            execution_mode="external_action",
        ),
    }

    full: dict[str, dict] = {}
    compact: dict[str, dict] = {}
    for name, request in requests.items():
        response = _dump_response(engine, request)
        full[name] = {
            "request": request.model_dump(mode="json"),
            "response": response,
        }
        compact[name] = _compact_example(request, response)

    # README examples are runtime evidence, not hand-authored expectations.
    if full["complete"]["response"]["overall_status"] != "COMPLETE":
        raise SystemExit("README_COMPLETE_EXAMPLE_NOT_COMPLETE")
    if full["complete"]["response"]["execution_allowed"] is not True:
        raise SystemExit("README_COMPLETE_EXAMPLE_NOT_ALLOWED")

    if full["partial"]["response"]["overall_status"] != "PARTIAL":
        raise SystemExit("README_PARTIAL_EXAMPLE_NOT_PARTIAL")
    if not full["partial"]["response"].get("blocked_reasons"):
        raise SystemExit("README_PARTIAL_EXAMPLE_MISSING_BLOCKED_REASONS")

    if full["fail_closed"]["response"]["execution_allowed"] is not False:
        raise SystemExit("README_FAIL_CLOSED_EXAMPLE_NOT_BLOCKED")
    if not full["fail_closed"]["response"].get("blocked_reasons"):
        raise SystemExit("README_FAIL_CLOSED_EXAMPLE_MISSING_BLOCKED_REASONS")

    reports = Path("reports")
    reports.mkdir(parents=True, exist_ok=True)
    full_path = reports / "readme-examples.json"
    compact_path = reports / "readme-examples-compact.json"

    full_path.write_text(
        json.dumps(full, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    compact_path.write_text(
        json.dumps(compact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(compact_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
