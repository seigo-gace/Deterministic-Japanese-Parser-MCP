# Support / サポート

## 日本語

### 公開検証・質問・改善案

第三者検証、判断に迷う解析結果、日本語表現の確認、Install・MCP設定・Python APIの質問、候補DataのEvidence確認、改善アイデアは、GitHub Discussionsを使用してください。

検証参加方法と、Discussion・Issue・Pull Requestの使い分けは[`VALIDATION.md`](VALIDATION.md)に記載しています。

Discussionsで受け付ける主な内容：

- 5分で行える日本語解釈の確認
- External Action Guardの安全性検証
- Windows、macOS、Linux、各MCP Clientの導入検証
- Offline Packageと性能契約の再確認
- 方言、俗語、比喩、慣用句、語用表現の判断
- Context v3 5,000件候補のSource、意味、Reading、Variant、地域・世代・Community、License確認
- 利用方法の質問
- 初期段階の改善案・設計検討

Discussionの投稿は、自動的に不具合、採用仕様、Runtime辞書Entry、実装Taskになるものではありません。Maintainerが再現・分類し、修正が必要な具体的不具合と確認した場合だけBug Issueへ移します。

### Issues

GitHub Issuesは、**確認済みで再現可能な不具合・回帰の修正追跡専用**です。

`Confirmed bug or regression` Formを使用し、VersionまたはCommit SHA、最小再現入力・Command、期待結果、実際の結果、再現手順、実行環境、秘密情報を除外したEvidenceを記載してください。

以下はIssueへ投稿しません。

- 質問
- 未再現の違和感・推測
- 検証参加報告
- 初期アイデア
- 採用条件が固まっていない改善案
- 個別Candidateの単なる確認依頼

これらはDiscussionsを使用してください。

### Security

脆弱性はPublic IssueまたはDiscussionへ詳細を書かず、[`SECURITY.md`](SECURITY.md)の手順を使用してください。

### 対象範囲

このRepositoryで扱うPublic Support・Validation範囲は次です。

- Deterministic Japanese Parser MCPのInstallと起動
- `analyze_japanese` ToolとPython API
- Meaning Graph、Task Graph、External Action Guard
- Rule、Metaphor、Synonym、Workflow、Gold Corpus
- Open Dictionary Supply Chain
- Open LexiconとContext Candidate Data
- Accuracy、Regression、Offline、Performance検証
- Public Documentation

Astera本体、Cloudflare、Square、非公開Server、非公開Workspace、利用者固有の秘密情報は、このPublic RepositoryのIssue・Discussion対象ではありません。

## English

### Public validation, questions, and ideas

Use GitHub Discussions for independent validation, suspicious or uncertain results, Japanese-language review, installation and MCP configuration questions, candidate evidence review, and early improvement ideas.

See [`VALIDATION.md`](VALIDATION.md) for participation tracks and the boundary between Discussions, Issues, and Pull Requests.

Discussions cover:

- five-minute Japanese interpretation checks;
- External Action Guard safety validation;
- Windows, macOS, Linux, and MCP client compatibility;
- offline package and performance contract checks;
- dialect, slang, metaphor, idiom, and pragmatic-expression review;
- source, meaning, reading, variant, region, generation, community, and license review for the 5,000 Context v3 candidates;
- usage questions;
- early ideas and design discussion.

A Discussion post does not automatically become a bug, accepted specification, runtime dictionary entry, or implementation task. Maintainers reproduce and classify findings before converting a confirmed defect into a Bug Issue.

### Issues

GitHub Issues are reserved for **confirmed, reproducible bugs and regressions that require a fix**.

Use the `Confirmed bug or regression` form and include the version or commit SHA, smallest reproducing input or command, expected result, actual result, reproduction steps, environment, and sanitized evidence.

Do not open Issues for questions, unverified suspicions, validation participation, early ideas, proposals without fixed acceptance criteria, or individual candidate review requests. Use Discussions instead.

### Security

Do not disclose vulnerability details in a public Issue or Discussion. Follow [`SECURITY.md`](SECURITY.md).

### Scope

Public support and validation cover this repository's parser, MCP tool, dictionaries, Meaning Graph, Task Graph, action guard, supply chain, open lexicon, context candidate data, validation contracts, packaging, and public documentation.

Private Astera infrastructure, Cloudflare, Square, private servers, private workspaces, and user-specific credentials are outside this repository's public support scope.
