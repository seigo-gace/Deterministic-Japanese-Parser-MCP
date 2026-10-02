from __future__ import annotations
import copy,pytest
from deterministic_japanese_parser_mcp.semantic_data_runtime import SemanticDataRuntime
from deterministic_japanese_parser_mcp.purpose_routing import routes_for_roles

def _item():
 r=routes_for_roles(["pragmatics"]); return {"source_role":"pragmatics","evidence_id":"E-1","typed_purpose_payload":{"schema_version":"1.0.0","kind":"response_ranking_supervision","label":1},"source":{"public_runtime_eligible":True},"consumers":r["consumers"],"allowed":r["allowed"],"forbidden":r["forbidden"]}
def test_allowed_consumer_receives_evidence():
 i=_item(); assert SemanticDataRuntime._validated_purpose_evidence_for_consumer({"purpose_evidence":[i]},"semantic_data_runtime")==[i]
def test_unrelated_consumer_receives_nothing(): assert SemanticDataRuntime._validated_purpose_evidence_for_consumer({"purpose_evidence":[_item()]},"grammar_kernel")==[]
@pytest.mark.parametrize("field",["consumers","allowed","forbidden"])
def test_tampered_route_fails_closed(field):
 i=copy.deepcopy(_item()); i[field]=["tampered"]
 with pytest.raises(ValueError,match="route mismatch"): SemanticDataRuntime._validated_purpose_evidence_for_consumer({"purpose_evidence":[i]},"semantic_data_runtime")
def test_non_public_runtime_source_fails_closed():
 i=copy.deepcopy(_item()); i["source"]["public_runtime_eligible"]=False
 with pytest.raises(ValueError,match="source boundary"): SemanticDataRuntime._validated_purpose_evidence_for_consumer({"purpose_evidence":[i]},"semantic_data_runtime")
def test_invalid_typed_payload_fails_closed():
 i=copy.deepcopy(_item()); i["typed_purpose_payload"]={}
 with pytest.raises(ValueError,match="typed purpose payload invalid"): SemanticDataRuntime._validated_purpose_evidence_for_consumer({"purpose_evidence":[i]},"semantic_data_runtime")

def test_purpose_evidence_must_be_list():
 with pytest.raises(ValueError,match="purpose_evidence must be list"): SemanticDataRuntime._validated_purpose_evidence_for_consumer({"purpose_evidence":{"bad":1}},"semantic_data_runtime")

def test_missing_evidence_id_fails_closed():
 i=copy.deepcopy(_item()); i["evidence_id"]=""
 with pytest.raises(ValueError,match="evidence_id missing"): SemanticDataRuntime._validated_purpose_evidence_for_consumer({"purpose_evidence":[i]},"semantic_data_runtime")
