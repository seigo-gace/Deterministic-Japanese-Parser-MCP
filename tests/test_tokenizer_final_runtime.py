from __future__ import annotations

from deterministic_japanese_parser_mcp.models import LexicalCandidate, OriginalSpan, Token
from deterministic_japanese_parser_mcp.tokenizer import JapaneseTokenizer


class _Runtime:
    def __init__(self, candidate: LexicalCandidate | None, total: int, *, available: bool = True):
        self.available = available
        self.candidate = candidate
        self.total = total
        self.annotate_calls = 0

    def lookup_token(self, token: Token, *, max_candidates: int = 8) -> Token:
        candidates = [self.candidate] if self.candidate is not None else []
        status = "NO_MATCH" if self.total == 0 else ("MATCHED" if self.total == 1 else "AMBIGUOUS")
        return token.model_copy(update={
            "lexical_candidates": candidates[:max_candidates],
            "lexical_candidate_total": self.total,
            "lexical_status": status,
        })

    def annotate_tokens(self, tokens: list[Token], *, max_candidates: int = 8) -> list[Token]:
        self.annotate_calls += 1
        return [self.lookup_token(token, max_candidates=max_candidates) for token in tokens]


def _candidate(record_id: str, dataset: str) -> LexicalCandidate:
    return LexicalCandidate(
        record_id=record_id,
        lemma="生",
        matched_text="生",
        match_type="surface",
        readings=["ナマ"],
        part_of_speech=["名詞"],
        source_dataset=dataset,
    )


def _token() -> Token:
    return Token(
        surface="生",
        normalized="生",
        reading="ナマ",
        pos=["名詞"],
        span=OriginalSpan(start=0, end=1, source_text="生"),
    )


def test_completed_runtime_candidates_are_first_and_legacy_candidates_are_retained():
    tokenizer = JapaneseTokenizer.__new__(JapaneseTokenizer)
    tokenizer.final_runtime = _Runtime(_candidate("DJPMCP-1", "final"), 1)
    tokenizer.open_lexicon = _Runtime(_candidate("R1", "legacy"), 1)

    annotated = tokenizer._annotate([_token()])[0]

    assert [item.record_id for item in annotated.lexical_candidates] == ["DJPMCP-1", "R1"]
    assert annotated.lexical_candidate_total == 2
    assert annotated.lexical_status == "AMBIGUOUS"


def test_legacy_path_is_unchanged_when_completed_runtime_is_unavailable():
    tokenizer = JapaneseTokenizer.__new__(JapaneseTokenizer)
    tokenizer.final_runtime = _Runtime(None, 0, available=False)
    tokenizer.open_lexicon = _Runtime(_candidate("R1", "legacy"), 1)

    annotated = tokenizer._annotate([_token()])[0]

    assert tokenizer.open_lexicon.annotate_calls == 1
    assert annotated.lexical_candidates[0].record_id == "R1"
    assert annotated.lexical_status == "MATCHED"
