from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"expected one patch marker in {path}, found {count}: {old[:80]!r}"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_models() -> None:
    path = ROOT / "src/deterministic_japanese_parser_mcp/models.py"
    marker = "\n\nclass Intent(BaseModel):"
    addition = '''

class LexicalNode(BaseModel):
    lexical_node_id: str
    surface: str
    normalized: str
    reading: str | None = None
    pos: list[str] = Field(default_factory=list)
    source_span: OriginalSpan
    candidates: list[LexicalCandidate] = Field(default_factory=list)
    candidate_scores: dict[str, int] = Field(default_factory=dict)
    candidate_evidence: dict[str, list[str]] = Field(default_factory=dict)
    selected_record_id: str | None = None
    resolution_reason: str = "no_candidates"
    resolution_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    related_proposition_ids: list[str] = Field(default_factory=list)
    related_entity_ids: list[str] = Field(default_factory=list)
    related_sense_ids: list[str] = Field(default_factory=list)
    status: ItemStatus = ItemStatus.AMBIGUOUS


class Intent(BaseModel):'''
    replace_once(path, marker, addition)
    replace_once(
        path,
        'class MeaningGraph(BaseModel):\n    graph_version: str = "2.1.0"',
        'class MeaningGraph(BaseModel):\n    graph_version: str = "2.2.0"',
    )
    replace_once(
        path,
        '    propositions: list[Proposition] = Field(default_factory=list)\n'
        '    scope_edges: list[ScopeEdge] = Field(default_factory=list)',
        '    propositions: list[Proposition] = Field(default_factory=list)\n'
        '    lexical_nodes: list[LexicalNode] = Field(default_factory=list)\n'
        '    scope_edges: list[ScopeEdge] = Field(default_factory=list)',
    )


def patch_engine() -> None:
    path = ROOT / "src/deterministic_japanese_parser_mcp/engine.py"
    replace_once(
        path,
        "from .logger import append_log\n",
        "from .logger import append_log\n"
        "from .lexical_graph import LexicalGraphEnricher\n",
    )
    replace_once(
        path,
        '''        self.enricher = SemanticEnricher(
            settings.system_dict_dir / "semantic_profiles.yaml",
            self.canonicalizer,
        )
        self.tasks = TaskDecomposer(self.bundle.templates)''',
        '''        self.enricher = SemanticEnricher(
            settings.system_dict_dir / "semantic_profiles.yaml",
            self.canonicalizer,
        )
        self.lexical_graph = LexicalGraphEnricher(
            max_nodes=settings.max_graph_nodes,
        )
        self.tasks = TaskDecomposer(self.bundle.templates)''',
    )
    replace_once(
        path,
        '''            phase_metrics["semantic_enrichment_ms"] = 0.0

        intents = self.meaning.emit_legacy_intents(''',
        '''            phase_metrics["semantic_enrichment_ms"] = 0.0

        if deadline_remaining():
            meaning_graph = run_phase(
                "lexical_graph_enrichment",
                lambda: self.lexical_graph.enrich(
                    meaning_graph,
                    tokens=tokens,
                    original_text=request.original_text,
                    conversation_context=context,
                    known_entities=request.known_entities,
                ),
            )
        else:
            phase_metrics["lexical_graph_enrichment_ms"] = 0.0
            self.lexical_graph.last_metrics = {
                "lexical_node_count": 0,
                "resolved_lexical_node_count": 0,
                "ambiguous_lexical_node_count": 0,
                "lexical_candidate_count": 0,
                "lexical_node_limit_skip_count": 0,
                "lexical_context_registry_used": 0,
            }

        intents = self.meaning.emit_legacy_intents(''',
    )
    replace_once(
        path,
        '''            **self.enricher.last_metrics,
            **self.tasks.last_metrics,''',
        '''            **self.enricher.last_metrics,
            **self.lexical_graph.last_metrics,
            **self.tasks.last_metrics,''',
    )
    replace_once(
        path,
        '''            "proposition_count": len(meaning_graph.propositions),
            "scope_edge_count": len(meaning_graph.scope_edges),''',
        '''            "proposition_count": len(meaning_graph.propositions),
            "meaning_graph_lexical_node_count": len(
                meaning_graph.lexical_nodes
            ),
            "scope_edge_count": len(meaning_graph.scope_edges),''',
    )


def patch_runtime_workflow() -> None:
    path = ROOT / ".github/workflows/compile-open-lexicon.yml"
    replace_once(
        path,
        '      - "src/deterministic_japanese_parser_mcp/models.py"\n'
        '      - "src/deterministic_japanese_parser_mcp/open_lexicon_runtime.py"',
        '      - "src/deterministic_japanese_parser_mcp/models.py"\n'
        '      - "src/deterministic_japanese_parser_mcp/lexical_graph.py"\n'
        '      - "src/deterministic_japanese_parser_mcp/open_lexicon_runtime.py"',
    )
    # The path list appears once for push and once for pull_request.
    text = path.read_text(encoding="utf-8")
    second_marker = (
        '      - "src/deterministic_japanese_parser_mcp/models.py"\n'
        '      - "src/deterministic_japanese_parser_mcp/open_lexicon_runtime.py"'
    )
    if second_marker in text:
        text = text.replace(
            second_marker,
            '      - "src/deterministic_japanese_parser_mcp/models.py"\n'
            '      - "src/deterministic_japanese_parser_mcp/lexical_graph.py"\n'
            '      - "src/deterministic_japanese_parser_mcp/open_lexicon_runtime.py"',
            1,
        )
        path.write_text(text, encoding="utf-8")
    replace_once(
        path,
        '      - "tests/test_open_lexicon_runtime.py"\n'
        '      - ".github/workflows/compile-open-lexicon.yml"',
        '      - "tests/test_open_lexicon_runtime.py"\n'
        '      - "tests/test_lexical_meaning_graph.py"\n'
        '      - ".github/workflows/compile-open-lexicon.yml"',
    )
    text = path.read_text(encoding="utf-8")
    second_test_marker = (
        '      - "tests/test_open_lexicon_runtime.py"\n'
        '      - ".github/workflows/compile-open-lexicon.yml"'
    )
    if second_test_marker in text:
        text = text.replace(
            second_test_marker,
            '      - "tests/test_open_lexicon_runtime.py"\n'
            '      - "tests/test_lexical_meaning_graph.py"\n'
            '      - ".github/workflows/compile-open-lexicon.yml"',
            1,
        )
        path.write_text(text, encoding="utf-8")
    replace_once(
        path,
        '''          pytest -q \\
            tests/test_compiled_open_lexicon.py \\
            tests/test_open_lexicon_runtime.py''',
        '''          pytest -q \\
            tests/test_compiled_open_lexicon.py \\
            tests/test_open_lexicon_runtime.py \\
            tests/test_lexical_meaning_graph.py''',
    )
    replace_once(
        path,
        '''          assert all(
              candidate.source_dataset == "JMdict"
              for candidate in japanese[0].lexical_candidates
          )

          report = {''',
        '''          assert all(
              candidate.source_dataset == "JMdict"
              for candidate in japanese[0].lexical_candidates
          )
          lexical_nodes = response.meaning_graph.lexical_nodes
          assert lexical_nodes
          japan_node = next(
              node for node in lexical_nodes if node.surface == "日本"
          )
          assert japan_node.selected_record_id
          suru_node = next(
              node for node in lexical_nodes if node.surface == "する"
          )
          assert suru_node.selected_record_id
          assert response.meaning_graph.quality_annotations[
              "context_candidate_registry_used"
          ] is False

          report = {''',
    )
    replace_once(
        path,
        '''              "matched_tokens": [token.model_dump() for token in matched],
              "semantic_auto_promotion": False,''',
        '''              "matched_tokens": [token.model_dump() for token in matched],
              "lexical_nodes": [
                  node.model_dump() for node in lexical_nodes
              ],
              "semantic_auto_promotion": False,''',
    )


def write_documentation() -> None:
    path = ROOT / "docs/OPEN_LEXICON_MEANING_GRAPH.md"
    path.write_text(
        '''# Open Lexicon MeaningGraph Connection\n\n'''
        '''## Stage 3 status\n\n'''
        '''The compiled 120,000-record open lexicon is connected to MeaningGraph as lexical identity nodes.\n\n'''
        '''## Resolution policy\n\n'''
        '''The resolver ranks the already-bounded token candidates using deterministic evidence:\n\n'''
        '''- exact surface, normalized surface, or reading match type\n'''
        '''- Sudachi reading agreement\n'''
        '''- Sudachi/JMdict part-of-speech family agreement\n'''
        '''- JMdict reading restrictions and no-kanji constraints\n'''
        '''- a small project-reviewed domain cue map\n'''
        '''- complete source provenance\n\n'''
        '''A single candidate is selected directly. Multiple candidates are selected only when the top score reaches the minimum and has a decisive margin. Truncated candidate lists and ties remain ambiguous.\n\n'''
        '''## MeaningGraph output\n\n'''
        '''Each lexical node contains the token span, ranked candidates, scores, evidence, selected record ID when resolved, related proposition/entity/sense IDs, confidence and status.\n\n'''
        '''## Safety boundary\n\n'''
        '''This stage resolves lexical identity only. It does not promote open-lexicon records into senses, synonyms, intents, tasks, pragmatic meanings, or external actions. The separate 5,000 context-candidate collection is not loaded or used.\n''',
        encoding="utf-8",
    )


def main() -> int:
    patch_models()
    patch_engine()
    patch_runtime_workflow()
    write_documentation()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
