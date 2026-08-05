# Deterministic Japanese Parser MCP

<p align="center">
  <strong>生成AIを使わず、日本語の意味・条件・禁止・例外・参照・実行可否を再現可能な構造へ変換するMCPサーバー</strong>
</p>

<p align="center">
  <strong>日本語</strong> ｜ <a href="README_EN.md">English</a>
</p>

<p align="center">
  <a href="https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/actions/workflows/ci.yml/badge.svg"></a>
</p>

| 項目 | 内容 |
|---|---|
| 実行方式 | 非AI・非生成・決定論的 |
| 対応環境 | Python 3.10以上 |
| 接続方式 | MCP標準入出力・Python API |
| プログラムのライセンス | MIT |
| 実行時の外部AI接続 | なし |
| 実行時の外部辞書接続 | なし |

[導入](#導入) ｜ [使い方](#使い方) ｜ [検証](#検証) ｜ [検証に参加する](VALIDATION.md) ｜ [不具合を報告する](https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/issues/new?template=bug_report.yml) ｜ [公開検証・質問](https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/discussions)

---

## これは何か

**Deterministic Japanese Parser MCP**は、日本語入力を単純な意図一覧へ変換するのではなく、次の情報を接続した**意味グラフ**へ変換します。

- 誰が、何を、何に対して求めているか
- 条件、例外、禁止、維持、優先順位、順序、依存関係
- 引用、疑問、仮定、伝聞、訂正、撤回
- 省略された対象と、解決できない参照
- 外部操作として実行してよい内容と、止めるべき内容

実行時に大規模言語モデルや外部AIを呼び出しません。固定された辞書、形態情報、事前構築した規則索引、文法処理、範囲解決、会話文脈、矛盾検出、作業グラフ、外部操作保護機構を使って処理します。

このサーバー自体は回答文を生成しません。後続システムが、日本語の指示や制約を安全に扱うための構造を返します。

## 何が返るか

主な出力は次のとおりです。

- `meaning_graph.entities`：対象、人、物、組織など
- `meaning_graph.clauses`：文節・節の構造
- `meaning_graph.propositions`：要求、判断、状態、関係
- `meaning_graph.scope_edges`：否定、条件、引用、疑問などの適用範囲
- `meaning_graph.unresolved`：解決できなかった意味・参照・省略
- `task_graph.tasks`：実行候補
- `task_graph.constraints`：維持、禁止、条件、例外、保護対象
- `execution_allowed`：外部操作を許可できるか
- `blocked_reasons`：停止理由

同じ入力、同じ文脈、同じ辞書・規則版からは、同じ意味ハッシュを返します。

## 安全性の中心設計

次の入力を、そのまま外部操作へ昇格させません。

- 引用内に書かれた命令
- 「削除するべき？」のような疑問
- 「もし不要なら削除する」のような仮定
- 「削除しろと言われた」のような伝聞
- 対象が解決できない指示語
- 維持対象と変更対象が矛盾する指示
- 制限時間内に意味を確定できなかった入力

重要な意味、対象、範囲、矛盾が未解決の場合は、推測で埋めず外部操作を停止します。

## 現在の収録規模

| データ | 件数 |
|---|---:|
| 比喩・慣用・語用表現 | **452** |
| 決定論的な意図規則 | **339** |
| 意図種別 | **21** |
| 類義語の正規化グループ | **100** |
| 作業・手順ひな型 | **63** |
| 手順群 | **42** |
| 正解検証用データ | **649** |

公開版の配布物では、公式JMdictから加工・照合した**120,000件の語彙記録**を完全オフラインで読み込みます。

この12万件は語彙識別用の基礎データです。全語の意味・語用・実行意図を自動承認したものではありません。

## 12万件語彙データの検証結果

| 検証項目 | 結果 |
|---|---:|
| 元データとの一致 | **120,000 / 120,000** |
| 完全一致検索 | **154,918 / 154,918** |
| 同じ表記に複数候補がある語 | **962件、全候補保持** |
| 包含語の誤統合検査 | **20,000 / 20,000** |
| 文中の部分一致汚染 | **20,000件中、誤一致0** |
| 検出された正確性エラー | **0** |

詳細は[`docs/OPEN_LEXICON_ACCURACY.md`](docs/OPEN_LEXICON_ACCURACY.md)を参照してください。

## 辞書を追加する仕組み

無料で機械処理可能な辞書資源を、次の順序で処理します。

```text
公式公開データ
  ↓
固定版の取得・ハッシュ記録
  ↓
出典別の変換
  ↓
共通形式への統一
  ↓
重複・衝突・多義の検査
  ↓
肯定例・否定例・境界例の作成
  ↓
人による意味・出典・ライセンス確認
  ↓
全回帰・安全性・性能・オフライン検証
  ↓
承認済みデータだけを反映
```

対応する主な公開資源：

- Japanese Wiktionary
- Wikidata Lexemes
- JMdict
- SudachiDictの公開元データ

候補データは自動で本番辞書へ入りません。意味、使用文脈、出典、ライセンス、衝突、安全性を確認したものだけを反映します。

詳細：

- [`docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md`](docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md)
- [`tools/README.md`](tools/README.md)
- [`dictionaries/README.md`](dictionaries/README.md)

## 導入

### Linux・macOS

```bash
git clone https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP.git
cd Deterministic-Japanese-Parser-MCP
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
djpmcp
```

### Windows PowerShell

```powershell
git clone https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP.git
cd Deterministic-Japanese-Parser-MCP
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
djpmcp
```

## 使い方

### Pythonから呼び出す

```python
from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine

response = ParserEngine().analyze(
    AnalyzeRequest(
        original_text="UIは維持する。APIだけ変更しろ。",
        execution_mode="external_action",
        deadline_ms=50,
    )
)

print(response.meaning_graph)
print(response.task_graph)
print(response.execution_allowed)
print(response.blocked_reasons)
```

### 処理の流れ

```text
入力
  ↓
原文保存・正規化・位置対応
  ↓
形態情報
  ↓
規則・比喩・語用候補
  ↓
文法処理
  ↓
意味グラフ
  ↓
範囲・参照・矛盾の検証
  ↓
作業グラフと制約
  ↓
外部操作の許可・停止判定
  ↓
形式検証済み応答
```

## 検証

```bash
python tools/lexicon_validator.py
python tools/validator.py
pytest
python scripts/benchmark.py --check
python scripts/performance_contract.py --check --max-ready-ms 10
python scripts/astera_latency_contract.py --check --target-ms 10 --hard-ms 50
python -m compileall -q src tools scripts tests
```

継続検証では次を確認します。

- Python 3.10・3.12
- 辞書と正解検証データの整合性
- 意味グラフと作業グラフ
- 引用・疑問・否定・仮定・参照の安全性
- 12万件語彙データと元データの一致
- 完全一致・多義保持・部分一致汚染
- MCP標準入出力
- オフライン導入
- 辞書20倍規模での性能
- 通常10ミリ秒目標・絶対50ミリ秒上限

## 公開検証への参加

コードを書けなくても参加できます。

- 5分で日本語の解釈を確認する
- 不自然・疑わしい結果を投稿する
- Windows、macOS、Linux、各MCPクライアントで動作確認する
- 方言、俗語、比喩、慣用表現の意味を確認する
- 5,000件候補データの出典・読み・意味・地域・世代・ライセンスを確認する

参加方法は[`VALIDATION.md`](VALIDATION.md)にまとめています。

### Discussionsで扱う内容

- 検証参加と検証結果
- 判断に迷う解析
- 日本語表現の確認
- 導入環境の確認
- 候補データの根拠確認
- 質問と初期段階の改善案

[Discussionsを開く](https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/discussions)

### Issuesで扱う内容

Issuesは、**確認済みで再現可能な不具合・回帰の修正追跡専用**です。

質問、未確認の違和感、検証参加、初期案はIssuesへ入れず、Discussionsを使用します。

[確認済み不具合を報告する](https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/issues/new?template=bug_report.yml)

脆弱性の詳細は公開IssueやDiscussionへ書かず、[`SECURITY.md`](SECURITY.md)に従ってください。

## 性能契約

| 測定範囲 | 条件 |
|---|---:|
| 常駐済み内部処理の最適目標 | 5ミリ秒以下 |
| 通常の呼び出し目標 | 95パーセンタイルで10ミリ秒以下 |
| 絶対上限 | 50ミリ秒以下 |
| 上限までに解決できない場合 | `TIMEOUT`を返し外部操作を停止 |

測定範囲には、常駐標準入出力、応答の読み取り、出力形式検証、意味グラフ・作業グラフ・保護判定の受け渡しを含みます。

## 限界

このプロジェクトは、あらゆる日本語を人間と同等に理解できるとは主張しません。

皮肉、広い常識、複雑な省略、長い複数段落の談話、地域・世代・共同体に強く依存する表現など、固定した辞書と規則で根拠を説明できない内容は未解決として返します。

12万件語彙検証は語彙識別の正確性を確認するものであり、12万語すべての意味理解を保証するものではありません。

## 文書案内

- [`docs/README.md`](docs/README.md)：公開文書の索引
- [`VALIDATION.md`](VALIDATION.md)：第三者検証への参加方法
- [`SUPPORT.md`](SUPPORT.md)：質問・不具合・安全報告の使い分け
- [`CONTRIBUTING.md`](CONTRIBUTING.md)：コード・辞書・検証データの提供条件
- [`docs/SEMANTIC_QUALITY_CONTRACT.md`](docs/SEMANTIC_QUALITY_CONTRACT.md)：意味品質契約
- [`docs/OPEN_LEXICON_ACCURACY.md`](docs/OPEN_LEXICON_ACCURACY.md)：12万件語彙の正確性検証
- [`docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md`](docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md)：辞書追加の設計
- [`docs/PUBLIC_RELEASE_CHECKLIST.md`](docs/PUBLIC_RELEASE_CHECKLIST.md)：公開版の必須検証
- [`CHANGELOG.md`](CHANGELOG.md)：変更履歴

<!-- project-control-ja:start -->
## 所有・管理・ブランド

**設計・開発・管理：加藤星悟（[`@seigo-gace`](https://github.com/seigo-gace)）。**

公式リポジトリ、設計方針、公開版、外部提供物の採用、名称・ロゴなどの利用許可に関する最終決定権は、[`GOVERNANCE.md`](GOVERNANCE.md)に従ってプロジェクト所有者が保持します。

プログラムはMITライセンスで利用・改変・再配布できます。ただし、MITライセンスは、改変版や派生サービスを公式版として表示するための名称・ロゴ・ブランド利用権を与えません。詳細は[`TRADEMARK.md`](TRADEMARK.md)を参照してください。

外部提供には開発者証明への署名が必要です。実質的なコード、辞書、正解検証データ、設計、公開、安全性、管理規程の変更には、統合前にプロジェクト所有者が受領した[`CONTRIBUTOR_LICENSE_AGREEMENT.md`](CONTRIBUTOR_LICENSE_AGREEMENT.md)が必要です。
<!-- project-control-ja:end -->

## ライセンス

プログラムコードはMITライセンスです。詳細は[`LICENSE`](LICENSE)と[`NOTICE.md`](NOTICE.md)を参照してください。

外部辞書から反映したデータには、各記録と出典台帳に記載された元データのライセンスが適用されます。
