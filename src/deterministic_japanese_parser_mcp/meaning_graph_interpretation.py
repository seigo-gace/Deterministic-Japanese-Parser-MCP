from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .interpretation_contracts import (
    FieldEvidenceReference,
    RecoveryInterpretationEvidence,
    RouterTrace,
)
from .models import MeaningGraph


NON_SEMANTIC_INTERPRETATION_FIELDS = frozenset(
    {
        "router_trace",
        "recovery_evidence",
        "field_evidence",
    }
)


def _hash_compatible_exclude(exclude: Any) -> Any:
    """Keep interpretation evidence outside MeaningGraph 2.3 semantic identity.

    Existing hash sites explicitly exclude ``semantic_hash``.  When that
    contract is in use, Router/Recovery/Rights evidence is also excluded so
    attaching inspectable evidence cannot rewrite the semantic identity of an
    otherwise identical graph.  Normal serialization keeps the evidence.
    """
    if isinstance(exclude, (set, frozenset)) and "semantic_hash" in exclude:
        return set(exclude) | set(NON_SEMANTIC_INTERPRETATION_FIELDS)
    return exclude


class InterpretationMeaningGraph(MeaningGraph):
    """MeaningGraph 2.3 plus inspectable, non-authoritative interpretation evidence.

    The added fields explain routing/recovery/provenance decisions.  They are
    intentionally not semantic authority.  A recovered interpretation changes
    semantic identity only when it actually changes existing semantic graph
    fields such as propositions, entities, clauses, reading analysis, or
    unresolved state.
    """

    router_trace: RouterTrace | None = None
    recovery_evidence: list[RecoveryInterpretationEvidence] = []
    field_evidence: list[FieldEvidenceReference] = []

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if "exclude" in kwargs:
            kwargs["exclude"] = _hash_compatible_exclude(kwargs["exclude"])
        return super().model_dump(*args, **kwargs)

    def model_dump_json(self, *args: Any, **kwargs: Any) -> str:
        if "exclude" in kwargs:
            kwargs["exclude"] = _hash_compatible_exclude(kwargs["exclude"])
        return super().model_dump_json(*args, **kwargs)


def attach_interpretation_evidence(
    graph: MeaningGraph,
    *,
    router_trace: RouterTrace | None = None,
    recovery_evidence: list[RecoveryInterpretationEvidence] | None = None,
    field_evidence: list[FieldEvidenceReference] | None = None,
) -> InterpretationMeaningGraph:
    """Attach evidence without granting it meaning authority or changing identity."""
    payload = graph.model_dump(mode="python")
    return InterpretationMeaningGraph.model_validate(
        {
            **payload,
            "router_trace": router_trace,
            "recovery_evidence": list(recovery_evidence or ()),
            "field_evidence": list(field_evidence or ()),
        }
    )


def interpretation_evidence_summary(
    graph: InterpretationMeaningGraph,
) -> Mapping[str, int | bool]:
    """Small deterministic summary for diagnostics without duplicating evidence."""
    return {
        "router_trace_present": graph.router_trace is not None,
        "recovery_evidence_count": len(graph.recovery_evidence),
        "field_evidence_count": len(graph.field_evidence),
    }
