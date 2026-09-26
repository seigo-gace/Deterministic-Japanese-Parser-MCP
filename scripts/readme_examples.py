from __future__ import annotations

import json
from pathlib import Path

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine


def _dump_response(engine: ParserEngine, request: AnalyzeRequest) -> dict:
    response = engine.analyze(request)
    return response.model_dump(mode="json")


def main() -> None:
    engine = ParserEngine()

    examples = {
        "complete": {
            "request": AnalyzeRequest(
                original_text="UIは維持する。APIだけ変更しろ。",
                protected_elements=["UI"],
                execution_mode="external_action",
            ),
        },
        "partial": {
            "request": AnalyzeRequest(
                original_text="それを変更しろ。",
                execution_mode="external_action",
            ),
        },
        "fail_closed": {
            "request": AnalyzeRequest(
                original_text="UIを変更しろ。",
                protected_elements=["UI"],
                execution_mode="external_action",
            ),
        },
    }

    result: dict[str, dict] = {}
    for name, spec in examples.items():
        request = spec["request"]
        response = _dump_response(engine, request)
        result[name] = {
            "request": request.model_dump(mode="json"),
            "response": response,
        }

    # README examples are evidence, not hand-authored expectations.
    # Only assert the properties that define the three documented classes.
    if result["complete"]["response"]["overall_status"] != "COMPLETE":
        raise SystemExit("README_COMPLETE_EXAMPLE_NOT_COMPLETE")
    if result["complete"]["response"]["execution_allowed"] is not True:
        raise SystemExit("README_COMPLETE_EXAMPLE_NOT_ALLOWED")

    if result["partial"]["response"]["overall_status"] != "PARTIAL":
        raise SystemExit("README_PARTIAL_EXAMPLE_NOT_PARTIAL")
    if not result["partial"]["response"].get("blocked_reasons"):
        raise SystemExit("README_PARTIAL_EXAMPLE_MISSING_BLOCKED_REASONS")

    if result["fail_closed"]["response"]["execution_allowed"] is not False:
        raise SystemExit("README_FAIL_CLOSED_EXAMPLE_NOT_BLOCKED")
    if not result["fail_closed"]["response"].get("blocked_reasons"):
        raise SystemExit("README_FAIL_CLOSED_EXAMPLE_MISSING_BLOCKED_REASONS")

    output = Path("reports/readme-examples.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
