# Contributing / Contribution Guide

Deterministic Japanese Parser MCPへのContributionを歓迎します。対象はParser Rule、Meaning Graph、Metaphor・Idiom、Synonym、Workflow、Gold Corpus、Open Dictionary Supply Chain、MCP Integration、Packaging、Documentation、Performanceです。

Contributions are welcome for parser rules, Meaning Graph behavior, metaphors and idioms, synonyms, workflows, Gold Corpus cases, the open dictionary supply chain, MCP integration, packaging, documentation, and performance.

Participation is governed by [`GOVERNANCE.md`](GOVERNANCE.md). A pull request is a proposal and does not create a right to merge, maintainership, official status, release authority, or use of Project Marks. Brand use is governed separately by [`TRADEMARK.md`](TRADEMARK.md).

参加には[`GOVERNANCE.md`](GOVERNANCE.md)が適用されます。Pull Requestは提案であり、Merge請求権、Maintainer権、公式Status、Release権、Project Marks使用権を発生させません。Brand利用には別途[`TRADEMARK.md`](TRADEMARK.md)が適用されます。

## Contribution rights / Contributionの権利処理

### 1. DCO is required for every commit / 全CommitでDCO必須

Every commit submitted for inclusion must include a valid `Signed-off-by` line under [`DEVELOPER_CERTIFICATE_OF_ORIGIN.md`](DEVELOPER_CERTIFICATE_OF_ORIGIN.md).

収録を目的として提出するすべてのCommitには、[`DEVELOPER_CERTIFICATE_OF_ORIGIN.md`](DEVELOPER_CERTIFICATE_OF_ORIGIN.md)に基づく有効な`Signed-off-by` Lineが必要です。

```bash
git commit -s
```

The sign-off must identify the person certifying provenance. It must not use an obviously false identity or a bot identity that cannot make the certification.

Sign-offにはProvenanceを証明する本人を記載してください。明らかな虚偽Identityまたは証明能力のないBot Identityは使用できません。

### 2. Substantive contributions require an accepted CLA / 実質的ContributionはCLA必須

A signed and Project-Owner-accepted [`CONTRIBUTOR_LICENSE_AGREEMENT.md`](CONTRIBUTOR_LICENSE_AGREEMENT.md) is required before merge for any substantive contribution, including:

- runtime code, parser logic, grammar, tokenization, normalization, Meaning Graph, Task Graph, guard, security, or API behavior;
- dictionary entries, language-feature data, metaphor or pragmatic data, synonym groups, workflows, Gold Corpus, evaluation sets, or source-data transformation logic;
- build, packaging, release, CI, provenance, license, reproducibility, or performance-gate logic;
- architecture, specification, governance, trademark, licensing, security, or other documentation containing original project design or policy;
- a series of nominally small changes that together form a substantive contribution;
- any contribution the Project Owner identifies as requiring additional rights for maintenance, relicensing, commercial distribution, or Astera integration.

次の実質的Contributionは、Merge前に署名済みかつProject Owner受領済みの[`CONTRIBUTOR_LICENSE_AGREEMENT.md`](CONTRIBUTOR_LICENSE_AGREEMENT.md)が必要です。

- Runtime Code、Parser Logic、Grammar、Tokenization、Normalization、Meaning Graph、Task Graph、Guard、Security、API Behavior。
- Dictionary Entry、Language Feature Data、Metaphor・Pragmatic Data、Synonym Group、Workflow、Gold Corpus、Evaluation Set、Source Data Transformation Logic。
- Build、Packaging、Release、CI、Provenance、License、Reproducibility、Performance Gate Logic。
- OriginalなProject Design・Policyを含むArchitecture、Specification、Governance、Trademark、Licensing、Securityその他のDocumentation。
- 個別には小規模でも、合計すると実質的Contributionになる一連の変更。
- Maintenance、Relicensing、Commercial Distribution、Astera Integrationに追加権利が必要であるとProject Ownerが判断したContribution。

A contributor retains copyright under the CLA. The CLA grants the Project Owner broad non-exclusive copyright and patent permissions, including sublicensing and relicensing. It is not a copyright assignment. A separate written assignment is required if exclusive ownership is needed for a particular contribution.

ContributorはCLAの下でもCopyrightを保持します。CLAはProject Ownerへ、Sublicensing・Relicensingを含む広い非独占Copyright・Patent Permissionを付与します。CLAはCopyright Assignmentではありません。特定ContributionについてExclusive Ownershipが必要な場合、別の書面Assignmentが必要です。

### 3. CLA exemption / CLA免除

The Project Owner may exempt a contribution from the CLA only when it is clearly non-substantive, such as:

- correction of an obvious typo with no change in meaning;
- whitespace, formatting, or broken-link repair with no original policy, design, or technical content;
- removal of accidentally duplicated text;
- a bug report or feature request containing no submitted code, original dataset, or protectable project material.

Project Ownerは、次のように明確に非実質的なContributionに限り、CLAを免除できます。

- 意味を変更しない明白なTypo修正。
- OriginalなPolicy、Design、Technical Contentを含まないWhitespace、Formatting、Broken Link修正。
- 誤って重複したTextの削除。
- 提出Code、Original Dataset、保護対象となるProject Materialを含まないBug Report・Feature Request。

The Project Owner decides the classification. File count, line count, commit count, or contributor intent alone does not determine whether a contribution is substantive. An exemption must be recorded in writing on the pull request; silence is not an exemption.

分類の最終判断はProject Ownerが行います。File数、Line数、Commit数、Contributorの意図だけでは実質性を決定しません。免除はPull Requestへ書面で記録する必要があり、無回答は免除を意味しません。

### 4. CLA submission and records / CLA提出・記録

Do not upload a handwritten signature, home address, government identifier, or other sensitive personal information to a public pull request.

手書き署名、自宅住所、公的Identifierその他の秘密性の高い個人情報を公開Pull Requestへ掲載してはなりません。

For a CLA-required pull request:

1. open the pull request with all provenance and license information;
2. the Project Owner confirms that the CLA is required and identifies the applicable Agreement version;
3. the Project Owner provides a private submission method;
4. the contributor submits the complete signed agreement privately;
5. the Project Owner records only the GitHub username, Agreement version, acceptance date, and a private-record identifier or digest on the pull request;
6. merge remains blocked until acceptance is recorded.

CLA必須Pull Requestでは次の手順を使用します。

1. Provenance・License情報を揃えてPull Requestを作成する。
2. Project OwnerがCLA要否と適用Agreement Versionを確認する。
3. Project OwnerがPrivate Submission Methodを指定する。
4. Contributorが完全な署名済みAgreementをPrivateに提出する。
5. Project OwnerがGitHub Username、Agreement Version、Acceptance Date、Private Record IdentifierまたはDigestだけをPull Requestへ記録する。
6. Acceptanceが記録されるまでMergeしない。

A typed checkbox or ordinary pull-request comment is not treated as a signed CLA unless the Project Owner has adopted a legally reviewed electronic-signature process for that exact Agreement version.

Project Ownerが当該Agreement VersionについてLegal Review済みのElectronic Signature Processを導入していない限り、Checkboxまたは通常のPull Request Commentだけでは署名済みCLAとして扱いません。

### 5. Third-party and generated material / 第三者・生成Material

DCO and CLA completion do not cure a third-party license violation. Contributors must still disclose and comply with every applicable source license, attribution, database right, corpus restriction, privacy obligation, and generated-material policy.

DCO・CLAを完了しても、第三者License違反は解消されません。Contributorは、適用されるSource License、Attribution、Database Right、Corpus Restriction、Privacy Obligation、Generated Material Policyをすべて開示・遵守する必要があります。

The Project Owner may reject material whose rights cannot be verified, even if the contributor signed the DCO and CLA.

ContributorがDCO・CLAへ署名していても、権利を検証できないMaterialはProject Ownerが拒否できます。

## 日本語

### Public Repositoryとしての前提

Contributionは、第三者がSource、意図、Test、License、限界を確認できる状態にしてください。

- 秘密情報、認証情報、個人情報、非公開Notion URL、Local absolute pathを含めない。
- Proprietary辞書定義や第三者Corpus文を転載しない。
- RuntimeでLLMまたは外部AIを呼び出す変更にしない。
- 未確定の意味を推測で埋めない。
- Generated Proposalを無審査で`dictionaries/system/`へ入れない。
- 関係のない変更を同じPull Requestへ混ぜない。
- 公式名称、Logo、Package、Account、Domainを変更・追加する場合は`TRADEMARK.md`との整合を説明する。
- Project Ownerの最終判断、Release Authority、Brand Authorityを回避する変更を行わない。

### Dictionary変更の必須Evidence

System Dictionary Entryには次が必要です。

- 正確な日本語表現またはPattern
- 決定論的な意味・Intent・語用機能
- 使用ContextとDomain制約
- 同じ意味・同じ制約であるAliasだけを採用した根拠
- Source、Version、License、Attribution
- 肯定例、否定例、曖昧例、衝突例
- 最低1件のGold Corpus Case
- External Actionへ影響する場合のFail Closed Case

同形異義、多義、読み違い、包含語は一つの意味へ潰さず、候補とEvidenceを保持してください。

### Code・Grammar変更

Pull Requestには次を説明してください。

1. 未対応または誤っていた入力
2. 変更する決定論的RuleまたはGraph構造
3. Meaning Graph / Task Graphの期待結果
4. Quote、Question、Negation、Scope、Reference、Collisionへの影響
5. 追加したRegression Test
6. Compatibility、Security、Performanceへの影響

### 検証

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python tools/lexicon_validator.py
python tools/validator.py
pytest
python scripts/test_harness.py
python scripts/benchmark.py --check
python scripts/performance_contract.py --check --max-ready-ms 10
python scripts/astera_latency_contract.py --check --target-ms 10 --hard-ms 50
python -m compileall -q src tools scripts tests
```

Windows PowerShellではVirtual Environmentの有効化に次を使用します。

```powershell
.\.venv\Scripts\Activate.ps1
```

すべて成功したHead SHAをPull Requestへ記載してください。Open Lexicon、Packaging、Release関連の変更はGitHub Actionsの`Release Readiness`も必須です。

### Directory

- `src/deterministic_japanese_parser_mcp/`: Runtime Code
- `dictionaries/system/`: Review済みProject Default
- `dictionaries/user/`: Local Override。Public Defaultは空
- `dictionaries/system/lexicon.d/`: License別Open Lexicon Pack
- `tests/gold/`: Gold Corpus
- `tests/`: Unit、Regression、Supply Chain、MCP、Public Contract
- `tools/`: Dictionary Supply ChainとValidator
- `scripts/`: Benchmark、Performance、Astera Contract
- `docs/`: Public ArchitectureとAccuracy Contract
- `proposals/`: 未採用Candidate。System Dictionaryではない

### Pull Request

`.github/pull_request_template.md`を埋め、利用者影響、Test、Evidence、License、既知の限界、DCO、CLA Statusを記録してください。Publicな挙動が変わる場合は`README.md`、`docs/`、`CHANGELOG.md`も更新してください。

## English

### Public repository requirements

A contribution must be reviewable by a third party from public source, tests, provenance, and documentation.

- Do not include secrets, credentials, personal data, private Notion URLs, or local absolute paths.
- Do not copy proprietary dictionary definitions or third-party corpus sentences.
- Do not add runtime LLM or external AI calls.
- Do not invent unresolved meaning.
- Do not auto-promote generated proposals into `dictionaries/system/`.
- Keep unrelated changes out of the same pull request.
- Explain compliance with `TRADEMARK.md` for changes to official names, logos, packages, accounts, or domains.
- Do not bypass the Project Owner’s final decision, release authority, or brand authority.

### Dictionary evidence

A system dictionary change must include the exact expression or pattern, deterministic interpretation, context constraints, source and license evidence, positive and negative cases, ambiguity and collision cases, at least one Gold Corpus case, and fail-closed coverage when external action behavior is affected.

Homographs, polysemy, reading differences, and containment relations must preserve candidate distinctions rather than collapsing them into one meaning.

### Code and grammar changes

Explain the unsupported or incorrect input, deterministic behavior change, expected Meaning Graph and Task Graph, scope and quotation impact, added regression cases, and compatibility, security, and performance impact.

Run the complete validation command set shown above and record the tested head SHA. Changes affecting the open lexicon, packaging, or releases must also pass GitHub Actions `Release Readiness`.

Use the pull request template and update public documentation and `CHANGELOG.md` whenever user-visible behavior changes. Record DCO and CLA status before requesting merge.
