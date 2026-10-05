from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .interpretation_contracts import RecoveryCandidateEvidence, RecoveryOperation
from .models import LexicalCandidate, Token
from .open_lexicon_runtime import OpenLexiconRuntime


@dataclass(frozen=True)
class RecoveryLimits:
    """Bound work; values are runtime policy, not final calibrated acceptance."""

    max_variants_per_span: int = 64
    max_candidates_per_variant: int = 8
    max_options_per_span: int = 16
    max_lattice_nodes: int = 256
    top_k_paths: int = 8

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if value < 1:
                raise ValueError(f"{name} must be >= 1")


@dataclass(frozen=True)
class RecoveryVariant:
    text: str
    operation: RecoveryOperation
    cost: float


@dataclass(frozen=True)
class LatticeOption:
    token_index: int
    original_text: str
    candidate_text: str
    recovery_cost: float
    runtime_record_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    operations: tuple[RecoveryOperation, ...] = ()
    unresolved: bool = False

    @property
    def key(self) -> str:
        operations = ",".join(self.operations)
        records = ",".join(self.runtime_record_ids)
        return f"{self.token_index}:{self.candidate_text}:{operations}:{records}"


@dataclass(frozen=True)
class SentencePath:
    options: tuple[LatticeOption, ...]
    recovery_cost: float
    unresolved_count: int

    @property
    def key(self) -> str:
        return "|".join(option.key for option in self.options)

    @property
    def text_sequence(self) -> tuple[str, ...]:
        return tuple(option.candidate_text for option in self.options)


@dataclass(frozen=True)
class RecoveryDecision:
    decision: str
    selected_path: SentencePath | None
    absolute_score: float | None
    margin: float | None
    competing_path_keys: tuple[str, ...]


_DAKUTEN_PAIRS = (
    ("か", "が"), ("き", "ぎ"), ("く", "ぐ"), ("け", "げ"), ("こ", "ご"),
    ("さ", "ざ"), ("し", "じ"), ("す", "ず"), ("せ", "ぜ"), ("そ", "ぞ"),
    ("た", "だ"), ("ち", "ぢ"), ("つ", "づ"), ("て", "で"), ("と", "ど"),
    ("は", "ば"), ("ひ", "び"), ("ふ", "ぶ"), ("へ", "べ"), ("ほ", "ぼ"),
    ("ハ", "バ"), ("ヒ", "ビ"), ("フ", "ブ"), ("ヘ", "ベ"), ("ホ", "ボ"),
    ("カ", "ガ"), ("キ", "ギ"), ("ク", "グ"), ("ケ", "ゲ"), ("コ", "ゴ"),
    ("サ", "ザ"), ("シ", "ジ"), ("ス", "ズ"), ("セ", "ゼ"), ("ソ", "ゾ"),
    ("タ", "ダ"), ("チ", "ヂ"), ("ツ", "ヅ"), ("テ", "デ"), ("ト", "ド"),
)
_HANDAKUTEN_PAIRS = (
    ("は", "ぱ"), ("ひ", "ぴ"), ("ふ", "ぷ"), ("へ", "ぺ"), ("ほ", "ぽ"),
    ("ハ", "パ"), ("ヒ", "ピ"), ("フ", "プ"), ("ヘ", "ペ"), ("ホ", "ポ"),
)
_SMALL_KANA_PAIRS = (
    ("ぁ", "あ"), ("ぃ", "い"), ("ぅ", "う"), ("ぇ", "え"), ("ぉ", "お"),
    ("ゃ", "や"), ("ゅ", "ゆ"), ("ょ", "よ"), ("っ", "つ"), ("ゎ", "わ"),
    ("ァ", "ア"), ("ィ", "イ"), ("ゥ", "ウ"), ("ェ", "エ"), ("ォ", "オ"),
    ("ャ", "ヤ"), ("ュ", "ユ"), ("ョ", "ヨ"), ("ッ", "ツ"), ("ヮ", "ワ"),
)


def _script_variant(text: str) -> str | None:
    converted: list[str] = []
    changed = False
    for char in text:
        if "ぁ" <= char <= "ゖ":
            converted.append(chr(ord(char) + 0x60))
            changed = True
        elif "ァ" <= char <= "ヶ":
            converted.append(chr(ord(char) - 0x60))
            changed = True
        else:
            converted.append(char)
    value = "".join(converted)
    return value if changed and value != text else None


def _single_replacements(
    text: str,
    pairs: Sequence[tuple[str, str]],
    operation: RecoveryOperation,
    cost: float,
) -> Iterable[RecoveryVariant]:
    mapping: dict[str, str] = {}
    for left, right in pairs:
        mapping[left] = right
        mapping[right] = left
    for index, char in enumerate(text):
        replacement = mapping.get(char)
        if replacement is not None:
            yield RecoveryVariant(
                text[:index] + replacement + text[index + 1 :],
                operation,
                cost,
            )


def generate_local_variants(
    text: str,
    *,
    limits: RecoveryLimits,
    insertion_alphabet: Sequence[str] = (),
    substitution_alphabet: Sequence[str] = (),
    rule_variants: Mapping[str, Sequence[tuple[str, RecoveryOperation, float]]] | None = None,
) -> list[RecoveryVariant]:
    """Generate finite local candidates only; this function never chooses a correction."""
    if not text:
        return []

    variants: dict[str, RecoveryVariant] = {}

    def add(variant: RecoveryVariant) -> None:
        if not variant.text or variant.text == text:
            return
        current = variants.get(variant.text)
        if current is None or (variant.cost, variant.operation) < (
            current.cost,
            current.operation,
        ):
            variants[variant.text] = variant

    script = _script_variant(text)
    if script:
        add(RecoveryVariant(script, "kana_variant", 0.25))

    for variant in _single_replacements(
        text, _DAKUTEN_PAIRS, "dakuten_handakuten", 0.35
    ):
        add(variant)
    for variant in _single_replacements(
        text, _HANDAKUTEN_PAIRS, "dakuten_handakuten", 0.35
    ):
        add(variant)
    for variant in _single_replacements(text, _SMALL_KANA_PAIRS, "small_kana", 0.4):
        add(variant)

    for index, char in enumerate(text):
        if char == "ー":
            add(RecoveryVariant(text[:index] + text[index + 1 :], "long_vowel", 0.45))

    for index in range(len(text) - 1):
        if text[index] != text[index + 1]:
            add(
                RecoveryVariant(
                    text[:index]
                    + text[index + 1]
                    + text[index]
                    + text[index + 2 :],
                    "transposition",
                    0.8,
                )
            )

    if len(text) > 1:
        for index in range(len(text)):
            add(RecoveryVariant(text[:index] + text[index + 1 :], "deletion", 1.0))

    # Insertion/substitution alphabets are intentionally caller supplied. Their
    # final contents must be calibrated by Golden/Noise/Latency evidence rather
    # than guessed inside the recovery engine.
    for index in range(len(text) + 1):
        for char in insertion_alphabet:
            if char:
                add(
                    RecoveryVariant(
                        text[:index] + char + text[index:],
                        "insertion",
                        1.0,
                    )
                )
    for index in range(len(text)):
        for char in substitution_alphabet:
            if char and char != text[index]:
                add(
                    RecoveryVariant(
                        text[:index] + char + text[index + 1 :],
                        "substitution",
                        1.0,
                    )
                )

    for candidate, operation, cost in (rule_variants or {}).get(text, ()):
        add(RecoveryVariant(candidate, operation, float(cost)))

    ordered = sorted(
        variants.values(),
        key=lambda item: (item.cost, item.operation, item.text),
    )
    return ordered[: limits.max_variants_per_span]


def _land_variant(
    runtime: OpenLexiconRuntime,
    variant: RecoveryVariant,
    *,
    limits: RecoveryLimits,
) -> RecoveryCandidateEvidence | None:
    candidates, _ = runtime.exact_lookup(
        variant.text,
        max_candidates=limits.max_candidates_per_variant,
    )
    if not candidates:
        candidates, _ = runtime.reading_lookup(
            variant.text,
            max_candidates=limits.max_candidates_per_variant,
        )
    if not candidates:
        return None
    record_ids = tuple(sorted({candidate.record_id for candidate in candidates}))
    evidence_ids = tuple(f"runtime:{record_id}" for record_id in record_ids)
    return RecoveryCandidateEvidence(
        candidate_text=variant.text,
        runtime_record_ids=list(record_ids),
        operations=[variant.operation],
        recovery_cost=variant.cost,
        score_components={"recovery_cost": -variant.cost},
        evidence_ids=list(evidence_ids),
    )


def recover_token_candidates(
    token: Token,
    runtime: OpenLexiconRuntime,
    *,
    limits: RecoveryLimits,
    insertion_alphabet: Sequence[str] = (),
    substitution_alphabet: Sequence[str] = (),
    rule_variants: Mapping[str, Sequence[tuple[str, RecoveryOperation, float]]] | None = None,
    force: bool = False,
) -> list[RecoveryCandidateEvidence]:
    """Return landed recovery evidence, never an automatically selected correction."""
    if not force and token.lexical_status != "NO_MATCH":
        return []
    if not runtime.available:
        return []

    landed: list[RecoveryCandidateEvidence] = []
    for variant in generate_local_variants(
        token.surface,
        limits=limits,
        insertion_alphabet=insertion_alphabet,
        substitution_alphabet=substitution_alphabet,
        rule_variants=rule_variants,
    ):
        evidence = _land_variant(runtime, variant, limits=limits)
        if evidence is not None:
            landed.append(evidence)
        if len(landed) >= limits.max_options_per_span:
            break
    return landed


def build_candidate_lattice(
    tokens: Sequence[Token],
    recoveries: Mapping[int, Sequence[RecoveryCandidateEvidence]],
    *,
    limits: RecoveryLimits,
) -> list[SentencePath]:
    """Build bounded whole-sentence alternatives without declaring a winner."""
    paths = [SentencePath(options=(), recovery_cost=0.0, unresolved_count=0)]
    node_count = 0

    for token_index, token in enumerate(tokens):
        options: list[LatticeOption] = []
        if token.lexical_status != "NO_MATCH":
            record_ids = tuple(
                sorted({candidate.record_id for candidate in token.lexical_candidates})
            )
            options.append(
                LatticeOption(
                    token_index=token_index,
                    original_text=token.surface,
                    candidate_text=token.surface,
                    recovery_cost=0.0,
                    runtime_record_ids=record_ids,
                    evidence_ids=tuple(f"runtime:{rid}" for rid in record_ids),
                )
            )
        else:
            # Preserve an unresolved original path. Unknown/new expressions are
            # therefore never forced into a typo correction merely because a
            # nearby dictionary landing exists.
            options.append(
                LatticeOption(
                    token_index=token_index,
                    original_text=token.surface,
                    candidate_text=token.surface,
                    recovery_cost=0.0,
                    unresolved=True,
                )
            )
            for evidence in recoveries.get(token_index, ())[: limits.max_options_per_span]:
                options.append(
                    LatticeOption(
                        token_index=token_index,
                        original_text=token.surface,
                        candidate_text=evidence.candidate_text,
                        recovery_cost=evidence.recovery_cost,
                        runtime_record_ids=tuple(evidence.runtime_record_ids),
                        evidence_ids=tuple(evidence.evidence_ids),
                        operations=tuple(evidence.operations),
                    )
                )

        next_paths: list[SentencePath] = []
        for path in paths:
            for option in options:
                node_count += 1
                if node_count > limits.max_lattice_nodes:
                    break
                next_paths.append(
                    SentencePath(
                        options=(*path.options, option),
                        recovery_cost=path.recovery_cost + option.recovery_cost,
                        unresolved_count=path.unresolved_count + int(option.unresolved),
                    )
                )
            if node_count > limits.max_lattice_nodes:
                break
        if not next_paths:
            break
        next_paths.sort(
            key=lambda path: (
                path.recovery_cost,
                path.unresolved_count,
                path.text_sequence,
            )
        )
        paths = next_paths[: limits.top_k_paths]

    return paths[: limits.top_k_paths]


def decide_sentence_recovery(
    paths: Sequence[SentencePath],
    *,
    path_scores: Mapping[str, float],
    minimum_score: float,
    minimum_margin: float,
) -> RecoveryDecision:
    """Apply explicit evidence/margin gates; absent evidence never resolves."""
    scored = [
        (float(path_scores[path.key]), path)
        for path in paths
        if path.key in path_scores
    ]
    scored.sort(key=lambda item: (-item[0], item[1].recovery_cost, item[1].key))
    if not scored:
        return RecoveryDecision("INSUFFICIENT", None, None, None, ())

    top_score, top_path = scored[0]
    if top_score < minimum_score:
        return RecoveryDecision(
            "INSUFFICIENT",
            None,
            top_score,
            None,
            tuple(path.key for _, path in scored[1:]),
        )

    second_score = scored[1][0] if len(scored) > 1 else None
    margin = top_score - second_score if second_score is not None else top_score
    if margin < minimum_margin:
        return RecoveryDecision(
            "AMBIGUOUS",
            None,
            top_score,
            margin,
            tuple(path.key for _, path in scored[1:]),
        )

    if top_path.unresolved_count:
        return RecoveryDecision(
            "INSUFFICIENT",
            None,
            top_score,
            margin,
            tuple(path.key for _, path in scored[1:]),
        )

    return RecoveryDecision(
        "RESOLVED",
        top_path,
        top_score,
        margin,
        tuple(path.key for _, path in scored[1:]),
    )
