# Governance / ガバナンス

Version 1.0 — 2026-08-05

## 1. Governance Model / 統治モデル

Deterministic Japanese Parser MCP is an **owner-maintained open-source project**. Source code is publicly available under the applicable licenses, while the official repository, official releases, roadmap, Project Marks, and final project decisions remain under the control of the Project Owner.

Deterministic Japanese Parser MCPは、**Owner-maintained型のOpen Source Project**です。Source Codeは適用Licenseに従って公開されますが、公式Repository、公式Release、Roadmap、Project MarksおよびProjectの最終決定はProject Ownerが管理します。

This is not a member-voting foundation, cooperative, or consensus-governed project. Discussion is welcome and may materially influence decisions, but community participation does not create a voting right, ownership interest, agency relationship, partnership, employment relationship, or entitlement to merge, release, or maintainership authority.

本Projectは、会員投票型Foundation、Cooperative、Consensus統治型Projectではありません。議論は歓迎され、意思決定へ大きく影響する場合がありますが、参加によって投票権、所有持分、代理権、Partnership、雇用関係、Merge権、Release権、Maintainer権が発生することはありません。

## 2. Project Owner / プロジェクト所有者

The Project Owner is:

- the copyright holder identified in [`LICENSE`](LICENSE);
- the controller of the official repository `seigo-gace/Deterministic-Japanese-Parser-MCP`;
- currently represented publicly by GitHub account [`@seigo-gace`](https://github.com/seigo-gace).

Project Ownerは次の者です。

- [`LICENSE`](LICENSE)に記載されたCopyright Holder。
- 公式Repository `seigo-gace/Deterministic-Japanese-Parser-MCP`の管理者。
- 現在、GitHub Account [`@seigo-gace`](https://github.com/seigo-gace)で公示されている者。

The Project Owner retains final authority over:

- official project scope, architecture, and design principles;
- roadmap and prioritization;
- acceptance, rejection, modification, or reversion of contributions;
- official branches, tags, versions, releases, packages, and distribution channels;
- security policy, supported environments, compatibility promises, and deprecation;
- dictionary provenance, review thresholds, Gold Corpus, semantic contracts, and performance gates;
- appointment, delegation, suspension, and removal of maintainers or reviewers;
- Project Marks, branding, official status, and trademark permissions;
- contribution agreement requirements and licensing decisions;
- any commercial, hosted, enterprise, certification, support, or Astera integration offering.

Project Ownerは、次について最終決定権を保持します。

- 公式Project Scope、Architecture、Design Principle。
- RoadmapとPriority。
- Contributionの採択、拒否、修正、Revert。
- 公式Branch、Tag、Version、Release、Package、配布Channel。
- Security Policy、Support対象環境、互換性保証、Deprecation。
- 辞書Provenance、Review基準、Gold Corpus、Semantic Contract、Performance Gate。
- Maintainer・Reviewerの任命、権限委任、停止、解除。
- Project Marks、Branding、公式性、商標使用許可。
- Contributor Agreement要否とLicensing Decision。
- 商用、Hosted、Enterprise、Certification、Support、Astera Integrationの提供。

## 3. Official Project / 公式Projectの定義

Only the following are official unless the Project Owner designates another location in writing:

- repository: `https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP`;
- branches, tags, releases, packages, artifacts, and documentation published from or expressly linked by that repository;
- accounts, domains, and distribution channels expressly identified by the Project Owner as official.

Project Ownerが書面で別Locationを指定しない限り、公式とされるのは次だけです。

- Repository: `https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP`。
- 当該Repositoryから公開される、または明示的にLinkされたBranch、Tag、Release、Package、Artifact、Documentation。
- Project Ownerが公式と明示したAccount、Domain、配布Channel。

A fork, mirror, package, binary, service, article, integration, or account is not official merely because it uses project code, links to this repository, receives a merged contribution, or is operated by a past contributor or delegated maintainer.

Fork、Mirror、Package、Binary、Service、記事、Integration、Accountは、Project Codeを使用していること、このRepositoryへLinkしていること、ContributionがMergeされたこと、過去のContributorまたは委任Maintainerが運用していることだけでは公式になりません。

## 4. Project Principles / 変更判断の原則

The Project Owner evaluates changes against the following non-negotiable public principles:

1. **Non-AI runtime** — no runtime LLM or external generative AI dependency.
2. **Determinism** — equivalent input, context, version, and configuration must produce equivalent structured results.
3. **Offline operation** — runtime must not require external dictionary downloads or network inference.
4. **Evidence and provenance** — dictionary and language data must retain source, license, review, and collision evidence.
5. **Fail-closed external action** — unresolved scope, quotation, social meaning, contradiction, timeout, or action risk must not be promoted into unsafe execution.
6. **Meaning Graph authority** — structured semantics remain the source of truth; compatibility views must not silently replace it.
7. **Accuracy and performance together** — speed improvements may not remove semantic distinctions or safety checks; accuracy improvements may not ignore declared latency contracts.
8. **Release readiness** — official releases must pass the project’s required validation, offline installation, provenance, reproducibility, and performance gates.

Project Ownerは、次の公開原則に基づいて変更を判断します。

1. **非AI Runtime** — RuntimeでLLMまたは外部生成AIへ依存しない。
2. **決定論** — 同等のInput、Context、Version、Configurationから同等の構造結果を得る。
3. **Offline動作** — Runtimeで外部辞書DownloadやNetwork推論を要求しない。
4. **EvidenceとProvenance** — 辞書・言語DataのSource、License、Review、Collision Evidenceを保持する。
5. **External ActionのFail Closed** — Scope、引用、社会的意味、矛盾、Timeout、Action Riskが未解決なら危険な実行へ昇格しない。
6. **Meaning Graph正本** — 構造意味を正本とし、互換Viewが黙って置き換えない。
7. **AccuracyとPerformanceの両立** — 高速化のために意味区別やSafety Checkを削除せず、精度向上のためにLatency Contractを無視しない。
8. **Release Readiness** — 公式Releaseは必須Validation、Offline Install、Provenance、Reproducibility、Performance Gateを通過する。

No contributor, maintainer, sponsor, user, or commercial customer may override these principles without the Project Owner’s express decision.

Contributor、Maintainer、Sponsor、User、Commercial Customerは、Project Ownerの明示的な決定なく、これらの原則を変更できません。

## 5. Roles / 役割

### Project Owner

Holds all final decision rights described in this document.

本Documentに定めるすべての最終決定権を保持します。

### Maintainer

A person granted limited repository or review authority by the Project Owner. Delegation:

- is limited to the expressly assigned scope;
- does not transfer ownership, Project Marks, release authority, or roadmap authority unless expressly stated;
- may be changed or revoked by the Project Owner at any time;
- does not survive removal of repository permission unless the Project Owner expressly confirms otherwise.

Project Ownerから限定的なRepository・Review権限を委任された者です。委任は次の条件に従います。

- 明示されたScopeに限定される。
- 明示がない限り、Ownership、Project Marks、Release Authority、Roadmap Authorityを移転しない。
- Project Ownerがいつでも変更・解除できる。
- Repository Permissionの解除後は、Project Ownerが別途明示しない限り存続しない。

### Reviewer

May analyze and recommend changes but cannot merge, release, grant trademark permission, accept a CLA, or alter governance unless separately authorized.

変更を分析・推奨できますが、別途権限を与えられない限り、Merge、Release、商標使用許可、CLA受領、Governance変更はできません。

### Contributor

Submits issues, documentation, code, data, tests, or other material under [`CONTRIBUTING.md`](CONTRIBUTING.md). Contribution does not create authority over the project.

[`CONTRIBUTING.md`](CONTRIBUTING.md)に従ってIssue、Documentation、Code、Data、Testその他を提出する者です。ContributionによってProjectへの権限は発生しません。

## 6. Decision Process / 意思決定手順

The normal process is:

1. issue, proposal, or pull request;
2. public technical, semantic, legal, provenance, safety, and performance review as applicable;
3. requested changes or rejection when required;
4. required DCO or Contributor License Agreement completion;
5. automated and manual validation;
6. final Project Owner decision;
7. merge, close, defer, revert, or release.

通常の手順は次です。

1. Issue、Proposal、Pull Request。
2. 必要に応じたTechnical、Semantic、Legal、Provenance、Safety、Performance Review。
3. 必要な修正要求または拒否。
4. 必須DCOまたはContributor License Agreementの完了。
5. 自動・手動Validation。
6. Project Ownerの最終判断。
7. Merge、Close、Defer、Revert、Release。

The Project Owner may make emergency security, legal, integrity, provenance, or release changes without prior public consensus. A public explanation may be added afterward when disclosure is safe and lawful.

Project Ownerは、Security、Legal、Integrity、Provenance、Release上の緊急変更を事前の公開Consensusなく実施できます。安全かつ適法に公開できる場合は、後から説明を追加できます。

## 7. Pull Requests and Acceptance / PR採択

A pull request is a proposal, not an entitlement. The Project Owner may reject or defer a contribution for reasons including architecture, project scope, duplication, maintainability, provenance, license risk, security, performance, user impact, incomplete evidence, strategic direction, or lack of required contributor agreement.

Pull Requestは提案であり、採択請求権ではありません。Project Ownerは、Architecture、Project Scope、重複、保守性、Provenance、License Risk、Security、Performance、User Impact、Evidence不足、戦略、Contributor Agreement未完了等を理由に拒否・保留できます。

A merged contribution does not guarantee continued inclusion. Code, data, documentation, APIs, behaviors, or compatibility may be modified or reverted under the applicable release and compatibility policies.

Merge済みContributionであっても、継続収録を保証しません。Code、Data、Documentation、API、Behavior、Compatibilityは、適用されるRelease・Compatibility Policyに従って変更・Revertされる場合があります。

## 8. Releases / 公式Release

Only the Project Owner, or a maintainer expressly delegated release authority, may publish an official release. An official release requires:

- an official tag or release record;
- source and artifact provenance;
- required notices and licenses;
- required CI, Gold, holdout, offline, reproducibility, and performance evidence;
- Project Owner approval or delegated release approval.

公式Releaseを公開できるのは、Project OwnerまたはRelease権限を明示的に委任されたMaintainerだけです。公式Releaseには次が必要です。

- 公式TagまたはRelease Record。
- Source・Artifact Provenance。
- 必須Notice・License。
- 必須CI、Gold、Holdout、Offline、Reproducibility、Performance Evidence。
- Project Ownerまたは委任Release Authorityによる承認。

## 9. Licensing and Contributions / License・Contribution

Program code remains under the license stated in [`LICENSE`](LICENSE). Third-party data remains under its recorded source license. Project Marks remain governed separately by [`TRADEMARK.md`](TRADEMARK.md).

Program Codeには[`LICENSE`](LICENSE)記載のLicenseが適用されます。第三者Dataには記録されたSource Licenseが適用されます。Project Marksには別途[`TRADEMARK.md`](TRADEMARK.md)が適用されます。

All contributions require provenance certification under [`DEVELOPER_CERTIFICATE_OF_ORIGIN.md`](DEVELOPER_CERTIFICATE_OF_ORIGIN.md). Substantive contributions require the Project Owner’s accepted Contributor License Agreement under [`CONTRIBUTOR_LICENSE_AGREEMENT.md`](CONTRIBUTOR_LICENSE_AGREEMENT.md), unless the Project Owner expressly waives it in writing for the specific contribution.

すべてのContributionには[`DEVELOPER_CERTIFICATE_OF_ORIGIN.md`](DEVELOPER_CERTIFICATE_OF_ORIGIN.md)に基づくProvenance Certificationが必要です。実質的Contributionには、個別ContributionについてProject Ownerが書面で免除しない限り、[`CONTRIBUTOR_LICENSE_AGREEMENT.md`](CONTRIBUTOR_LICENSE_AGREEMENT.md)に基づきProject Ownerが受領したContributor License Agreementが必要です。

The Project Owner may change the outbound license for future versions or offer the project under additional licenses only to the extent the Project Owner holds or has received sufficient rights. Existing recipients retain rights already granted under the license version they received.

Project Ownerは、保有または取得済みの権利範囲内で、将来VersionのOutbound Licenseを変更し、またはAdditional Licenseを提供できます。既存受領者が既に取得したLicense上の権利は維持されます。

## 10. Project Marks and Commercial Offerings / Brand・商用提供

Contribution, sponsorship, integration, or use of project code does not grant rights to Project Marks, official status, certification, hosted services, enterprise support, commercial distribution, or Astera branding.

Contribution、Sponsorship、Integration、Project Code利用は、Project Marks、公式Status、Certification、Hosted Service、Enterprise Support、Commercial Distribution、Astera Brandingの権利を与えません。

Separate written terms may govern trademark licenses, commercial licenses, hosted services, support, certification, or integrations. Those terms do not change the rights already granted under the repository’s open-source licenses unless they expressly say so and applicable law permits it.

Trademark License、Commercial License、Hosted Service、Support、Certification、Integrationには別の書面条件が適用される場合があります。その条件は、明示され、かつ法令上許される場合を除き、RepositoryのOpen-source Licenseで既に与えられた権利を変更しません。

## 11. Forks / Forkの独立性

The MIT License permits forks and derivative works. Fork operators control their own repositories and code changes, but they do not control this official project, its roadmap, releases, or Project Marks. Modified forks must comply with [`TRADEMARK.md`](TRADEMARK.md).

MIT LicenseはFork・Derivative Workを許可します。Fork運営者は自らのRepositoryとCode変更を管理できますが、本公式Project、Roadmap、Release、Project Marksは管理できません。改変Forkは[`TRADEMARK.md`](TRADEMARK.md)に従う必要があります。

## 12. Succession and Continuity / 承継

Only the Project Owner may designate a successor Project Owner. A designation must be made through a verifiable official repository record, signed release record, or other written instrument controlled by the Project Owner.

後継Project Ownerを指定できるのはProject Ownerだけです。指定は、検証可能な公式Repository Record、署名済みRelease Record、またはProject Ownerが管理する別の書面によって行います。

Repository inactivity, delayed responses, a fork becoming more popular, or a former maintainer continuing development does not transfer official status or Project Marks.

Repositoryの活動停止、返答の遅れ、ForkのPopularity上昇、元Maintainerによる継続開発は、公式StatusまたはProject Marksを移転しません。

## 13. Governance Changes / Governance変更

The Project Owner may amend this governance document. Material changes should be recorded in repository history and should not retroactively revoke rights already granted under an open-source license or an executed agreement.

Project Ownerは本Governance Documentを変更できます。重要変更はRepository Historyへ記録し、Open-source Licenseまたは締結済みAgreementで既に付与された権利を遡及的に剥奪しません。

## 14. Interpretation / 解釈

If a conflict exists between this document and an executed written agreement, the executed agreement controls for its subject matter. If a conflict exists between this document and the MIT License regarding use of Program Code, the MIT License controls. This governance document controls only project decision-making and official-project administration; it does not reduce rights granted by an open-source license.

本Documentと締結済み書面Agreementが矛盾する場合、その対象事項について締結済みAgreementが優先します。本DocumentとMIT LicenseがProgram Code利用について矛盾する場合、MIT Licenseが優先します。本Governance DocumentはProjectの意思決定と公式Project管理を定めるものであり、Open-source Licenseで付与された権利を減らしません。
