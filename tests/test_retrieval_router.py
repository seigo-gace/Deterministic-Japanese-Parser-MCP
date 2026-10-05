from types import SimpleNamespace

import pytest

from deterministic_japanese_parser_mcp.models import OriginalSpan, Token
from deterministic_japanese_parser_mcp.retrieval_router import RetrievalRouter
from deterministic_japanese_parser_mcp.purpose_routing import roles_for_consumer


def _token(surface="橋", normalized="橋", reading="ハシ"):
    return Token(surface=surface, normalized=normalized, reading=reading, pos=["名詞", "普通名詞", "一般"], span=OriginalSpan(start=0, end=len(surface), source_text=surface))


def _candidate(record_id):
    return SimpleNamespace(record_id=record_id)


class FakeLexicon:
    def __init__(self, purpose_available=True):
        self.calls = []
        self.purpose_available = purpose_available

    def purpose_exact_lookup(self, text, *, role, match_type="surface", max_candidates=8):
        self.calls.append(("purpose_exact", role, match_type, text))
        if not self.purpose_available:
            raise RuntimeError("purpose-specific index is unavailable")
        return ([_candidate("P1")], 1)

    def purpose_reading_lookup(self, reading, *, role, surface=None, normalized=None, max_candidates=8):
        self.calls.append(("purpose_reading", role, reading))
        if not self.purpose_available:
            raise RuntimeError("purpose-specific index is unavailable")
        return ([_candidate("PR1")], 1)

    def exact_lookup(self, text, *, match_type="surface", max_candidates=8):
        self.calls.append(("exact", match_type, text))
        return ([_candidate("P1"), _candidate("G1")], 2)

    def reading_lookup(self, reading, *, surface=None, normalized=None, max_candidates=8):
        self.calls.append(("reading", reading))
        return ([_candidate("R1")], 1)


def test_purpose_lane_precedes_general_and_deduplicates():
    lexicon = FakeLexicon()
    result = RetrievalRouter(lexicon).retrieve_token(_token(), source_roles=["lexical-definition"], max_candidates=8)
    assert [item.record_id for item in result.candidates] == ["P1", "G1"]
    assert result.trace.lanes_attempted[0] == "purpose:lexical-definition:surface"
    assert result.trace.purpose_lane_hits == 1
    assert result.trace.general_lane_hits == 1
    assert not any(call[0] in {"purpose_reading", "reading"} for call in lexicon.calls)


def test_missing_purpose_index_falls_back_to_general_without_promoting_role():
    lexicon = FakeLexicon(purpose_available=False)
    result = RetrievalRouter(lexicon).retrieve_token(_token(), source_roles=["lexical-definition"], max_candidates=2)
    assert [item.record_id for item in result.candidates] == ["P1", "G1"]
    assert result.trace.purpose_index_available is False
    assert ("exact", "surface", "橋") in lexicon.calls


def test_unknown_role_fails_closed():
    with pytest.raises(ValueError, match="unroutable purpose roles"):
        RetrievalRouter(FakeLexicon()).retrieve_token(_token(), source_roles=["not-a-real-role"])


def test_bound_is_stable_and_reading_is_progressive():
    lexicon = FakeLexicon()
    result = RetrievalRouter(lexicon).retrieve_token(_token(), source_roles=["lexical-definition"], max_candidates=2)
    assert [item.record_id for item in result.candidates] == ["P1", "G1"]
    assert not any(call[0] == "reading" for call in lexicon.calls)


def test_consumer_roles_are_contract_derived_and_deterministic():
    roles = roles_for_consumer("sense_resolver")
    assert roles == sorted(roles)
    assert "lexical-definition" in roles
    assert "semantic-class" in roles
    assert "lexical-relation" in roles
    assert "pronunciation" not in roles

def test_unknown_consumer_gets_no_authority():
    assert roles_for_consumer("not-a-runtime-consumer") == []


def test_known_contract_role_absent_from_snapshot_skips_only_that_lane():
    class PartialPurposeLexicon(FakeLexicon):
        def purpose_exact_lookup(self, text, *, role, match_type="surface", max_candidates=8):
            self.calls.append(("purpose_exact", role, match_type, text))
            if role == "domain-term":
                raise ValueError("unknown purpose role: domain-term")
            return ([_candidate("P1")], 1)
    lexicon = PartialPurposeLexicon()
    result = RetrievalRouter(lexicon).retrieve_token(_token(), source_roles=["domain-term", "lexical-definition"], max_candidates=8)
    assert [item.record_id for item in result.candidates] == ["P1", "G1"]
    assert ("purpose_exact", "domain-term", "surface", "橋") in lexicon.calls
    assert ("purpose_exact", "lexical-definition", "surface", "橋") in lexicon.calls


def test_reading_runs_only_after_all_exact_lanes_miss():
    class ReadingOnlyLexicon(FakeLexicon):
        def purpose_exact_lookup(self, text, *, role, match_type="surface", max_candidates=8):
            self.calls.append(("purpose_exact", role, match_type, text))
            return ([], 0)
        def exact_lookup(self, text, *, match_type="surface", max_candidates=8):
            self.calls.append(("exact", match_type, text))
            return ([], 0)
    lexicon = ReadingOnlyLexicon()
    result = RetrievalRouter(lexicon).retrieve_token(_token(), source_roles=["lexical-definition"], max_candidates=8)
    assert [item.record_id for item in result.candidates] == ["PR1", "R1"]
    assert ("purpose_reading", "lexical-definition", "ハシ") in lexicon.calls
    assert ("reading", "ハシ") in lexicon.calls


def test_surface_hit_blocks_normalized_fallback():
    class L(FakeLexicon):
        def purpose_exact_lookup(self, text, *, role, match_type="surface", max_candidates=8):
            self.calls.append(("purpose_exact", role, match_type, text))
            return (([_candidate("P1")], 1) if match_type == "surface" else ([_candidate("PN1")], 1))
        def exact_lookup(self, text, *, match_type="surface", max_candidates=8):
            self.calls.append(("exact", match_type, text))
            return (([_candidate("G1")], 1) if match_type == "surface" else ([_candidate("GN1")], 1))
    x = L()
    r = RetrievalRouter(x).retrieve_token(_token(surface="し", normalized="為る"), source_roles=["lexical-definition"], max_candidates=8)
    assert [i.record_id for i in r.candidates] == ["P1", "G1"]
    assert ("purpose_exact", "lexical-definition", "normalized", "為る") not in x.calls
    assert ("exact", "normalized", "為る") not in x.calls


def test_normalized_fallback_runs_after_surface_miss():
    class L(FakeLexicon):
        def purpose_exact_lookup(self, text, *, role, match_type="surface", max_candidates=8):
            self.calls.append(("purpose_exact", role, match_type, text))
            return (([], 0) if match_type == "surface" else ([_candidate("PN1")], 1))
        def exact_lookup(self, text, *, match_type="surface", max_candidates=8):
            self.calls.append(("exact", match_type, text))
            return (([], 0) if match_type == "surface" else ([_candidate("GN1")], 1))
    x = L()
    r = RetrievalRouter(x).retrieve_token(_token(surface="し", normalized="為る"), source_roles=["lexical-definition"], max_candidates=8)
    ids = [i.record_id for i in r.candidates]
    assert "PN1" in ids and "GN1" in ids
    assert ("purpose_exact", "lexical-definition", "normalized", "為る") in x.calls
    assert ("exact", "normalized", "為る") in x.calls
