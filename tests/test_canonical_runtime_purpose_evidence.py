from __future__ import annotations
import pytest
from tools.unified_semantic_data.canonical_runtime_projection import _project_purpose_evidence

def _record(role="morphology", *, public=True, typed=True, evidence_role=None):
    payload={"source_value":{"columns":["会う","会わない","V;PRS;NEG"]}}
    if typed: payload["typed_purpose_payload"]={"schema_version":"1.0.0","kind":"morphology_feature_sequence","lemma":"会う","inflected_form":"会わない","features":["V","PRS","NEG"]}
    return {"auxiliary_evidence":{role:[{"evidence_id":"E-1","source_role":evidence_role or role,"payload":payload,"source":{"public_runtime_eligible":public,"logical_source_id":"j-unimorph","source_record_sha256":"a"*64}}]}}

def test_typed_purpose_evidence_is_projected_losslessly_and_routed():
    original=_record(); result=_project_purpose_evidence(original); assert len(result)==1
    item=result[0]; assert item["source_role"]=="morphology"; assert item["evidence_id"]=="E-1"; assert item["typed_purpose_payload"]==original["auxiliary_evidence"]["morphology"][0]["payload"]["typed_purpose_payload"]; assert "grammar_kernel" in item["consumers"]; assert "reading_runtime" in item["consumers"]

def test_non_typed_auxiliary_evidence_is_not_promoted(): assert _project_purpose_evidence(_record(typed=False))==[]
def test_non_public_typed_evidence_is_not_projected(): assert _project_purpose_evidence(_record(public=False))==[]
def test_unknown_role_fails_closed():
    with pytest.raises(ValueError, match="unroutable"): _project_purpose_evidence(_record(role="unknown-role"))
def test_role_mismatch_fails_closed():
    with pytest.raises(ValueError, match="role mismatch"): _project_purpose_evidence(_record(evidence_role="usage"))
