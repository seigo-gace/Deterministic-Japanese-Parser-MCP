# Deterministic Japanese Parser MCP

<p align="center">
  <strong>日本語を、LLMなしで再現可能・検証可能なMeaningGraphへ変換する決定論的MCPサーバー</strong>
</p>

<p align="center">
  <strong>日本語</strong> ｜ <a href="README_EN.md">English</a>
</p>

<p align="center">
  <a href="https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/actions/workflows/ci.yml/badge.svg"></a>
</p>

## これは何か

Deterministic Japanese Parser MCP（DJPMCP）は、日本語を**生成AIに推測させる前に、再現可能・検証可能・機械処理可能な構造へ変換する**決定論的Parser / MCP Serverです。
中心となる出力は`MeaningGraph`で、語彙、Entity、Clause、Proposition、述語・項、否定・条件・数量・モダリティ、引用帰属、照応、談話関係、曖昧性や不足情報を保持します。
実行候補がある場合は同じ読解結果から`TaskGraph`を派生し、`external_action`では未解決・矛盾・保護対象との衝突などをFail Closedで止めます。
DJPMCP自身は回答文を生成せず、外部サービスも操作しません。

現在の公開Toolは`analyze_japanese`、Program CodeはMIT、Python 3.10+対応です。Self-hosted OSSとOfficial Astera Hosted Commercial Serviceの境界は[`docs/COMMERCIAL_AND_DISTRIBUTION_MODEL.md`](docs/COMMERCIAL_AND_DISTRIBUTION_MODEL.md)を参照してください。

## なぜ決定論的か

同じ入力・Context・Runtime Data・設定から同等の意味構造を再現し、**なぜその読解結果になったかをTest・Hash・Evidenceで検証可能にするため**です。
RuntimeではLLMや外部Generative AIへ依存せず、曖昧な主語・対象・語義・因果を根拠なく補完しません。
External Actionでは「たぶん合っている」を実行許可へ昇格せず、重要な未解決要素が残れば`execution_allowed=false`として止めます。

## 3分で試す

### Linux / macOS

```bash
git clone https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP.git
cd Deterministic-Japanese-Parser-MCP
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
djpmcp-validate
```

MCP Serverを起動：

```bash
djpmcp
```

MCP Client設定例：

```json
{
  "mcpServers": {
    "deterministic-japanese-parser": {
      "command": "/absolute/path/Deterministic-Japanese-Parser-MCP/.venv/bin/djpmcp"
    }
  }
}
```

### Windows PowerShell

```powershell
git clone https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP.git
cd Deterministic-Japanese-Parser-MCP
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
djpmcp-validate
djpmcp
```

WindowsのMCP Clientでは、たとえば次を`command`へ指定します。

```text
C:\path\Deterministic-Japanese-Parser-MCP\.venv\Scripts\djpmcp.exe
```

Pythonから直接試す場合：

```python
from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine

response = ParserEngine().analyze(
    AnalyzeRequest(
        original_text="UIは維持する。APIだけ変更しろ。",
        protected_elements=["UI"],
        execution_mode="external_action",
    )
)

print(response.overall_status)
print(response.execution_allowed)
print(response.meaning_graph.semantic_hash)
```

Streamable HTTP / RESTを使う場合は[`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)と[`docs/PRODUCTION_HTTP_DEPLOYMENT.md`](docs/PRODUCTION_HTTP_DEPLOYMENT.md)を参照してください。

## サンプル入出力

以下は手書きした期待値ではありません。`scripts/readme_examples.py`が実際の`ParserEngine`を実行し、Full `AnalyzeResponse`からREADME表示用Fieldを機械抽出した結果です。Full responseはCIの`reports/readme-examples.json`、表示用は`reports/readme-examples-compact.json`としてEvidence Artifactに保存します。

### 1. COMPLETE — 保護条件を維持してAPIだけ変更

```json
{
  "request": {
    "analysis_depth": "auto",
    "conversation_context": [],
    "deadline_ms": 50,
    "discourse_state": {},
    "execution_mode": "external_action",
    "known_entities": [],
    "original_text": "UIは維持する。APIだけ変更しろ。",
    "protected_elements": ["UI"],
    "social_context": {
      "addressee": null,
      "addressee_group": null,
      "formality": null,
      "mentioned_people": [],
      "setting": null,
      "speaker": null,
      "speaker_group": null
    }
  },
  "response": {
    "overall_status": "COMPLETE",
    "execution_allowed": true,
    "blocked_reasons": [],
    "analysis_path": "DEEP",
    "semantic_hash": "a10116e63f9c90641e1a7167bdbb310adc61103381522177fdddac120825bcc9",
    "proposition_count": 5,
    "task_count": 1,
    "ambiguity_count": 0,
    "contradiction_count": 0,
    "missing_information_count": 0,
    "unsupported_element_count": 0
  }
}
```

### 2. PARTIAL — 指示対象が解決できない

```json
{
  "request": {
    "analysis_depth": "auto",
    "conversation_context": [],
    "deadline_ms": 50,
    "discourse_state": {},
    "execution_mode": "external_action",
    "known_entities": [],
    "original_text": "それを変更しろ。",
    "protected_elements": [],
    "social_context": {
      "addressee": null,
      "addressee_group": null,
      "formality": null,
      "mentioned_people": [],
      "setting": null,
      "speaker": null,
      "speaker_group": null
    }
  },
  "response": {
    "overall_status": "PARTIAL",
    "execution_allowed": false,
    "blocked_reasons": ["AMBIGUOUS_OR_INSUFFICIENT_REFERENCE"],
    "analysis_path": "DEEP",
    "semantic_hash": "902e5d49d1d1faa3fe34120ddf1d1600b8bce2287621d3e430a8b24464184655",
    "proposition_count": 4,
    "task_count": 1,
    "ambiguity_count": 0,
    "contradiction_count": 0,
    "missing_information_count": 2,
    "unsupported_element_count": 0
  }
}
```

### 3. Fail Closed — protected elementとの衝突

```json
{
  "request": {
    "analysis_depth": "auto",
    "conversation_context": [],
    "deadline_ms": 50,
    "discourse_state": {},
    "execution_mode": "external_action",
    "known_entities": [],
    "original_text": "UIを変更しろ。",
    "protected_elements": ["UI"],
    "social_context": {
      "addressee": null,
      "addressee_group": null,
      "formality": null,
      "mentioned_people": [],
      "setting": null,
      "speaker": null,
      "speaker_group": null
    }
  },
  "response": {
    "overall_status": "PARTIAL",
    "execution_allowed": false,
    "blocked_reasons": ["CONTRADICTORY"],
    "analysis_path": "DEEP",
    "semantic_hash": "e75467c8de66a1af2cc7c038fb5dd1254136b5e388f492698806f731aece185f",
    "proposition_count": 3,
    "task_count": 1,
    "ambiguity_count": 0,
    "contradiction_count": 2,
    "missing_information_count": 0,
    "unsupported_element_count": 0
  }
}
```

実際の完全なResponseにはToken、MeaningGraph、Reading Analysis、TaskGraph、Reference、Intent compatibility view、Metrics、Versions等も含まれます。完全な契約は[`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)を参照してください。

## 詳細はどこ

| 確認したい内容 | Document |
|---|---|
| 公開Document全体 | [`docs/README.md`](docs/README.md) |
| MCP / REST / Python API | [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) |
| Environment Variables / Runtime設定 | [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) |
| 日本語読解・MeaningGraph契約 | [`docs/JAPANESE_READING_CONTRACT.md`](docs/JAPANESE_READING_CONTRACT.md) |
| Semantic品質契約 | [`docs/SEMANTIC_QUALITY_CONTRACT.md`](docs/SEMANTIC_QUALITY_CONTRACT.md) |
| Performance / Release Gate | [`docs/PERFORMANCE_AND_RELEASE_CONTRACT.md`](docs/PERFORMANCE_AND_RELEASE_CONTRACT.md) |
| 開発・CI・Evidence | [`docs/DEVELOPMENT_AND_CI.md`](docs/DEVELOPMENT_AND_CI.md) |
| Source Codeの責務Map | [`docs/SOURCE_MAP.md`](docs/SOURCE_MAP.md) |
| Dictionary / Language Runtime | [`docs/LANGUAGE_DATA_RUNTIME.md`](docs/LANGUAGE_DATA_RUNTIME.md) |
| Open Dictionary Supply Chain | [`docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md`](docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md) |
| Production HTTP | [`docs/PRODUCTION_HTTP_DEPLOYMENT.md`](docs/PRODUCTION_HTTP_DEPLOYMENT.md) |
| Public OSS / Hosted Commercial境界 | [`docs/COMMERCIAL_AND_DISTRIBUTION_MODEL.md`](docs/COMMERCIAL_AND_DISTRIBUTION_MODEL.md) |
| Astera Hosted API Architecture | [`docs/ASTERA_HOSTED_API_ARCHITECTURE.md`](docs/ASTERA_HOSTED_API_ARCHITECTURE.md) |
| Security報告 | [`SECURITY.md`](SECURITY.md) |
| Contribution | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| License / Third-party Notice | [`LICENSE`](LICENSE) / [`NOTICE.md`](NOTICE.md) |
| Governance / Brand | [`GOVERNANCE.md`](GOVERNANCE.md) / [`TRADEMARK.md`](TRADEMARK.md) |

Program CodeはMITです。Third-party Dataには個別のSource Licenseが適用される場合があります。実測性能値はCI Evidenceと対応するCommitを確認してください。
