from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .interpretation_contracts import RecoveryCandidateEvidence, RecoveryOperation
from .models import Token
from .open_lexicon_runtime import OpenLexiconRuntime


@dataclass(frozen=True)
class RecoveryLimits:
    """Bound work; values are runtime policy, not final calibrated acceptance."""

    max_variants_per_span: int = 64
    max_candidates_per_variant: int = 8
    max_options_per_span: int = 16
    max_boundary_options: int = 16
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
    start_token: int
    end_token_exclusive: int
    original_text: str
    candidate_text: str
    recovery_cost: float
    runtime_record_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    operations: tuple[RecoveryOperation, ...] = ()
    candidate_segments: tuple[str, ...] = ()
    unresolved: bool = False

    def __post_init__(self) -> None:
        if self.start_token < 0 or self.end_token_exclusive <= self.start_token:
            raise ValueError("invalid lattice token span")
        if self.recovery_cost < 0:
            raise ValueError("recovery_cost must be >= 0")

    @property
    def segments(self) -> tuple[str, ...]:
        return self.candidate_segments or (self.candidate_text,)

    @property
    def key(self) -> str:
        operations = ",".join(self.operations)
        records = ",".join(self.runtime_record_ids)
        segments = "/".join(self.segments)
        return (
            f"{self.start_token}-{self.end_token_exclusive}:"
            f"{segments}:{operations}:{records}:{int(self.unresolved)}"
        )


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
        return tuple(
            segment
            for option in self.options
            for segment in option.segments
        )


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
    ("カ", "ガ"), ("キ", "ギ"), ("ク", "グ"), ("ケ", "ゲ"), ("コ", "ゴ"),
    ("サ", "ザ"), ("シ", "ジ"), ("ス", "ズ"), ("セ", "ゼ"), ("ソ", "ゾ"),
    ("タ", "ダ"), ("チ", "ヂ"), ("ツ", "ヅ"), ("テ", "デ"), ("ト", "ド"),
    ("ハ", "バ"), ("ヒ", "ビ"), ("フ", "ブ"), ("ヘ", "ベ"), ("ホ", "ボ"),
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
    """Generate finite local candidates only; never choose a correction here."""
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

    # Insertion/substitution alphabets are caller supplied deliberately. Final
    # alphabets and costs require Golden/Noise/Latency calibration rather than
    # an unverified permanent guess inside the engine.
    for index in range(len(text) + 1):
        for char in insertion_alphabet:
            if char:
                add(RecoveryVariant(text[:index] + char + text[index:], "insertion", 1.0))
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

    return sorted(
        variants.values(),
        key=lambda item: (item.cost, item.operation, item.text),
    )[: limits.max_variants_per_span]


def _record_ids(candidates: Sequence) -> tuple[str, ...]:
    return tuple(sorted({candidate.record_id for candidate in candidates}))


def _land_exact(
    runtime: OpenLexiconRuntime,
    text: str,
    *,
    limits: RecoveryLimits,
) -> tuple[str, ...]:
    candidates, _ = runtime.exact_lookup(
        text,
        max_candidates=limits.max_candidates_per_variant,
    )
    return _record_ids(candidates)


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
    record_ids = _record_ids(candidates)
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
    """Return landed evidence; never automatically select a correction."""
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


def recover_boundary_options(
    tokens: Sequence[Token],
    runtime: OpenLexiconRuntime,
    *,
    limits: RecoveryLimits,
    force: bool = False,
) -> dict[int, list[LatticeOption]]:
    """Create bounded split/merge paths only when every segment lands exactly."""
    if not runtime.available:
        return {}
    by_start: dict[int, list[LatticeOption]] = {}

    def add(option: LatticeOption) -> None:
        bucket = by_start.setdefault(option.start_token, [])
        if len(bucket) < limits.max_boundary_options:
            bucket.append(option)

    for index, token in enumerate(tokens):
        if force or token.lexical_status == "NO_MATCH":
            for split_at in range(1, len(token.surface)):
                left = token.surface[:split_at]
                right = token.surface[split_at:]
                left_ids = _land_exact(runtime, left, limits=limits)
                right_ids = _land_exact(runtime, right, limits=limits)
                if not left_ids or not right_ids:
                    continue
                record_ids = tuple(sorted({*left_ids, *right_ids}))
                add(
                    LatticeOption(
                        start_token=index,
                        end_token_exclusive=index + 1,
                        original_text=token.surface,
                        candidate_text=token.surface,
                        candidate_segments=(left, right),
                        recovery_cost=0.9,
                        runtime_record_ids=record_ids,
                        evidence_ids=tuple(f"runtime:{rid}" for rid in record_ids),
                        operations=("split",),
                    )
                )

        if index + 1 >= len(tokens):
            continue
        right_token = tokens[index + 1]
        if not force and (
            token.lexical_status != "NO_MATCH"
            and right_token.lexical_status != "NO_MATCH"
        ):
            continue
        merged = token.surface + right_token.surface
        merged_ids = _land_exact(runtime, merged, limits=limits)
        if not merged_ids:
            continue
        add(
            LatticeOption(
                start_token=index,
                end_token_exclusive=index + 2,
                original_text=merged,
                candidate_text=merged,
                candidate_segments=(merged,),
                recovery_cost=0.9,
                runtime_record_ids=merged_ids,
                evidence_ids=tuple(f"runtime:{rid}" for rid in merged_ids),
                operations=("merge",),
            )
        )

    for options in by_start.values():
        options.sort(key=lambda item: (item.recovery_cost, item.key))
    return by_start


def _normal_option(token_index: int, token: Token) -> LatticeOption:
    if token.lexical_status == "NO_MATCH":
        return LatticeOption(
            start_token=token_index,
            end_token_exclusive=token_index + 1,
            original_text=token.surface,
            candidate_text=token.surface,
            recovery_cost=0.0,
            unresolved=True,
        )
    record_ids = tuple(
        sorted({candidate.record_id for candidate in token.lexical_candidates})
    )
    return LatticeOption(
        start_token=token_index,
        end_token_exclusive=token_index + 1,
        original_text=token.surface,
        candidate_text=token.surface,
        recovery_cost=0.0,
        runtime_record_ids=record_ids,
        evidence_ids=tuple(f"runtime:{rid}" for rid in record_ids),
    )


def _original_path(tokens: Sequence[Token]) -> SentencePath:
    options = tuple(_normal_option(index, token) for index, token in enumerate(tokens))
    return SentencePath(
        options=options,
        recovery_cost=0.0,
        unresolved_count=sum(int(option.unresolved) for option in options),
    )


def build_candidate_lattice(
    tokens: Sequence[Token],
    recoveries: Mapping[int, Sequence[RecoveryCandidateEvidence]],
    *,
    limits: RecoveryLimits,
    boundary_options: Mapping[int, Sequence[LatticeOption]] | None = None,
) -> list[SentencePath]:
    """Build bounded sentence paths including split/merge without choosing meaning."""
    if not tokens:
        return []

    edges: dict[int, list[LatticeOption]] = {}
    for token_index, token in enumerate(tokens):
        token_edges = [_normal_option(token_index, token)]
        if token.lexical_status == "NO_MATCH":
            for evidence in recoveries.get(token_index, ())[: limits.max_options_per_span]:
                token_edges.append(
                    LatticeOption(
                        start_token=token_index,
                        end_token_exclusive=token_index + 1,
                        original_text=token.surface,
                        candidate_text=evidence.candidate_text,
                        recovery_cost=evidence.recovery_cost,
                        runtime_record_ids=tuple(evidence.runtime_record_ids),
                        evidence_ids=tuple(evidence.evidence_ids),
                        operations=tuple(evidence.operations),
                    )
                )
        token_edges.extend((boundary_options or {}).get(token_index, ()))
        edges[token_index] = sorted(
            token_edges,
            key=lambda option: (
                option.unresolved,
                option.recovery_cost,
                option.key,
            ),
        )[: limits.max_options_per_span + limits.max_boundary_options + 1]

    frontier: dict[int, list[SentencePath]] = {
        0: [SentencePath(options=(), recovery_cost=0.0, unresolved_count=0)]
    }
    node_count = 0
    token_count = len(tokens)

    for position in range(token_count):
        current_paths = frontier.get(position, [])
        if not current_paths:
            continue
        for path in current_paths:
            for option in edges.get(position, ()):
                if option.end_token_exclusive > token_count:
                    continue
                node_count += 1
                if node_count > limits.max_lattice_nodes:
                    # Budget exhaustion is not a completed interpretation.
                    # Returning even the baseline here would bypass the bounded
                    # work contract, so fail closed and let the caller retain
                    # the original unresolved input outside the lattice.
                    return []
                candidate_path = SentencePath(
                    options=(*path.options, option),
                    recovery_cost=path.recovery_cost + option.recovery_cost,
                    unresolved_count=path.unresolved_count + int(option.unresolved),
                )
                destination = option.end_token_exclusive
                bucket = frontier.setdefault(destination, [])
                bucket.append(candidate_path)
                bucket.sort(
                    key=lambda item: (
                        item.unresolved_count,
                        item.recovery_cost,
                        item.key,
                    )
                )
                del bucket[limits.top_k_paths :]

    return _finalize_paths(frontier.get(token_count, []), tokens, limits=limits)


def _finalize_paths(
    paths: Sequence[SentencePath],
    tokens: Sequence[Token],
    *,
    limits: RecoveryLimits,
) -> list[SentencePath]:
    ordered = sorted(
        {path.key: path for path in paths}.values(),
        key=lambda item: (item.unresolved_count, item.recovery_cost, item.key),
    )
    baseline = _original_path(tokens)
    if baseline.key not in {path.key for path in ordered}:
        if len(ordered) >= limits.top_k_paths:
            ordered = ordered[: limits.top_k_paths - 1]
        ordered.append(baseline)
    return ordered[: limits.top_k_paths]


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
