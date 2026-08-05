# Repository Control Settings / Repository強制設定

Version 1.0 — 2026-08-05

This document records the GitHub repository settings required to make [`GOVERNANCE.md`](../GOVERNANCE.md), [`CODEOWNERS`](../.github/CODEOWNERS), and the contribution-rights workflows enforceable at the platform level.

本Documentは、[`GOVERNANCE.md`](../GOVERNANCE.md)、[`CODEOWNERS`](../.github/CODEOWNERS)、Contribution Rights WorkflowをGitHub Platform上で強制するために必要なRepository Settingsを正本化します。

## 1. Scope / 対象

- Repository: `seigo-gace/Deterministic-Japanese-Parser-MCP`
- Protected branch: `main`
- Project Owner and bypass authority: `@seigo-gace`
- Enforcement target: every direct push, pull request, merge, force push, deletion, and release-related change affecting `main`

## 2. Repository ruleset / 必須Ruleset

Create an active branch ruleset with the following values.

次の内容でActiveなBranch Rulesetを作成します。

### Identity

- Ruleset name: `Official main control`
- Enforcement status: `Active`
- Target: `Branch`
- Included branch: `refs/heads/main`
- Excluded branches: none

### Bypass

- Add only the Project Owner or repository administrator role controlled exclusively by `@seigo-gace`.
- Bypass mode: `Always` or `Pull requests only`, chosen so the sole Project Owner can recover the repository and merge owner-authored PRs without requiring self-approval.
- Do not grant bypass to contributors, bots, external maintainers, sponsors, or broad write/maintain roles.
- A GitHub App may be added only when its exact purpose, permissions, and revocation procedure are recorded in this document and approved by the Project Owner.

Bypassには、`@seigo-gace`が単独管理するProject OwnerまたはRepository Administrator Roleだけを登録します。Contributor、Bot、External Maintainer、Sponsor、広範なWrite/Maintain Roleには付与しません。

### Required rules

Enable:

- **Restrict deletions**
- **Block force pushes**
- **Require a pull request before merging**
- **Require status checks to pass before merging**
- **Require conversation resolution before merging**
- **Require linear history**

推奨Status Check:

- `CI`の必須Job
- `Release Readiness`の必須Job（Package、辞書、Release、Runtime、Performanceへ影響する変更）
- `README governance consistency`
- `DCO and owner rights review`（外部ContributorのPR）

Status Check名はGitHub Actionsが実際に生成した最新のCheck名を選択し、Workflow Display Nameだけを推測で登録しません。

### Pull-request review rules

For pull requests authored by anyone other than `@seigo-gace`:

- Require at least one approving review.
- Require review from Code Owners.
- Dismiss stale approvals when new commits are pushed.
- Require approval of the most recent reviewable push when available.
- Prevent merge while a change-request review remains unresolved.

`@seigo-gace`自身のPull Requestは、GitHub上で自己承認できないため、Project OwnerのBypassを使用します。ただし、CI、Release Readiness、Documentation Integrityその他のStatus Checkを原則として通過させ、緊急Bypassを通常運用にしません。

### Optional but recommended

- Require signed commits after a signing method is configured and tested for all official release paths.
- Restrict branch creation or matching release tags if a separate release ruleset is introduced.
- Require code scanning or dependency review only after those checks are stable and do not create an unverifiable release path.

## 3. CODEOWNERS / Code Owner

The official file is [`.github/CODEOWNERS`](../.github/CODEOWNERS).

Required invariants:

- `* @seigo-gace` remains the fallback owner.
- `.github/CODEOWNERS` itself is owned by `@seigo-gace`.
- Legal, governance, trademark, security, release, runtime, dictionaries, Gold data, tests, tools, and packaging remain assigned to `@seigo-gace` unless [`GOVERNANCE.md`](../GOVERNANCE.md) records an explicit delegation.
- A pull request may not remove or weaken the fallback owner without Project Owner approval.

CODEOWNERSはReview Requestを自動化しますが、RulesetまたはBranch Protectionで`Require review from Code Owners`を有効にしない限り、Approvalを必須化しません。

## 4. Contribution rights check / Contribution権利Gate

The workflow [`.github/workflows/contribution-rights.yml`](../.github/workflows/contribution-rights.yml) must remain a required check for external pull requests.

It enforces:

- DCO `Signed-off-by` on every external commit;
- Project Owner review bound to the exact current PR head;
- either an accepted CLA record or a written CLA exemption;
- no checkout or execution of untrusted fork code in the privileged `pull_request_target` job;
- read-only repository and pull-request permissions.

The workflow checks out only the trusted default branch policy script. It must never change to checking out or executing the external pull-request head under `pull_request_target`.

## 5. Official release control / 公式Release

Repository settings and release operations must preserve:

- only `@seigo-gace` or an explicitly delegated release maintainer may create official releases or tags;
- release artifacts must be produced by approved workflow definitions from the official repository;
- release evidence, hashes, source manifests, licenses, and provenance remain attached or reproducibly available;
- a fork, mirror, third-party package, or separately built binary is not an official release;
- Project Marks and official release branding remain governed by [`TRADEMARK.md`](../TRADEMARK.md).

## 6. Secrets and workflow permissions / Secret・Workflow権限

- Default workflow token permission: read-only unless a specific workflow requires a narrower write action.
- Do not expose secrets to fork pull requests.
- A `pull_request_target` workflow must never execute code from the pull-request head.
- Environment or release secrets must be limited to official protected branches and approved release workflows.
- Remove unused deploy keys, personal access tokens, GitHub Apps, webhooks, and collaborators.
- Record the purpose and owner of every write-capable integration.

## 7. Verification record / 設定確認記録

After applying or changing the ruleset, record:

- ruleset URL or numeric ID;
- activation date;
- exact protected ref;
- bypass actors and bypass mode;
- required status-check names;
- review requirements;
- force-push and deletion settings;
- verification screenshot or exported ruleset JSON digest;
- Project Owner verification date.

Record template:

```text
Ruleset ID:
Ruleset URL:
Enforcement: Active
Protected ref: refs/heads/main
Bypass actor: @seigo-gace / repository administrator
Bypass mode:
Required checks:
Require pull request: yes
Require code owner review: yes
Dismiss stale approvals: yes
Require latest-push approval:
Require conversation resolution: yes
Block force pushes: yes
Restrict deletions: yes
Require linear history: yes
Verified by: @seigo-gace
Verified at:
Export or screenshot digest:
```

## 8. Current implementation boundary / 現在の実装境界

The repository files establish ownership routing, contribution checks, official-project policy, and auditable requirements. GitHub rulesets are repository settings, not version-controlled files. Therefore:

- a committed `CODEOWNERS` file does not by itself make owner approval mandatory;
- a workflow does not by itself prevent an administrator from bypassing checks;
- the Ruleset must be enabled in GitHub settings to enforce the platform controls in this document;
- no document may state that the Ruleset is active until the verification record above is completed from the actual repository settings.

Repository FileはOwnership Routing、Contribution Check、Official Project Policy、監査可能な要件を確立します。GitHub RulesetはVersion管理FileではなくRepository Settingです。そのため、実SettingsのVerification Recordが完成するまでは、RulesetがActiveであると表示してはなりません。
