from __future__ import annotations

import hashlib
import re
from typing import Iterable

from .canonical import Canonicalizer
from .grammar_kernel import (
    ACTION_INTENTS,
    argument_roles,
    clause_for_span,
    clean_fragment,
    context_version,
    infer_deontic_force,
    infer_epistemic_status,
    infer_polarity,
    infer_sentence_mood,
    infer_speech_act,
    is_inside_quote,
    predicate_for,
    quote_ranges,
    segment_clauses,
    target_for,
)
from .models import (
    Argument,
    Clause,
    DecisionStateChange,
    Entity,
    Intent,
    ItemStatus,
    MeaningGraph,
    Metaphor,
    OriginalSpan,
    Proposition,
    ReferenceResolution,
    ScopeEdge,
    Token,
)


_RELATION_BY_INTENT = {
    "prohibition": "prohibits",
    "preserve": "preserves",
    "condition": "conditions",
    "exception": "excepts",
    "priority": "prioritizes",
    "scope": "limits",
    "out_of_scope": "excludes",
    "completion_criteria": "completion_gate",
    "verification_criteria": "verification_gate",
    "premise": "premise_for",
}
_TARGET_REQUIRED = {
    "modify",
    "remove",
    "comparison",
    "preserve",
    "scope",
    "out_of_scope",
}


def _compact(value: str) -> str:
    return re.sub(r"[\s、。！？!?「」『』\"'()（）]+", "", value or "")


def _entity_type(value: str) -> str:
    if re.search(
        r"(?:API|UI|GitHub|Notion|MCP|DB|URL|HTTP|JSON|YAML|Code|コード)",
        value,
        re.I,
    ):
        return "technical_object"
    if re.search(r"(?:人|者|ユーザー|利用者|管理者|彼|彼女|私|相手)$", value):
        return "person_or_role"
    if re.search(r"(?:案|方針|仕様|内容|計画|決定)$", value):
        return "concept"
    if re.search(
        r"(?:ファイル|ページ|文書|資料|リポジトリ|ブランチ)$",
        value,
        re.I,
    ):
        return "artifact"
    return "unknown"


def _fragment_span(
    fragment: str,
    container: OriginalSpan,
    original: str,
) -> OriginalSpan | None:
    if not fragment:
        return None
    start = original.find(fragment, container.start, container.end)
    if start < 0:
        start = original.find(fragment)
    if start < 0:
        return None
    return OriginalSpan(
        start=start,
        end=start + len(fragment),
        source_text=fragment,
    )


def _object_value(proposition: Proposition) -> str:
    for role in ("object", "task", "action", "result", "scope", "reference"):
        for argument in proposition.arguments:
            if argument.role == role and argument.value:
                return argument.value
    return clean_fragment(proposition.value)


class MeaningGraphBuilder:
    def __init__(
        self,
        canonicalizer: Canonicalizer,
        *,
        max_graph_nodes: int = 512,
        max_scope_edges: int = 1024,
    ) -> None:
        self.canonicalizer = canonicalizer
        self.max_graph_nodes = max_graph_nodes
        self.max_scope_edges = max_scope_edges

    def build(
        self,
        *,
        original_text: str,
        normalized_text: str,
        tokens: list[Token],
        intents: list[Intent],
        references: list[ReferenceResolution],
        metaphors: list[Metaphor],
        conversation_context: list[str],
        known_entities: list[str],
        update_hash: bool = True,
    ) -> MeaningGraph:
        del normalized_text, tokens
        seeds = segment_clauses(original_text)
        clauses = [
            Clause(
                clause_id=seed.clause_id,
                text=seed.text,
                source_span=seed.span,
            )
            for seed in seeds
        ]
        clause_by_id = {item.clause_id: item for item in clauses}
        quotes = quote_ranges(original_text)
        entity_by_key: dict[str, Entity] = {}

        def register_entity(
            value: str,
            *,
            span: OriginalSpan | None = None,
            entity_type: str | None = None,
            salience: int = 0,
            status: ItemStatus = ItemStatus.RESOLVED,
        ) -> str | None:
            value = clean_fragment(value)
            key = _compact(value)
            if not key:
                return None
            existing = entity_by_key.get(key)
            if existing is None:
                existing = Entity(
                    entity_id=f"E-{len(entity_by_key) + 1:03d}",
                    canonical=value,
                    entity_type=entity_type or _entity_type(value),
                    mentions=[value],
                    source_spans=[span] if span is not None else [],
                    salience=salience,
                    status=status,
                )
                entity_by_key[key] = existing
            else:
                updates: dict = {}
                if value not in existing.mentions:
                    updates["mentions"] = [*existing.mentions, value]
                if span is not None and all(
                    not (item.start == span.start and item.end == span.end)
                    for item in existing.source_spans
                ):
                    updates["source_spans"] = [*existing.source_spans, span]
                if salience > existing.salience:
                    updates["salience"] = salience
                if (
                    existing.status != ItemStatus.RESOLVED
                    and status == ItemStatus.RESOLVED
                ):
                    updates["status"] = status
                if updates:
                    existing = existing.model_copy(update=updates)
                    entity_by_key[key] = existing
            return existing.entity_id

        for index, value in enumerate(reversed(conversation_context)):
            register_entity(
                value,
                entity_type="context_candidate",
                salience=max(1, 20 - index),
            )
        for value in known_entities:
            register_entity(value, entity_type="known_entity", salience=30)
        for reference in references:
            if reference.selected:
                register_entity(
                    reference.selected,
                    entity_type="resolved_reference",
                    salience=40,
                )
            else:
                for candidate in reference.candidates:
                    register_entity(
                        candidate,
                        entity_type="reference_candidate",
                        salience=10,
                        status=ItemStatus.AMBIGUOUS,
                    )
        for metaphor in metaphors:
            register_entity(
                metaphor.expression,
                span=metaphor.span,
                entity_type="figurative_expression",
                salience=5,
                status=metaphor.status,
            )

        propositions: list[Proposition] = []
        evidence_rule_ids: set[str] = set()
        unresolved: list[dict] = []

        for intent in sorted(
            intents,
            key=lambda item: (
                item.span.start,
                item.span.end,
                -item.priority,
                item.type,
            ),
        ):
            if len(propositions) + len(entity_by_key) >= self.max_graph_nodes:
                unresolved.append({
                    "type": "graph_node_limit",
                    "status": ItemStatus.TIMEOUT.value,
                    "source_span": intent.span.model_dump(),
                })
                break
            clause_seed = clause_for_span(intent.span, seeds)
            clause = clause_by_id.get(clause_seed.clause_id) if clause_seed else None
            clause_text = clause.text if clause is not None else intent.span.source_text
            mood = infer_sentence_mood(clause_text, intent.type)
            quoted, quote_source = is_inside_quote(intent.span, quotes)
            arguments: list[Argument] = []
            for role, value, marker in argument_roles(intent):
                argument_span = _fragment_span(value, intent.span, original_text)
                entity_id = register_entity(
                    value,
                    span=argument_span,
                    salience=50 if role in {"object", "task", "action"} else 20,
                )
                arguments.append(Argument(
                    role=role,
                    value=value,
                    entity_id=entity_id,
                    case_marker=marker,
                    explicit=True,
                    span=argument_span,
                ))
            if (
                intent.type in ACTION_INTENTS
                and not any(item.role == "agent" for item in arguments)
            ):
                arguments.append(Argument(
                    role="agent",
                    value="downstream_system",
                    explicit=False,
                ))

            status = intent.status
            target = target_for(intent)
            if intent.type in _TARGET_REQUIRED and not target:
                status = ItemStatus.INSUFFICIENT
            executable_candidate = (
                intent.type in ACTION_INTENTS
                and not quoted
                and mood != "interrogative"
                and status == ItemStatus.RESOLVED
            )
            proposition_id = f"P-{len(propositions) + 1:03d}"
            proposition = Proposition(
                proposition_id=proposition_id,
                predicate=predicate_for(intent.type),
                intent_type=intent.type,
                value=intent.value,
                captures=dict(intent.captures),
                arguments=arguments,
                polarity=infer_polarity(intent.type, clause_text),
                sentence_mood=mood,
                speech_act=infer_speech_act(intent.type, mood),
                deontic_force=infer_deontic_force(intent.type, clause_text),
                epistemic_status=infer_epistemic_status(clause_text),
                quoted=quoted,
                quote_source=quote_source,
                executable_candidate=executable_candidate,
                clause_id=clause.clause_id if clause else None,
                source_span=intent.span,
                status=status,
                evidence_ids=[intent.rule_id] if intent.rule_id else [],
            )
            propositions.append(proposition)
            evidence_rule_ids.update(proposition.evidence_ids)
            if clause is not None:
                clause_by_id[clause.clause_id] = clause.model_copy(update={
                    "proposition_ids": [
                        *clause.proposition_ids,
                        proposition_id,
                    ],
                })
            if status != ItemStatus.RESOLVED:
                unresolved.append({
                    "type": "proposition",
                    "proposition_id": proposition_id,
                    "status": status.value,
                    "source_span": intent.span.model_dump(),
                })
            elif intent.type in ACTION_INTENTS and mood == "interrogative":
                unresolved.append({
                    "type": "speech_act_not_action",
                    "proposition_id": proposition_id,
                    "status": ItemStatus.AMBIGUOUS.value,
                    "reason": "interrogative clauses are not executable commands",
                })

        clauses = [clause_by_id[item.clause_id] for item in clauses]
        proposition_by_id = {
            item.proposition_id: item for item in propositions
        }
        action_props = [
            item for item in propositions if item.intent_type in ACTION_INTENTS
        ]

        def related(left: str, right: str) -> bool:
            if not left or not right:
                return False
            return (
                self.canonicalizer.related(left, right)
                or _compact(left) == _compact(right)
            )

        def best_action(
            source: Proposition,
            fragment: str | None = None,
        ) -> Proposition | None:
            ranked: list[tuple[int, int, Proposition]] = []
            source_value = fragment or _object_value(source)
            for candidate in action_props:
                if candidate.proposition_id == source.proposition_id:
                    continue
                score = 0
                candidate_value = _object_value(candidate)
                if source_value and related(source_value, candidate_value):
                    score += 100
                if source.clause_id and source.clause_id == candidate.clause_id:
                    score += 40
                if candidate.source_span.start >= source.source_span.start:
                    score += 20
                distance = abs(
                    candidate.source_span.start - source.source_span.start
                )
                ranked.append((score, -distance, candidate))
            if not ranked:
                return None
            ranked.sort(
                key=lambda item: (item[0], item[1], item[2].proposition_id),
                reverse=True,
            )
            if ranked[0][0] <= 0:
                fallback_types = {
                    "preserve",
                    "prohibition",
                    "condition",
                    "exception",
                    "priority",
                    "scope",
                    "out_of_scope",
                    "completion_criteria",
                    "verification_criteria",
                    "premise",
                }
                if source.intent_type in fallback_types and action_props:
                    return min(
                        action_props,
                        key=lambda item: (
                            abs(
                                item.source_span.start
                                - source.source_span.start
                            ),
                            item.source_span.start,
                        ),
                    )
                return None
            return ranked[0][2]

        edges: list[ScopeEdge] = []

        def add_edge(
            source: Proposition,
            target: Proposition,
            relation: str,
        ) -> None:
            if len(edges) >= self.max_scope_edges:
                if not any(
                    item.get("type") == "scope_edge_limit"
                    for item in unresolved
                ):
                    unresolved.append({
                        "type": "scope_edge_limit",
                        "status": ItemStatus.TIMEOUT.value,
                    })
                return
            key = (source.proposition_id, target.proposition_id, relation)
            if any(
                (item.source_id, item.target_id, item.relation) == key
                for item in edges
            ):
                return
            edges.append(ScopeEdge(
                edge_id=f"R-{len(edges) + 1:03d}",
                source_id=source.proposition_id,
                target_id=target.proposition_id,
                relation=relation,
                evidence_ids=list(source.evidence_ids),
            ))

        for proposition in propositions:
            relation = _RELATION_BY_INTENT.get(proposition.intent_type)
            if relation:
                target = best_action(proposition)
                if target is not None:
                    add_edge(proposition, target, relation)
            if proposition.intent_type == "sequence":
                source_prop = best_action(
                    proposition,
                    proposition.captures.get("first"),
                )
                target_prop = best_action(
                    proposition,
                    proposition.captures.get("second")
                    or proposition.captures.get("last"),
                )
                if (
                    source_prop
                    and target_prop
                    and source_prop.proposition_id
                    != target_prop.proposition_id
                ):
                    add_edge(source_prop, target_prop, "precedes")
            if proposition.intent_type == "dependency":
                source_prop = best_action(
                    proposition,
                    proposition.captures.get("dependency"),
                )
                target_prop = best_action(
                    proposition,
                    proposition.captures.get("task"),
                )
                if (
                    source_prop
                    and target_prop
                    and source_prop.proposition_id
                    != target_prop.proposition_id
                ):
                    add_edge(target_prop, source_prop, "depends_on")
            if proposition.intent_type == "correction":
                previous = best_action(
                    proposition,
                    proposition.captures.get("old"),
                )
                if previous:
                    add_edge(proposition, previous, "corrects")

        entity_by_id = {
            item.entity_id: item for item in entity_by_key.values()
        }
        final_clauses: list[Clause] = []
        for clause in clauses:
            topics: list[str] = []
            focuses: list[str] = []
            for proposition_id in clause.proposition_ids:
                proposition = proposition_by_id[proposition_id]
                for argument in proposition.arguments:
                    if not argument.entity_id:
                        continue
                    if re.search(re.escape(argument.value) + r"は", clause.text):
                        topics.append(argument.entity_id)
                    if re.search(re.escape(argument.value) + r"が", clause.text):
                        focuses.append(argument.entity_id)
            final_clauses.append(clause.model_copy(update={
                "topic_entity_ids": list(dict.fromkeys(topics)),
                "focus_entity_ids": list(dict.fromkeys(focuses)),
            }))

        for reference in references:
            if reference.status == ItemStatus.RESOLVED:
                continue
            clause_seed = clause_for_span(reference.span, seeds)
            related_ids = [
                item.proposition_id
                for item in action_props
                if clause_seed is not None
                and item.clause_id == clause_seed.clause_id
            ]
            unresolved.append({
                "type": "reference",
                "expression": reference.expression,
                "status": reference.status.value,
                "candidates": list(reference.candidates),
                "related_proposition_ids": related_ids,
                "source_span": reference.span.model_dump(),
            })

        decision_changes: list[DecisionStateChange] = []
        for proposition in propositions:
            target = _object_value(proposition) or None
            if proposition.intent_type == "decision":
                decision_changes.append(DecisionStateChange(
                    change_type="activate",
                    proposition_id=proposition.proposition_id,
                    target=target,
                    new_state="active",
                ))
            elif proposition.intent_type == "correction":
                decision_changes.append(DecisionStateChange(
                    change_type="supersede",
                    proposition_id=proposition.proposition_id,
                    target=target,
                    previous_state="active",
                    new_state="superseded",
                ))
            elif proposition.intent_type in {"preserve", "prohibition"}:
                decision_changes.append(DecisionStateChange(
                    change_type="constraint",
                    proposition_id=proposition.proposition_id,
                    target=target,
                    new_state=proposition.intent_type,
                ))

        graph = MeaningGraph(
            entities=sorted(
                entity_by_id.values(),
                key=lambda item: item.entity_id,
            ),
            clauses=final_clauses,
            propositions=propositions,
            scope_edges=edges,
            unresolved=unresolved,
            decision_state_changes=decision_changes,
            evidence_rule_ids=sorted(evidence_rule_ids),
            context_version=context_version(
                conversation_context,
                known_entities,
            ),
        )
        if not update_hash:
            return graph
        semantic_hash = hashlib.sha256(
            graph.model_dump_json(
                exclude={"semantic_hash"},
            ).encode("utf-8")
        ).hexdigest()
        return graph.model_copy(update={"semantic_hash": semantic_hash})

    @staticmethod
    def emit_legacy_intents(
        graph: MeaningGraph,
        candidates: Iterable[Intent],
    ) -> list[Intent]:
        represented = {
            (item.intent_type, item.source_span.start, item.source_span.end)
            for item in graph.propositions
        }
        output = [
            item
            for item in candidates
            if item.type == "reference"
            or (item.type, item.span.start, item.span.end) in represented
        ]
        return sorted(
            output,
            key=lambda item: (
                item.span.start,
                item.span.end,
                -item.priority,
                item.type,
            ),
        )
