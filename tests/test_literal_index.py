from deterministic_japanese_parser_mcp.literal_index import LiteralIndex
from deterministic_japanese_parser_mcp.metaphor import MetaphorMatcher
from deterministic_japanese_parser_mcp.normalizer import normalize_with_map
from deterministic_japanese_parser_mcp.rule_engine import (
    RuleEngine,
    _extract_proven_triggers,
)


def test_literal_index_returns_overlapping_matches_deterministically():
    index = LiteralIndex(["前の案", "案", "直前の案", "前の"])
    assert list(index.find("直前の案と前の案")) == [
        ("前の", 1, 3),
        ("直前の案", 0, 4),
        ("前の案", 1, 4),
        ("案", 3, 4),
        ("前の", 5, 7),
        ("前の案", 5, 8),
        ("案", 7, 8),
    ]


def test_literal_index_rejects_same_root_without_exact_prefix():
    index = LiteralIndex(["あれ", "以前", "変更する"])
    assert not index._has_possible_match("あ" * 20000)
    assert list(index.find("あ" * 20000)) == []


def test_literal_index_lookup_does_not_depend_on_literal_count_for_correctness():
    literals = [f"負荷試験専用{i:05d}" for i in range(5000)]
    target = literals[-1]
    index = LiteralIndex(literals)
    assert list(index.find(f"開始{target}終了")) == [
        (target, 2, 2 + len(target)),
    ]


def test_trigger_selection_prefers_long_mandatory_sequence_over_character_set():
    assert _extract_proven_triggers("(?P<target>[あい])を変更する") == (
        "を変更する",
    )


def test_trigger_selection_preserves_every_branch_alternative():
    assert set(_extract_proven_triggers("(?:変更する|修正する|改善する)")) == {
        "変更する",
        "修正する",
        "改善する",
    }


def test_rule_index_matches_exhaustive_with_large_decoy_dictionary():
    rules = {
        "timeout_ms": 25,
        "intents": {
            "modify": [
                {
                    "id": "REAL",
                    "pattern": "(?P<target>API)だけ変更しろ",
                    "priority": 10,
                    "enabled": True,
                },
                *[
                    {
                        "id": f"DECOY-{index}",
                        "pattern": f"(?P<target>負荷試験専用規則{index:05d})",
                        "priority": 1,
                        "enabled": True,
                    }
                    for index in range(2000)
                ],
            ]
        },
    }
    engine = RuleEngine(rules)
    original = "APIだけ変更しろ"
    normalized, mapping = normalize_with_map(original)
    indexed, indexed_timeouts = engine.extract(normalized, mapping, original)
    exhaustive, exhaustive_timeouts = engine.extract_exhaustive(
        normalized, mapping, original
    )
    assert [item.model_dump() for item in indexed] == [
        item.model_dump() for item in exhaustive
    ]
    assert indexed_timeouts == exhaustive_timeouts == []


def test_metaphor_index_finds_only_matching_entry_in_large_dictionary():
    entries = [
        {
            "expression": f"負荷試験専用比喩{index:05d}",
            "interpretation": f"解釈{index:05d}",
            "domain": "stress",
        }
        for index in range(2000)
    ]
    matcher = MetaphorMatcher({"entries": entries})
    original = "負荷試験専用比喩01999を確認しろ"
    normalized, mapping = normalize_with_map(original)
    result = matcher.find(normalized, mapping, original)
    assert len(result) == 1
    assert result[0].expression == "負荷試験専用比喩01999"
