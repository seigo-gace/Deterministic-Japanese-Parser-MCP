from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import LexicalCandidate, Token
from .purpose_routing import routes_for_roles, semantic_targets_for_roles


class LexiconLookup(Protocol):
    def purpose_exact_lookup(self, text: str, *, role: str, match_type: str = "surface", max_candidates: int = 8) -> tuple[list[LexicalCandidate], int]: ...
    def purpose_reading_lookup(self, reading: str, *, role: str, surface: str | None = None, normalized: str | None = None, max_candidates: int = 8) -> tuple[list[LexicalCandidate], int]: ...
    def exact_lookup(self, text: str, *, match_type: str = "surface", max_candidates: int = 8) -> tuple[list[LexicalCandidate], int]: ...
    def reading_lookup(self, reading: str, *, surface: str | None = None, normalized: str | None = None, max_candidates: int = 8) -> tuple[list[LexicalCandidate], int]: ...


@dataclass(frozen=True)
class RetrievalTrace:
    source_roles: tuple[str, ...]
    semantic_targets: tuple[str, ...]
    lanes_attempted: tuple[str, ...]
    purpose_lane_hits: int
    general_lane_hits: int
    purpose_index_available: bool


@dataclass(frozen=True)
class RetrievalResult:
    candidates: tuple[LexicalCandidate, ...]
    candidate_total: int
    trace: RetrievalTrace


class RetrievalRouter:
    """Deterministic progressive retrieval.

    Purpose roles select permitted/priority retrieval lanes only. They never
    create a sense, intent, task, or executable action. General exact lookup
    remains a fallback so Purpose Role cannot become Meaning Authority.
    """

    def __init__(self, lexicon: LexiconLookup):
        self.lexicon = lexicon

    @staticmethod
    def _merge(output, seen, candidates, limit):
        added = 0
        for candidate in candidates:
            if candidate.record_id in seen:
                continue
            seen.add(candidate.record_id)
            if len(output) < limit:
                output.append(candidate)
                added += 1
        return added

    def retrieve_token(self, token: Token, *, source_roles: list[str], max_candidates: int = 8) -> RetrievalResult:
        route = routes_for_roles(source_roles)
        if not route["routing_valid"]:
            raise ValueError(f"unroutable purpose roles={route['unknown_roles']}")
        roles = tuple(route["source_roles"])
        targets = tuple(semantic_targets_for_roles(list(roles)))
        limit = max(1, int(max_candidates))
        output = []
        seen = set()
        lanes = []
        purpose_hits = 0
        general_hits = 0
        purpose_index_available = True

        for role in roles:
            try:
                lanes.append(f"purpose:{role}:surface")
                values, _ = self.lexicon.purpose_exact_lookup(token.surface, role=role, match_type="surface", max_candidates=limit)
                purpose_hits += self._merge(output, seen, values, limit)
                if token.normalized != token.surface and not values and len(output) < limit:
                    lanes.append(f"purpose:{role}:normalized")
                    values, _ = self.lexicon.purpose_exact_lookup(token.normalized, role=role, match_type="normalized", max_candidates=limit)
                    purpose_hits += self._merge(output, seen, values, limit)
            except ValueError:
                continue
            except RuntimeError:
                purpose_index_available = False
                break

        lanes.append("general:surface")
        values, total = self.lexicon.exact_lookup(token.surface, match_type="surface", max_candidates=limit)
        general_hits += self._merge(output, seen, values, limit)
        general_total = total

        if token.normalized != token.surface and not values and len(output) < limit:
            lanes.append("general:normalized")
            values, total = self.lexicon.exact_lookup(token.normalized, match_type="normalized", max_candidates=limit)
            general_hits += self._merge(output, seen, values, limit)
            general_total = max(general_total, total)

        if token.reading and not output and len(output) < limit:
            if purpose_hits == 0:
                for role in roles:
                    if not purpose_index_available or len(output) >= limit:
                        break
                    try:
                        lanes.append(f"purpose:{role}:reading")
                        values, _ = self.lexicon.purpose_reading_lookup(token.reading, role=role, surface=token.surface, normalized=token.normalized, max_candidates=limit)
                        purpose_hits += self._merge(output, seen, values, limit)
                    except ValueError:
                        continue
                    except RuntimeError:
                        purpose_index_available = False
                        break
            if len(output) < limit:
                lanes.append("general:reading")
                values, total = self.lexicon.reading_lookup(token.reading, surface=token.surface, normalized=token.normalized, max_candidates=limit)
                general_hits += self._merge(output, seen, values, limit)
                general_total = max(general_total, total)

        return RetrievalResult(
            candidates=tuple(output),
            candidate_total=max(len(seen), general_total),
            trace=RetrievalTrace(
                source_roles=roles,
                semantic_targets=targets,
                lanes_attempted=tuple(lanes),
                purpose_lane_hits=purpose_hits,
                general_lane_hits=general_hits,
                purpose_index_available=purpose_index_available,
            ),
        )
