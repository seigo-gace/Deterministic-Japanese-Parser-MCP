from __future__ import annotations

from collections import deque

from .grammar_kernel import ACTION_INTENTS
from .models import ItemStatus, MeaningGraph


class GraphGuard:
    """Evaluate only the graph region that can affect an external action."""

    def action_relevance_closure(self, graph: MeaningGraph) -> set[str]:
        seeds = {
            item.proposition_id
            for item in graph.propositions
            if item.intent_type in ACTION_INTENTS and item.executable_candidate
        }
        adjacency: dict[str, set[str]] = {}
        for edge in graph.scope_edges:
            adjacency.setdefault(edge.source_id, set()).add(edge.target_id)
            adjacency.setdefault(edge.target_id, set()).add(edge.source_id)
        closure = set(seeds)
        queue = deque(seeds)
        while queue:
            current = queue.popleft()
            for neighbor in adjacency.get(current, set()):
                if neighbor not in closure:
                    closure.add(neighbor)
                    queue.append(neighbor)
        return closure

    def evaluate(
        self,
        graph: MeaningGraph,
        *,
        contradictions: list[dict],
        unsupported: list[dict],
        timeouts: list[dict],
        external_action: bool,
    ) -> tuple[bool, list[str], set[str]]:
        if not external_action:
            return True, [], set()

        blocked: list[str] = []
        closure = self.action_relevance_closure(graph)
        all_action_like = [
            item for item in graph.propositions if item.intent_type in ACTION_INTENTS
        ]
        executable = [item for item in all_action_like if item.executable_candidate]

        for contradiction in contradictions:
            related_ids = {
                contradiction.get("left_proposition_id"),
                contradiction.get("right_proposition_id"),
            } - {None}
            if not related_ids or related_ids.intersection(closure):
                blocked.append("CONTRADICTORY")
                break
        if timeouts:
            blocked.append("TIMEOUT")
        if unsupported and not executable:
            blocked.append("UNSUPPORTED")
        if all_action_like and not executable:
            blocked.append("NON_EXECUTABLE_SPEECH_ACT")
        if not all_action_like:
            blocked.append("NO_EXECUTABLE_ACTION")

        proposition_by_id = {
            item.proposition_id: item for item in graph.propositions
        }
        for proposition_id in closure:
            proposition = proposition_by_id.get(proposition_id)
            if proposition is None:
                continue
            if proposition.status != ItemStatus.RESOLVED:
                blocked.append(f"{proposition.status.value}_ACTION_GRAPH")
            if proposition.quoted:
                blocked.append("QUOTED_ACTION")
            if (
                proposition.sentence_mood == "interrogative"
                and proposition.intent_type in ACTION_INTENTS
                and proposition.speech_act != "polite_request"
            ):
                blocked.append("INTERROGATIVE_ACTION")
            if proposition.sense_candidates and not proposition.sense_id:
                blocked.append("AMBIGUOUS_ACTION_SENSE")

        for edge in graph.scope_edges:
            if edge.source_id in closure or edge.target_id in closure:
                if edge.status != ItemStatus.RESOLVED:
                    blocked.append(f"{edge.status.value}_SCOPE")

        frame_propositions = {
            frame.frame_id: set(frame.related_proposition_ids)
            for frame in graph.reading_analysis.predicate_frames
        }
        for operator in graph.reading_analysis.scope_operators:
            related = set().union(*(
                frame_propositions.get(frame_id, set())
                for frame_id in operator.target_frame_ids
            )) if operator.target_frame_ids else set()
            if not related.intersection(closure):
                continue
            if operator.status != ItemStatus.RESOLVED:
                blocked.append(f"{operator.status.value}_READING_SCOPE")
            if operator.operator_type == "quotation":
                blocked.append("QUOTED_ACTION")
            elif operator.operator_type == "question":
                related_actions = [
                    proposition_by_id[proposition_id]
                    for proposition_id in related.intersection(closure)
                    if proposition_id in proposition_by_id
                    and proposition_by_id[proposition_id].intent_type
                    in ACTION_INTENTS
                ]
                if any(
                    item.speech_act != "polite_request"
                    for item in related_actions
                ):
                    blocked.append("INTERROGATIVE_ACTION")
            elif operator.operator_type == "negation":
                blocked.append("NEGATED_ACTION")
            elif operator.operator_type == "condition":
                blocked.append("CONDITIONAL_ACTION_REQUIRES_EVALUATION")
            elif (
                operator.operator_type == "modality"
                and operator.semantic_value in {"hearsay", "inference"}
            ):
                blocked.append("NON_ASSERTED_ACTION")

        for attribution in graph.reading_analysis.attribution_frames:
            related = set().union(*(
                frame_propositions.get(frame_id, set())
                for frame_id in attribution.related_frame_ids
            )) if attribution.related_frame_ids else set()
            if related.intersection(closure):
                blocked.append("ATTRIBUTED_ACTION")
                if attribution.status != ItemStatus.RESOLVED:
                    blocked.append("INSUFFICIENT_ATTRIBUTION")

        for unresolved in graph.unresolved:
            related = set(unresolved.get("related_proposition_ids", []))
            status = unresolved.get("status")
            if related and related.intersection(closure):
                if status in {
                    ItemStatus.AMBIGUOUS.value,
                    ItemStatus.INSUFFICIENT.value,
                }:
                    blocked.append("AMBIGUOUS_OR_INSUFFICIENT_REFERENCE")
                blocked.append(f"{status}_ACTION_REFERENCE")
            elif unresolved.get("proposition_id") in closure:
                blocked.append(f"{status}_ACTION_GRAPH")
            elif unresolved.get("type") in {
                "graph_node_limit",
                "scope_edge_limit",
            }:
                blocked.append("TIMEOUT")

        return not blocked, list(dict.fromkeys(blocked)), closure
