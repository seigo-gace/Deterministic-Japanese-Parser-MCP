# Contributing / Contribution Guide

Deterministic Japanese Parser MCPへのContributionを歓迎します。対象はParser Rule、Meaning Graph、Metaphor・Idiom、Synonym、Workflow、Gold Corpus、Open Dictionary Supply Chain、MCP Integration、Packaging、Documentation、Performanceです。

Contributions are welcome for parser rules, Meaning Graph behavior, metaphors and idioms, synonyms, workflows, Gold Corpus cases, the open dictionary supply chain, MCP integration, packaging, documentation, and performance.

## 日本語

### Public Repositoryとしての前提

Contributionは、第三者がSource、意図、Test、License、限界を確認できる状態にしてください。

- 秘密情報、認証情報、個人情報、非公開Notion URL、Local absolute pathを含めない。
- Proprietary辞書定義や第三者Corpus文を転載しない。
- RuntimeでLLMまたは外部AIを呼び出す変更にしない。
- 未確定の意味を推測で埋めない。
- Generated Proposalを無審査で`dictionaries/system/`へ入れない。
- 関係のない変更を同じPull Requestへ混ぜない。

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

`.github/pull_request_template.md`を埋め、利用者影響、Test、Evidence、License、既知の限界を記録してください。Publicな挙動が変わる場合は`README.md`、`docs/`、`CHANGELOG.md`も更新してください。

## English

### Public repository requirements

A contribution must be reviewable by a third party from public source, tests, provenance, and documentation.

- Do not include secrets, credentials, personal data, private Notion URLs, or local absolute paths.
- Do not copy proprietary dictionary definitions or third-party corpus sentences.
- Do not add runtime LLM or external AI calls.
- Do not invent unresolved meaning.
- Do not auto-promote generated proposals into `dictionaries/system/`.
- Keep unrelated changes out of the same pull request.

### Dictionary evidence

A system dictionary change must include the exact expression or pattern, deterministic interpretation, context constraints, source and license evidence, positive and negative cases, ambiguity and collision cases, at least one Gold Corpus case, and fail-closed coverage when external action behavior is affected.

Homographs, polysemy, reading differences, and containment relations must preserve candidate distinctions rather than collapsing them into one meaning.

### Code and grammar changes

Explain the unsupported or incorrect input, deterministic behavior change, expected Meaning Graph and Task Graph, scope and quotation impact, added regression cases, and compatibility, security, and performance impact.

Run the complete validation command set shown above and record the tested head SHA. Changes affecting the open lexicon, packaging, or releases must also pass GitHub Actions `Release Readiness`.

Use the pull request template and update public documentation and `CHANGELOG.md` whenever user-visible behavior changes.