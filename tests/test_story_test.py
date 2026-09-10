from __future__ import annotations

import scripts.story_test as story_test


def test_story_runner_applies_cli_deadline_to_engine_hard_deadline(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        '{"id":"story-001","text":"UIを確認する。"}\n',
        encoding="utf-8",
    )
    output = tmp_path / "actual.jsonl"
    captured = {}

    class FakeResponse:
        overall_status = type("Status", (), {"value": "COMPLETE"})()
        analysis_path = "fake"
        unsupported_elements = []
        timeouts = []

        class Graph:
            propositions = []
            language_features = []
            lexical_nodes = []
            unresolved = []
            quality_annotations = {}

            class Reading:
                paragraph_structure = None
                summary = None
                argumentation = None

            reading_analysis = Reading()

        meaning_graph = Graph()

    class FakeEngine:
        def __init__(self, settings):
            captured["hard_deadline_ms"] = settings.hard_deadline_ms

        def analyze(self, request):
            captured["request_deadline_ms"] = request.deadline_ms
            return FakeResponse()

    monkeypatch.setattr(story_test, "ParserEngine", FakeEngine)

    story_test.run_story_test(corpus, output, deadline_ms=5000)

    assert captured == {
        "hard_deadline_ms": 5000,
        "request_deadline_ms": 5000,
    }
    assert output.exists()
