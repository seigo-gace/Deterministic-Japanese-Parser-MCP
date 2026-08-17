from __future__ import annotations

import json
from typing import Any

from .final_runtime import FinalRuntimeLexicon as _IndexedFinalRuntimeLexicon
from .models import LexicalCandidate


class FinalRuntimeLexicon(_IndexedFinalRuntimeLexicon):
    """Expose completed-runtime rich data through the MCP lexical model.

    The base runtime owns verified SQLite storage and lookup. This bridge only
    carries source-backed rich fields into LexicalCandidate.runtime_data so the
    MCP response can retain them without promoting them to a selected sense,
    intent, task, or external action.
    """

    @staticmethod
    def _candidate(
        row,
        *,
        matched_text: str,
        match_type: str,
    ) -> LexicalCandidate:
        candidate = _IndexedFinalRuntimeLexicon._candidate(
            row,
            matched_text=matched_text,
            match_type=match_type,
        )
        runtime_data: dict[str, Any] = {}
        rich_payload = row["rich_payload_json"]
        if rich_payload:
            value = json.loads(rich_payload)
            if isinstance(value, dict):
                runtime_data = value
        return candidate.model_copy(update={"runtime_data": runtime_data})

    def support_records(
        self,
        *,
        record_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Read support-pack payloads without fabricating lexical entries."""
        if not self.available or self._connection is None:
            return []
        bounded_limit = max(1, min(int(limit), 1000))
        if record_type is None:
            rows = self._connection.execute(
                "SELECT payload_json FROM support ORDER BY support_id LIMIT ?",
                (bounded_limit,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                """
                SELECT payload_json
                FROM support
                WHERE record_type = ?
                ORDER BY support_id
                LIMIT ?
                """,
                (record_type, bounded_limit),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]
