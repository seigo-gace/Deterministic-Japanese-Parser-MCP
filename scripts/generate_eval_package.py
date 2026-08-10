from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_CORPUS = Path("tests/data/story_test_corpus.jsonl")
DEFAULT_EXPECTED = Path("tests/data/story_test_expected.jsonl")
DEFAULT_ACTUAL = Path("tests/results/mcp_actual.jsonl")
DEFAULT_OUTPUT = Path("eval_package.md")
DEFAULT_SAMPLE_IDS = [f"story-{index:03d}" for index in range(1, 11)]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            item = json.loads(raw)
            story_id = item.get("id")
            if not isinstance(story_id, str) or not story_id:
                raise ValueError(f"{path}:{line_number}: missing id")
            items.append(item)
    return items


def _by_id(items: list[dict[str, Any]], *, label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        story_id = item["id"]
        if story_id in indexed:
            raise ValueError(f"{label}: duplicate id {story_id}")
        indexed[story_id] = item
    return indexed


def _json_block(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def generate_package(
    corpus_path: Path = DEFAULT_CORPUS,
    expected_path: Path = DEFAULT_EXPECTED,
    actual_path: Path = DEFAULT_ACTUAL,
    *,
    sample_ids: list[str] | None = None,
) -> str:
    corpus = _by_id(load_jsonl(corpus_path), label="corpus")
    expected = _by_id(load_jsonl(expected_path), label="expected")
    actual = _by_id(load_jsonl(actual_path), label="actual")
    chosen = sample_ids or DEFAULT_SAMPLE_IDS

    missing = [
        story_id
        for story_id in chosen
        if story_id not in corpus
        or story_id not in expected
        or story_id not in actual
    ]
    if missing:
        raise ValueError(f"missing evaluation records: {missing}")

    lines = [
        "# 日本語読解MCP 外部AI評価パッケージ",
        "",
        "あなたは日本語読解評価AIです。以下のDeterministic Japanese Parser MCPの"
        "実際の解析結果を、提示された期待値と本文に照らして評価してください。",
        "",
        "## 重要な評価境界",
        "",
        "- 期待値は現時点では `HUMAN_REVIEW_PENDING` のGold Candidateです。"
        "人間認証済みGoldであるとは扱わないでください。",
        "- Gold Candidate自体に誤り・不足があると判断した場合は、"
        "`Gold Candidate issue`として明示し、MCP出力を本文から独立に評価してください。",
        "- MCP出力に `error` がある場合、そのStoryは実行失敗として評価してください。",
        "- 若者言葉・文脈依存語が本文に存在しない場合も、"
        "不要な意味を捏造せず『存在しない』と扱えているかを評価対象に含めます。",
        "- 0〜100点は感覚ではなく、本文・期待値・MCP出力の対応根拠を示して付けてください。",
        "",
        "## 評価ルーブリック（各項目0〜100点）",
        "",
        "| 項目 | 評価基準 |",
        "|------|----------|",
        "| 段落構造 | 明示段落境界、段落数、各段落の範囲、トピック文が本文に整合しているか |",
        "| 要旨 | 文章全体の主要主張・結論を保ち、補足や具体例を主旨と取り違えていないか |",
        "| 論証構造 | 主張・理由・根拠・反論・限定・前提と、それらの関係を正しく抽出しているか |",
        "| 若者言葉認識 | ネットスラング・若者言葉の有無と意味・極性・用法を文脈に沿って認識しているか |",
        "| 文脈依存語識別 | 多義語・比喩・文脈依存表現のSenseを文脈に応じて選択し、曖昧なら曖昧として保持できているか |",
        "",
        "## 採点方法",
        "",
        "各Storyについて5項目を0〜100点で採点し、理由を1〜3文で記載してください。",
        "最後に5項目それぞれについて、10 Storyの平均点と中央値を出してください。",
        "さらに、重大な誤読を `critical_errors` として列挙してください。",
        "",
        "最終回答の末尾には次のJSONを必ず出してください。",
        "",
        "```json",
        "{",
        '  "model": "モデル名",',
        '  "category_average": {',
        '    "paragraph_structure": 0,',
        '    "summary": 0,',
        '    "argumentation": 0,',
        '    "youth_slang": 0,',
        '    "context_dependent": 0',
        "  },",
        '  "category_median": {',
        '    "paragraph_structure": 0,',
        '    "summary": 0,',
        '    "argumentation": 0,',
        '    "youth_slang": 0,',
        '    "context_dependent": 0',
        "  },",
        '  "critical_errors": [],',
        '  "gold_candidate_issues": []',
        "}",
        "```",
        "",
        "---",
        "",
    ]

    for story_id in chosen:
        story = corpus[story_id]
        lines.extend(
            [
                f"## {story_id}",
                "",
                f"**Genre:** `{story.get('genre', '')}`",
                "",
                f"**Target features:** `{', '.join(story.get('target_features', []))}`",
                "",
                "### 本文",
                "",
                story.get("text", ""),
                "",
                "### 期待値（Gold Candidate / HUMAN_REVIEW_PENDING）",
                "",
                "```json",
                _json_block(expected[story_id]),
                "```",
                "",
                "### MCP実際出力",
                "",
                "```json",
                _json_block(actual[story_id]),
                "```",
                "",
                "### 評価スコア（各項目0〜100点）",
                "",
                "| 項目 | スコア | 理由 |",
                "|------|--------|------|",
                "| 段落構造 |  |  |",
                "| 要旨 |  |  |",
                "| 論証構造 |  |  |",
                "| 若者言葉認識 |  |  |",
                "| 文脈依存語識別 |  |  |",
                "",
                "### Gold Candidate issue（ある場合のみ）",
                "",
                "- ",
                "",
                "---",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a copy/paste-ready external-AI story evaluation package."
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED)
    parser.add_argument("--actual", type=Path, default=DEFAULT_ACTUAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    package = generate_package(
        args.corpus,
        args.expected,
        args.actual,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(package, encoding="utf-8", newline="\n")
    print(
        "Evaluation package saved: "
        f"path={args.output} sample_count={len(DEFAULT_SAMPLE_IDS)}"
    )


if __name__ == "__main__":
    main()
