# Support / サポート

## 日本語

### Bug報告

再現可能な不具合は、GitHub Issueの`Bug report` Templateを使用してください。対象VersionまたはCommit SHA、入力、期待結果、実際の結果、再現手順、実行環境を記載してください。

### 改善提案

新しいRule、辞書表現、Meaning Graph構造、MCP連携、性能改善は`Feature request` Templateを使用してください。人間同等の任意日本語理解ではなく、決定論的に定義・検証できる変更として提案してください。

### 利用方法の質問

Install、MCP設定、Python API、辞書追加、検証Commandに関する質問は`Usage question` Templateを使用してください。秘密情報、個人情報、非公開URL、認証情報をIssueへ掲載しないでください。

### Security

脆弱性はPublic Issueへ詳細を書かず、[`SECURITY.md`](SECURITY.md)の手順を使用してください。

### 対象範囲

このRepositoryで扱うSupport範囲は次です。

- Deterministic Japanese Parser MCPのInstallと起動
- `analyze_japanese` ToolとPython API
- Meaning Graph、Task Graph、External Action Guard
- Rule、Metaphor、Synonym、Workflow、Gold Corpus
- Open Dictionary Supply Chain
- Accuracy、Regression、Offline、Performance検証

Astera本体、Cloudflare、Square、非公開Server、利用者固有の秘密情報は、このPublic RepositoryのIssue対象ではありません。

## English

### Bug reports

Use the `Bug report` issue form for reproducible defects. Include the version or commit SHA, input, expected result, actual result, reproduction steps, and environment.

### Improvement proposals

Use the `Feature request` form for deterministic parser rules, dictionary entries, Meaning Graph structures, MCP integration, or performance improvements. Proposals must be definable and testable rather than relying on an undefined claim of human-level understanding.

### Usage questions

Use the `Usage question` form for installation, MCP configuration, Python API usage, dictionary contribution, and validation commands. Do not include secrets, personal data, private URLs, or credentials.

### Security

Do not disclose vulnerability details in a public issue. Follow [`SECURITY.md`](SECURITY.md).

### Scope

Public support covers this repository's parser, MCP tool, dictionaries, Meaning Graph, Task Graph, action guard, supply chain, and validation contracts. Private Astera infrastructure and user-specific credentials are outside this repository's support scope.