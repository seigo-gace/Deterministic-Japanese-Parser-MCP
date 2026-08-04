# Japanese Context Collection Research

このDirectoryは、Deterministic Japanese Parser MCPが文脈込みで意味を判定するためのWeb収集台帳です。単語一覧をRuntime辞書へ直接取り込む場所ではありません。

## Files

- [`SOURCE_INVENTORY_2026-08-05.md`](SOURCE_INVENTORY_2026-08-05.md) — 115 Sourceの用途、再配布区分、信頼度、URL
- [`CANDIDATE_SURFACES_2026-08-05.md`](CANDIDATE_SURFACES_2026-08-05.md) — 1,145 Surface Candidate。意味未確定、全件`needs-evidence`
- [`WEB_COLLECTION_AUDIT_2026-08-05.md`](WEB_COLLECTION_AUDIT_2026-08-05.md) — 前回不足の原因、収集構造、Validation、未完了境界

## Non-negotiable gates

1. まとめサイトやCommunity用語集は候補発見に限定する。
2. 意味、極性、強度、現役判定は独立Evidenceなしに確定しない。
3. 商用辞書の語釈、Corpus本文、SNS投稿本文をRepositoryへ転載しない。
4. License、Version、Source URL、Snapshot Hashを固定する。
5. Positive、Negative、Boundary、External Action Safety Testを通過してからRuntimeへ昇格する。
6. 引用、否定、疑問、仮定、伝聞、未解決参照はFail Closedとする。

## Status semantics

- `needs-evidence`: Surface候補のみ。意味を主張しない。
- `needs-review`: Evidenceはあるが、人手ReviewまたはContext Testが不足。
- `ambiguous`: 複数解釈を保持し、Context不足時は解決しない。
- `approved`: Source、License、Context、Test、External Action Riskを検証済み。

このDirectoryへ掲載されたこと自体は、Runtime辞書への採用または再配布許可を意味しません。
