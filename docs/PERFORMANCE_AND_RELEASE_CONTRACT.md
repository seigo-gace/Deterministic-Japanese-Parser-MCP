# Shiori / Deterministic Japanese Parser MCP
# Performance and Release Contract

## 1. MCPの本来の目的

このMCPは回答文を生成するAIではない。日本語の入力から、意図、制約、指示対象、比喩、矛盾、実行順序、外部Actionの可否を、非AI・非生成・決定論的に抽出し、後続Systemが安全に扱える構造へ変換するParserである。

速度改善のために解析機能を削除してはならない。高速経路は、全件解析と同じ意味結果を返すことを自動検証できる場合だけ採用する。

## 2. 正確性契約

Release候補は以下をすべて満たさなければならない。

- Gold Corpus全件成功
- Indexed RuleとExhaustive Ruleの意味結果一致
- 原文、正規化結果、Intent、Capture、Rule ID、Span、Reference、Metaphor、Task、Dependency、Guard結果の回帰なし
- 同一入力・同一Context・同一Versionで同一Semantic Hash
- 外部Actionで曖昧性、矛盾、Timeoutがある場合はBlock
- Python 3.10と3.12で同じ意味結果
- MCP stdio E2E成功

時間、候補数などのMetricは実行環境差があるため意味同値比較から除外するが、別の性能Gateで検証する。

## 3. 速度契約

### 3.1 5msの測定境界

このRepositoryが保証対象にできる「利用者へ結果が到達するまで」は、常駐済みのローカルMCP Clientが`call_tool`を開始してから、stdioを通じてServerが完全な構造化応答を返し、MCP SDKがDecodeを完了するまでとする。

以下を自動計測する。

1. Parser内部の短文Warm応答 p95
2. Parser内部の複合文Warm応答 p95
3. MCP初期化完了後の最初のTool Call
4. 常駐stdio Tool Call p95
5. 20倍辞書での短文／複合文Warm応答 p95
6. 20倍辞書・20,000文字でのRule／Metaphor Index検索 p95

各項目のRelease Gateは **5.000ms以下** とする。

### 3.2 Cold Start

Process起動、Python Import、Sudachi Dictionary読込、辞書File読込、Regex Compile、Index構築は5ms契約へ混ぜない。その代わり、これらをMCP handshake前に必ず完了する。

`server.prewarm()`は以下を実行してからstdio受付を開始する。

- 全辞書読込
- 全Regex Compile
- Rule／Metaphor Index構築
- Sudachi初期化
- 代表入力による一度目の完全解析

Cold Start時間はReportへ記録するが、Ready後のTool Callと混同しない。

### 3.3 Network／UIを含む製品全体

Remote Network、MCP Host、利用者端末、UI描画はこのRepositoryの制御外であり、本Repository単体から5msを保証したと報告してはならない。Remote製品へ組み込む場合は、製品側で「入力確定から画面描画完了まで」の外部Probeを追加し、本MCPのstdio測定と分離して提出する。

## 4. 辞書拡張契約

「辞書が無制限に増えても計算量が一切増えない」という保証は行わない。保証容量を明示し、実データで検証する。

現在のRelease Gateは次の20倍構成とする。

- Rule: 150件から3,000件
- Metaphor: 152件から3,040件
- 既存の短文／複合文に一致しないDecoy辞書を追加
- Base辞書と20倍辞書のSemantic Response完全一致
- 20倍構成でも5ms Gateを維持

RuleとMetaphorのLiteral検索にはAho-Corasick型Indexを使用し、検索時間を登録Literal数の単純全走査へ依存させない。証明不能なRegex Ruleは必ずExhaustive Fallbackへ残す。

保証容量を拡張する場合は、Scale値、最大文字数、Context数、p50／p95／p99、Memory、Semantic Parityを更新してからReleaseする。

## 5. Deployment前の必須順序

Release用Workflowは次の順序を変更してはならない。

1. Source Checkout
2. Build Toolの取得
3. Runtime／Test依存をWheelhouseへ全Download・Build
4. Project Wheel作成
5. WheelhouseとProject WheelのSHA-256 Manifest作成
6. 新しいVirtual Environment作成
7. `PIP_NO_INDEX=1`と`--no-index`でWheelhouseだけからInstall
8. Repository外のWorking DirectoryからInstalled WheelをImport
9. `scripts/preflight.py`
10. Dictionary／Gold Validator
11. pytestとMCP stdio E2E
12. 5ms Performance Contract
13. compileall
14. Test Report、Performance Report、Manifest、Wheelhouse、Project WheelをArtifact化

Step 3より後にNetwork Downloadを必要とする構成はRelease不可とする。Runtime起動時のModel／辞書／依存Downloadは禁止する。

## 6. 客観的エビデンス

Release Artifactには以下を含める。

- Project Wheel
- 全依存WheelのWheelhouse
- SHA-256 Release Manifest
- 解決済みDependency一覧
- Preflight Report
- Performance Contract Report
- pytest結果
- Validator結果

GitHub Actionsの成功表示だけでなく、Report本文とArtifactを確認できる状態を残す。

## 7. 完了条件チェックリスト

- [ ] MCPの目的を変えていない
- [ ] 解析機能を速度のために削除していない
- [ ] Gold Corpus全件成功
- [ ] Indexed／Exhaustive意味同値
- [ ] 20回以上の決定性Hash一致
- [ ] Python 3.10／3.12成功
- [ ] 常駐stdioの最初のCallが5ms以下
- [ ] 常駐stdio p95が5ms以下
- [ ] 20倍辞書のCore p95が5ms以下
- [ ] 20倍辞書で意味結果不変
- [ ] Offline Install成功
- [ ] Installed Wheelから辞書を読める
- [ ] Runtime Downloadがない
- [ ] Manifestの全FileにSHA-256がある
- [ ] MCP stdio E2E成功
- [ ] Test／Performance ReportをArtifact保存

一項目でも失敗した状態を「完了」と報告してはならない。

---

## English summary

This MCP is a deterministic Japanese parser, not a response-generating AI. Release candidates must preserve full semantic behavior, pass Gold and exhaustive-parity checks, preload all runtime data before the MCP handshake, install from a fully prepared offline wheelhouse, and meet a 5ms ready-state latency gate for internal parsing and persistent local stdio calls. The current tested expansion capacity is 20x the bundled rule and metaphor dictionaries. Remote network and UI latency must be measured separately by the consuming product and must never be presented as guaranteed by this repository alone.
