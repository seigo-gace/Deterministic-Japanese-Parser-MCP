from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.models import ExecutionMode, ItemStatus


def _proposition(response, *, intent=None, predicate=None, sense=None):
    for item in response.meaning_graph.propositions:
        if intent is not None and item.intent_type != intent:
            continue
        if predicate is not None and item.predicate != predicate:
            continue
        if sense is not None and item.sense_id != sense:
            continue
        return item
    raise AssertionError({
        "intent": intent,
        "predicate": predicate,
        "sense": sense,
        "actual": [
            {
                "intent": item.intent_type,
                "predicate": item.predicate,
                "sense": item.sense_id,
                "speech_act": item.speech_act,
            }
            for item in response.meaning_graph.propositions
        ],
    })


def test_system_failure_sense_is_selected_from_context():
    response = ParserEngine().analyze(AnalyzeRequest(
        original_text="サーバーが落ちた。",
    ))
    proposition = _proposition(response, sense="fall.system_failure")
    assert proposition.sense_confidence > 0.5
    assert proposition.status == ItemStatus.RESOLVED
    assert proposition.intent_type == "observation"


def test_ambiguous_bare_sense_remains_unselected():
    response = ParserEngine().analyze(AnalyzeRequest(
        original_text="落ちた。",
    ))
    proposition = next(
        item
        for item in response.meaning_graph.propositions
        if item.surface_predicate == "落ちた"
    )
    assert proposition.sense_id is None
    assert proposition.sense_confidence == 0.0


def test_ellipsis_inherits_previous_explicit_target():
    response = ParserEngine().analyze(AnalyzeRequest(
        original_text="APIを確認して、問題があれば修正して。",
    ))
    proposition = _proposition(response, intent="modify")
    inferred = [
        item
        for item in proposition.arguments
        if not item.explicit and item.value == "API"
    ]
    assert inferred
    assert proposition.status == ItemStatus.RESOLVED
    assert any(
        source.startswith("ellipsis:")
        for source in proposition.inference_sources
    )


def test_missing_target_without_antecedent_fails_closed():
    response = ParserEngine().analyze(AnalyzeRequest(
        original_text="削除して。",
        execution_mode=ExecutionMode.EXTERNAL_ACTION,
    ))
    assert not response.execution_allowed
    remove = _proposition(response, intent="remove")
    assert remove.status == ItemStatus.INSUFFICIENT
    assert not remove.executable_candidate


def test_polite_request_is_an_executable_request_not_a_capability_question():
    response = ParserEngine().analyze(AnalyzeRequest(
        original_text="APIを確認していただけますか。",
        execution_mode=ExecutionMode.EXTERNAL_ACTION,
    ))
    request = _proposition(response, intent="request")
    assert request.speech_act == "polite_request"
    assert request.executable_candidate
    assert response.execution_allowed
    assert response.task_graph.tasks
    assert response.task_graph.tasks[0].target == "API"


def test_commitment_is_not_executed_as_a_request():
    response = ParserEngine().analyze(AnalyzeRequest(
        original_text="こちらで確認します。",
        execution_mode=ExecutionMode.EXTERNAL_ACTION,
    ))
    commitment = _proposition(response, intent="commitment")
    assert commitment.speech_act == "commitment"
    assert not commitment.executable_candidate
    assert not response.execution_allowed


def test_indirect_refusal_is_preserved_and_not_executed():
    response = ParserEngine().analyze(AnalyzeRequest(
        original_text="今はその変更への対応が難しいです。",
        execution_mode=ExecutionMode.EXTERNAL_ACTION,
    ))
    refusal = _proposition(response, intent="refusal")
    assert refusal.speech_act == "refusal"
    assert not refusal.executable_candidate
    assert not response.execution_allowed


def test_causal_discourse_edge_is_created():
    response = ParserEngine().analyze(AnalyzeRequest(
        original_text="テストが通った。そのためAPIを公開しろ。",
    ))
    assert any(
        edge.relation == "causes"
        for edge in response.meaning_graph.scope_edges
    )
    second = response.meaning_graph.clauses[1]
    assert second.relation == "causes"
    assert second.parent_clause_id == response.meaning_graph.clauses[0].clause_id


def test_contrast_discourse_edge_is_created():
    response = ParserEngine().analyze(AnalyzeRequest(
        original_text="UIは維持する。しかしAPIは変更しろ。",
    ))
    assert any(
        edge.relation == "contrasts_with"
        for edge in response.meaning_graph.scope_edges
    )


def test_known_entity_resolves_typed_reference():
    response = ParserEngine().analyze(AnalyzeRequest(
        original_text="そのAPIを修正しろ。",
        conversation_context=["料金API", "顧客API"],
        known_entities=["決済API"],
    ))
    assert response.references
    reference = response.references[0]
    assert reference.selected == "決済API"
    assert reference.status == ItemStatus.RESOLVED
    assert reference.resolution_reason.startswith("ranked:known")
