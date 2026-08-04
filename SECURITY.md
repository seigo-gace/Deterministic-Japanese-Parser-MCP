# Security Policy / セキュリティポリシー

## 日本語

### 対象Version

Security修正は、原則として`main`と最新Release Snapshotを対象にします。過去Versionについては、影響範囲と修正可能性を個別に判断します。

### 脆弱性の報告

脆弱性の再現手順、Exploit、秘密情報をPublic Issueへ掲載しないでください。

1. Repositoryの`Security`タブに`Report a vulnerability`が表示される場合は、Private Vulnerability Reportを使用してください。
2. Private報告機能が表示されない場合は、詳細を書かずに`[Security contact request]`という件名でIssueを作成し、非公開連絡方法の案内を依頼してください。

報告には、可能な範囲で次を含めてください。

- 対象VersionまたはCommit SHA
- 影響するComponent
- 想定されるImpact
- 最小限の再現条件
- 修正案または回避策

### 対応方針

報告内容を確認し、影響範囲、再現性、修正方法を検証します。公開が必要な場合は、修正版を利用可能にしてから技術情報を公開します。対応期限の固定保証は行いませんが、実害を防ぐためのFail Closedと再現可能なEvidenceを優先します。

## English

### Supported versions

Security fixes primarily target `main` and the latest release snapshot. Older versions are evaluated individually based on impact and feasibility.

### Reporting a vulnerability

Do not publish exploit details, secrets, or full reproduction steps in a public issue.

1. Use GitHub's private `Report a vulnerability` flow under the repository's `Security` tab when available.
2. If private reporting is not available, open a minimal issue titled `[Security contact request]` without sensitive details and request a private reporting channel.

Please include, when possible:

- affected version or commit SHA;
- affected component;
- expected impact;
- minimal reproduction conditions;
- a possible fix or mitigation.

### Handling

Reports are validated for impact, reproducibility, and remediation. Technical details are published only after a fix is available when disclosure is necessary. No fixed response-time guarantee is provided; fail-closed behavior and reproducible evidence take priority.