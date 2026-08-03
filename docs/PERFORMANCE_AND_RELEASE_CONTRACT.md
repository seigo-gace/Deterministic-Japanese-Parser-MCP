# Deterministic Japanese Parser MCP
# Performance and Release Contract

## 1. 目的

このMCPは回答生成AIではない。日本語入力を、原文Span、Entity、Clause、Proposition、Argument、型付きScope、Task Constraint、外部Action可否を持つMeaning Graphへ、非AI・非生成・決定論的に変換する。

速度のために意味解析機能を削除してはならない。高速経路、Cache、Indexは、非高速経路とSemantic Responseが一致すると自動検証できる場合だけReleaseへ採用する。

## 2. 意味正本

- Meaning Graphを唯一の意味正本とする。
- Rule / Regexは候補とEvidenceを供給し、最終的なTask／Guardを直接決定しない。
- 旧`intents`、`references`、`tasks`はMeaning Graphから生成する互換Viewとする。
- 禁止、維持、条件、例外、対象範囲、完了条件、検証条件は、原則としてAction Taskへ接続されたConstraintとする。
- 引用内・疑問・反語候補・未解決参照の命令を外部Actionとして許可しない。

## 3. 正確性契約

Release候補は以下をすべて満たす。

- Gold Corpus全件成功
- Meaning Graph専用Test成功
- Indexed RuleとExhaustive RuleのSemantic Response一致
- 原文、正規化、Span、Meaning Graph、Task Graph、Guard、互換Viewの回帰なし
- 同一入力・同一Context・同一Versionで同一Semantic Hash
- Cache Hit / MissでSemantic Hash一致
- 引用内命令の誤実行0
- 疑問文内命令の誤実行0
- Scope未確定Actionの誤許可0
- 未解決参照を含むActionの誤許可0
- 保護対象への誤変更許可0
- Python 3.10 / 3.12で同じ意味結果
- MCP stdio E2E成功

Metric、実行時間、Candidate数は意味同値比較から除外し、性能Gateで別途検証する。

## 4. 性能契約

### 4.1 Astera全体

Asteraの回答処理全体目標は100ms以内とする。

### 4.2 MCP通常目標

Astera側でのCall開始から、常駐local stdioを通じてServer応答を受け、Decodeし、事前Compile済みの正式Pydantic Schemaで完全検証し、Meaning Graph・Task Graph・Guard結果を後続処理へ渡せる状態になるまで、p95 10ms以下を通常目標とする。

### 4.3 絶対上限

同じ測定境界で50msを絶対上限とする。50ms以内に確定できない場合、推測した結果を成功として返さず、`TIMEOUT`を明示し、外部ActionをBlockする。

### 4.4 内部最適目標

常駐済みKernelおよびLowLatency local stdio経路の最適目標として5ms以下を維持する。ただし5msを満たさないだけで、10ms通常目標と50ms絶対上限を満たすReleaseを失敗とはしない。

### 4.5 Ready前処理

次をRuntime測定へ混ぜない代わりに、MCP Ready前に必ず完了する。

- Package Import
- Sudachi Dictionary初期化
- System / User辞書読込
- Regex Compile
- Literal / Metaphor Index構築
- Grammar Table構築
- Dictionary Snapshot確定
- Output Schema Compile
- 代表入力によるPrewarm

### 4.6 Remote境界

Remote Network、MCP Host間通信、利用者端末、UI描画は本Repository単体の保証外とする。製品側は入力確定から画面描画完了までを別Probeで測定し、本MCPのlocal stdio結果と混同しない。

## 5. 辞書拡張契約

辞書量が増えても全辞書を単純全走査しない。

- Literal Rule / Metaphor: Aho-Corasick型Index
- 機能表現・活用: Compile済みGrammar Table
- 述語・Domain: Key別Index / Shard
- Runtime辞書: Immutable Version Snapshot
- Snapshot更新: 別領域でCompile・検証後に原子的切替

「辞書が無制限に増えても処理量が変わらない」とは保証しない。保証容量、最大入力長、最大Context数、最大Candidate数、最大Graph Node数、MemoryをRelease Reportへ明記する。

Scale Testは次を分離して行う。

1. Non-match Scale：無関係Entry大量追加
2. High-match Scale：一入力への大量一致
3. Collision Scale：同一表現の意味衝突
4. Domain Scale：Domain数とShard増加
5. Grammar Scale：機能表現・文法候補増加
6. Context Scale：会話State増加
7. Graph Scale：Clause / Proposition / Scope Edge増加
8. Cache Hit / Miss意味同値
9. Snapshot切替前後の決定性

現在の20倍Decoy試験はNon-match Scaleの証拠として維持するが、それだけで全衝突耐性を証明したとは報告しない。

## 6. DeadlineとFail Closed

すべてのPhaseは共通の50ms Deadlineを共有する。Candidate上限、Graph Node上限、Scope Edge上限へ達した場合、候補を勝手に捨てて一件へ確定しない。

- 確定可能：`RESOLVED`
- 複数解釈：`AMBIGUOUS`
- 必須情報不足：`INSUFFICIENT`
- 未対応：`UNSUPPORTED`
- 矛盾：`CONTRADICTORY`
- Deadline到達：`TIMEOUT`

External Actionでは対象ActionのAction-Relevance Closureに未解決NodeがあればBlockする。無関係な説明文の曖昧さだけで全Actionを止めないが、関連性そのものが不明ならBlockする。

## 7. Deployment前の必須順序

1. Source Checkout
2. Build Tool取得
3. Runtime / Test依存をWheelhouseへ全Download / Build
4. Project Wheel作成
5. WheelhouseとProject WheelのSHA-256 Manifest作成
6. Clean Virtual Environment作成
7. `PIP_NO_INDEX=1`、`--no-index`でWheelhouseのみからInstall
8. Repository外からInstalled WheelをImport
9. Deployment Preflight
10. Dictionary / Gold Validator
11. pytest / MCP stdio E2E
12. Indexed / Exhaustive Semantic Parity
13. 20倍辞書Performance Contract
14. Astera 10ms / 50ms Call-through Contract
15. compileall
16. Report、Manifest、Wheelhouse、WheelをArtifact保存

Dependency準備後にRuntime Downloadを必要とする構成はRelease不可とする。

## 8. Release Evidence

- Project Wheel
- Dependency Wheelhouse
- SHA-256 Manifest
- Dependency一覧
- Preflight Report
- Validator Report
- pytest JUnit
- Benchmark Report
- Dictionary Scale Report
- Astera Latency Report
- MCP stdio E2E Evidence

GitHub Actionsの緑表示だけでなく、Report本文とArtifactを確認可能にする。

## 9. 完了条件

- [ ] Meaning Graphが唯一の意味正本
- [ ] Legacy Intent / Taskが互換View
- [ ] Quote / Interrogative Fail Closed
- [ ] ActionとConstraintが分離
- [ ] Gold Corpus成功
- [ ] Meaning Graph専用Test成功
- [ ] Indexed / Exhaustive意味同値
- [ ] Semantic Hash決定性
- [ ] Python 3.10 / 3.12成功
- [ ] p95 10ms以下
- [ ] 最大50ms以下
- [ ] 20倍辞書で意味不変
- [ ] Collision / Context / Graph Scaleの証拠
- [ ] Offline Install成功
- [ ] Runtime Downloadなし
- [ ] MCP stdio E2E成功
- [ ] 全EvidenceをArtifact保存

一項目でも失敗した状態を「完全」または「Verified」と報告してはならない。

---

## English summary

The parser uses a Meaning Graph as its single semantic source of truth. Rules provide candidates and evidence; typed scope relations, action constraints, and an action-relevance guard determine execution safety. The normal Astera-side call-through target is p95 <= 10 ms, the absolute validated-response handoff limit is 50 ms, and Astera's total response target is 100 ms. A resident 5 ms path remains an optimization goal rather than the only release gate. Releases must preserve legacy compatibility views, deterministic semantic hashes, fail-closed quotation/interrogative behavior, indexed/exhaustive parity, dictionary-scale evidence, offline installation, and complete CI artifacts.
