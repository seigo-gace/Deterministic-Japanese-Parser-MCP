# Supported Semantic Quality Contract

## 日本語

### 目的

この契約は、Deterministic Japanese Parser MCPが現在実装している意味処理能力を、再現可能なCase集合で測定するための公開品質Gateです。

この数値は「あらゆる日本語を人間と同等に理解する割合」ではありません。Version固定された辞書、Rule、Sense Profile、Context Resolver、Discourse Rule、External Action Guardで**対応対象としている機能**の正確性を表します。

### 対象能力

- 高影響多義語の文脈別Sense選択
- Sense Candidate、Evidence、ConfidenceのMeaning Graph出力
- 省略されたTargetとゼロ代名詞の局所Antecedent補完
- 前者／後者、型付き指示語、Known Entityを使った参照解決
- 婉曲依頼、希望、約束、拒否、保留、懸念、確認要求、承認、却下等のSpeech Act
- 丁寧な依頼と能力質問の分離
- 因果、対比、言換え、根拠、順序、選択肢、目的のDiscourse Edge
- Quote、Question、Commitment、Desire、Refusal、曖昧Sense、未解決TargetのExternal Action Fail Closed

### 2段階Corpus

#### Supported Profile Contract

Runtime Profileに登録されたSense／Pragmaticsと、設計上の省略・談話・参照・安全Caseを検証します。

- Case数：**167**
- Runtime Profileと期待構造の整合を確認
- `scripts/semantic_quality_contract.py`

#### Independent Holdout Contract

Runtimeが読み込まない独立Corpusです。Profileの例文とは異なる表現、活用、対象、文脈、攻撃的External Action Caseを使用します。

- Case数：**130**
- Runtime Profileへ未登録
- `tests/gold/semantic-quality-holdout.yaml`
- `scripts/semantic_holdout_contract.py`

Holdout期待値の修正は、理由を記載したAudit Fileへ分離します。現在の2件は、Contextなしの`この設定`／`このファイル`を実行許可する期待値がFail Closed原則に反していたため、実行拒否へ訂正しています。

- `tests/gold/semantic-quality-holdout-overrides.yaml`

### 合格条件

| Gate | 条件 |
|---|---:|
| Macro Accuracy | **95%以上** |
| 各Category Accuracy | **90%以上** |
| External Action Safety | **100%** |
| Python | **3.10 / 3.12** |
| Offline Wheel | **同一契約を再実行** |

### 現行検証結果

| Corpus | Case | Passed | Macro Accuracy |
|---|---:|---:|---:|
| Supported Profile | 167 | 167 | **100%** |
| Independent Holdout | 130 | 130 | **100%** |
| 合計 | 297 | 297 | **100%** |

Holdout Category：

| Category | Passed / Total |
|---|---:|
| Sense Selection | 52 / 52 |
| Pragmatics | 28 / 28 |
| Ellipsis Resolution | 12 / 12 |
| Discourse Relations | 10 / 10 |
| Reference Resolution | 8 / 8 |
| External Action Safety | 20 / 20 |

この結果は対応対象内の品質を示します。未登録語義、皮肉、広範な常識推論、自由な長文談話理解、地域差・世代差の大きい俗語等を100%理解することを意味しません。

### 実装構造

```text
Rule / Morphology / Grammar Kernel
    ↓
Meaning Graph
    ↓
Semantic Profile Stage
    ├─ Sense candidate scoring
    ├─ Pragmatic speech act
    └─ Bounded bare-action completion
    ↓
Contextual Refinement Stage
    ├─ Local ellipsis target
    ├─ Typed reference
    ├─ Discourse relation
    └─ Reported-command detection
    ↓
Task Graph
    ↓
External Action Guard
```

推測できないSense、Target、Referenceは`AMBIGUOUS`または`INSUFFICIENT`として残し、External Actionを許可しません。

### 実行

```bash
python scripts/semantic_quality_contract.py \
  --check \
  --output reports/semantic-quality.json

python scripts/semantic_holdout_contract.py \
  --check \
  --output reports/semantic-holdout.json
```

CIとRelease Readinessは両方を実行します。Release Readinessでは公式JMdictからBuildした12万語Snapshotを含むOffline WheelをInstallし、Repositoryの`src`を一時的に退避した状態で契約を再実行します。

---

## English

### Purpose

This contract measures the deterministic semantic capabilities explicitly supported by the current implementation. It does not claim human-level understanding of arbitrary Japanese.

### Covered capabilities

- context-sensitive sense selection for high-impact polysemous expressions;
- sense candidates, evidence, and confidence in the Meaning Graph;
- local omitted-target and zero-object recovery;
- ordered and typed reference resolution;
- pragmatic speech acts such as requests, commitments, refusals, deferrals, concerns, approvals, and rejections;
- separation of polite requests from capability questions;
- causal, contrastive, elaborative, evidential, sequential, alternative, and purpose discourse relations;
- fail-closed external-action handling for quotations, questions, commitments, desires, refusals, ambiguous senses, and unresolved targets.

### Two independent contracts

1. **Supported Profile Contract** — 167 cases tied to the public supported profiles.
2. **Independent Holdout Contract** — 130 cases that are not loaded by the runtime and use different wording, inflection, context, and adversarial action cases.

### Passing requirements

- macro accuracy: at least 95%;
- every category: at least 90%;
- external-action safety: exactly 100%;
- Python 3.10 and 3.12;
- the same contracts against the offline release wheel with the generated 120k lexical snapshot.

### Current verified result

- supported profile: **167 / 167**;
- independent holdout: **130 / 130**;
- combined: **297 / 297**;
- external-action safety: **20 / 20** on the independent holdout.

These results are limited to the documented supported capability set. Unsupported senses, unrestricted commonsense inference, sarcasm, arbitrary long-document discourse, and unregistered regional or generational slang remain outside the claim.
