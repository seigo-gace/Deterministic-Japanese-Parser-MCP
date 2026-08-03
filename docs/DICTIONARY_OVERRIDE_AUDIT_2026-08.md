# Dictionary Override Audit 2026-08

## Why this file exists

The comprehensive second-wave expansion initially revealed three different collision classes that must not be silently collapsed:

1. A new source file intentionally provides a richer definition for an expression already present in an older category.
2. A new canonical expression collides with an older alias owned by another expression.
3. A natural Gold sentence uses a grammatical surface variation that is not the literal canonical string.

`dictionaries/system/metaphors/overrides.json` is the explicit control file for these cases. The loader, validator, Gold loader, and coverage tests all enforce this file. No implicit exception is allowed.

## Declared definition overrides

The following ten expressions occur in an older category and in the second-wave source categories. Their final definition follows deterministic file order and the duplicate is permitted only because it is listed under `override_expressions`:

- `話を戻す`
- `話を広げる`
- `詰まりを取る`
- `後手に回る`
- `逃げ道を作る`
- `行間を読む`
- `入口を絞る`
- `鍵をかける`
- `入口を広げる`
- `落とし所を探る`

The validator fails if an undeclared duplicate source expression appears or if a declared override no longer has two source definitions.

## Tombstoned alias collisions

The following four second-wave source expressions collide with aliases already owned by older canonical entries. They are removed from the effective dictionary through `disabled_expressions` and replaced with unique expressions:

| Tombstoned surface | Replacement |
|---|---|
| `腑に落ちる` | `理解が腹に落ちる` |
| `火種を消す` | `問題の芽を消す` |
| `ボールを渡す` | `担当のバトンを渡す` |
| `ボールを抱える` | `判断を手元に抱える` |

The tombstoned surfaces remain auditable in their source category files but cannot become active runtime entries.

## Other replacement entries

Ten exact duplicate expressions were also replaced in second-wave Gold coverage so that the expansion adds genuinely new effective coverage instead of counting the same canonical expression twice:

| Existing expression | New effective expression |
|---|---|
| `話を戻す` | `議論を本筋へ戻す` |
| `話を広げる` | `観点を広げる` |
| `詰まりを取る` | `進行の詰まりを解く` |
| `後手に回る` | `対応が後追いになる` |
| `逃げ道を作る` | `撤退経路を用意する` |
| `行間を読む` | `書かれていない意図を読む` |
| `入口を絞る` | `受付経路を限定する` |
| `鍵をかける` | `アクセスに鍵をかける` |
| `入口を広げる` | `利用開始経路を増やす` |
| `落とし所を探る` | `合意点を探る` |

Together with the four tombstone replacements, this preserves exactly 252 genuinely covered second-wave effective expressions and 452 effective expressions overall.

## Pattern overrides

Sixteen active expressions receive explicit regex surfaces for natural Japanese word order or English/Japanese technical-token variation:

- `対象を囲い込む`
- `先に手を打つ`
- `リスクを抱える`
- `リスクを落とす`
- `関係者を立てる`
- `データを流す`
- `データを受ける`
- `データを吐き出す`
- `データを詰め替える`
- `依存を閉じ込める`
- `Payloadを丸める`
- `Schemaを寄せる`
- `防御の盾を置く`
- `画面を詰め込む`
- `画面に余白を作る`
- `まずこれだけやる`

Pattern overrides do not bypass context policy. They only provide additional candidate surfaces; context requirements and final semantic validation still apply.

## Gold override policy

`tests/gold/cases-99-overrides.json` declares `last_case_id_wins` and replaces fourteen source Gold cases with the unique replacement expressions above. The effective Gold loader uses case ID as the stable identity and produces 649 unique cases.

A repeated Gold ID in any file without the explicit override policy is a validation failure.

## Enforced invariants

CI and offline release validation require all of the following:

- 452 effective expressions
- no active duplicate canonical expressions
- no active surface/alias collisions
- every undeclared duplicate source expression fails validation
- every declared override still has multiple source definitions
- all tombstoned entries are absent from the runtime dictionary
- all fourteen replacement entries are active
- all sixteen pattern overrides target active entries
- 252 second-wave effective expressions each have an effective Gold case and are detected
- 649 effective Gold case IDs
- indexed and exhaustive results remain semantically identical
