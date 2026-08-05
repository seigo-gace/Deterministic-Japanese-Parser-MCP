# Community Validation / 公開検証への参加

Deterministic Japanese Parser MCPでは、Code Contributionだけでなく、**第三者による独立検証**を重視します。

You can contribute without writing code. Independent validation of Japanese interpretation, external-action safety, installation, MCP compatibility, performance, and candidate data is valuable.

## Where to participate / 参加場所

Use **GitHub Discussions** for:

- validation campaign participation;
- suspicious or uncertain parser results;
- Japanese interpretation review;
- Windows, macOS, Linux, and MCP client compatibility checks;
- dialect, slang, metaphor, idiom, and pragmatic-expression review;
- source, license, reading, variant, and usage evidence for candidate data;
- questions and early ideas.

Use **GitHub Issues only for confirmed, reproducible bugs or regressions that require a fix**.

```text
Discussion validation result
        ↓ maintainer reproduction and classification
Confirmed reproducible defect
        ↓
Bug Issue
        ↓
Pull Request + CI + evidence
        ↓
Original validator re-check
```

A Discussion result does not automatically become a bug, accepted specification, runtime dictionary entry, or implementation task.

## Participation tracks / 参加コース

### 1. Five-minute language review / 5分日本語確認

No installation is required. Review an input and its output, then report:

- correct;
- partly suspicious;
- incorrect;
- unable to judge;
- your own interpretation.

### 2. Fifteen-minute execution validation / 15分実行検証

Run a specified validation pack or command and report the generated result with:

- pack or campaign ID;
- version or commit SHA;
- operating system and Python version;
- MCP client when applicable;
- pass, suspicious, or failure result;
- sanitized logs.

### 3. Specialist review / 専門検証

Specialist reviews may cover:

- quotations, questions, negation, hypothesis, hearsay, correction, and withdrawal;
- External Action Guard behavior;
- homographs, polysemy, containment, and reading restrictions;
- dialect, generation, community, and domain constraints;
- source provenance and license;
- performance and offline packaging.

## Validation categories / Discussionカテゴリ

The repository uses the following category names and slugs.

| Category | Slug | Format | Purpose |
|---|---|---|---|
| Validation Campaigns / 検証募集 | `validation-campaigns` | Announcement | Maintainer-created validation packs and current recruitment |
| Validation Results / 検証結果 | `validation-results` | Open-ended | Results, suspicious behavior, and independent findings |
| Japanese Language Review / 日本語判断 | `japanese-language-review` | Question and answer | Interpretation, naturalness, ambiguity, dialect, slang, and pragmatic judgment |
| Environment Validation / 導入環境検証 | `environment-validation` | Question and answer | Install, MCP client, operating system, packaging, and offline checks |
| Evidence Review / 根拠確認 | `evidence-review` | Open-ended | Candidate data, source, license, reading, variant, region, generation, and usage review |

The YAML forms in `.github/DISCUSSION_TEMPLATE/` correspond exactly to these slugs.

## Candidate data boundary / 候補Dataの境界

The 5,000 Context v3 records are candidate-discovery data. A candidate is not automatically approved.

```text
Candidate exists
≠ meaning is verified
≠ usage is current
≠ license is cleared
≠ runtime promotion is safe
```

Runtime promotion requires source evidence, meaning and context review, license review, positive and negative cases, ambiguity and collision checks, Gold regression, holdout coverage, external-action safety review, and human approval.

Do not create one Issue per candidate. Review candidates in small packs, and create a Bug Issue only when a concrete repository defect is confirmed.

## Submission safety / 投稿時の安全条件

Do not post:

- secrets, credentials, personal data, or private URLs;
- private Astera, Cloudflare, Square, server, or workspace information;
- proprietary dictionary definitions or copied corpus sentences;
- vulnerability details in a public Discussion or Issue;
- unverifiable claims represented as confirmed facts.

Short self-created examples and links to public sources are preferred. Source and license information must be included before external material is incorporated into project data.

## Credit / 検証協力者の記録

Confirmed findings should retain a link to the original Discussion and credit the validator in the related Issue, Pull Request, or release note unless the validator requests otherwise. Validation credit does not transfer project ownership, release authority, maintainership, or trademark rights.
