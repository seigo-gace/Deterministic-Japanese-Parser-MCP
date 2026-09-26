# Deterministic Japanese Parser MCP

> [`README.md`](README.md) (Japanese) is the primary project README. This English README follows the same public contract.

<p align="center">
  <strong>A deterministic MCP server that turns Japanese into reproducible, testable MeaningGraphs without an LLM</strong>
</p>

<p align="center">
  <a href="README.md">日本語</a> ｜ <strong>English</strong>
</p>

<p align="center">
  <a href="https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/actions/workflows/ci.yml/badge.svg"></a>
</p>

## What this is

Deterministic Japanese Parser MCP (DJPMCP) converts Japanese into **reproducible, testable, machine-processable structures before a generative model has to guess what the text means**.
Its primary output is the `MeaningGraph`, preserving lexical candidates, entities, clauses, propositions, predicate-argument structure, scope, attribution, reference, discourse relations, ambiguity, and missing information.
When actionable content exists, the same reading can produce a `TaskGraph`; in `external_action` mode, unresolved meaning, contradictions, or conflicts with protected elements remain fail-closed.
DJPMCP does not generate answer text and does not operate external services itself.

The current public tool is `analyze_japanese`, the program code is MIT-licensed, and Python 3.10+ is supported. For the boundary between self-hosted OSS and the official Astera hosted commercial service, see [`docs/COMMERCIAL_AND_DISTRIBUTION_MODEL.md`](docs/COMMERCIAL_AND_DISTRIBUTION_MODEL.md).

## Why deterministic

Equivalent input, context, runtime data, and configuration should produce equivalent semantic structures so the result can be **tested, hashed, audited, and reproduced**.
The runtime does not depend on an LLM, external generative AI, or network inference, and it does not silently guess unresolved subjects, targets, senses, or causal relations.
For external actions, uncertainty is not promoted into permission: material unresolved state keeps `execution_allowed=false`.

## Try it in 3 minutes

### Linux / macOS

```bash
git clone https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP.git
cd Deterministic-Japanese-Parser-MCP
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
djpmcp-validate
djpmcp
```

MCP client example:

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

Example Windows MCP command path:

```text
C:\path\Deterministic-Japanese-Parser-MCP\.venv\Scripts\djpmcp.exe
```

Direct Python example:

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

For Streamable HTTP and REST, see [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) and [`docs/PRODUCTION_HTTP_DEPLOYMENT.md`](docs/PRODUCTION_HTTP_DEPLOYMENT.md).

## Sample input and output

These values are not hand-written expected output. `scripts/readme_examples.py` executes the real `ParserEngine`, stores the full response in `reports/readme-examples.json`, and mechanically extracts the compact README view into `reports/readme-examples-compact.json` for CI evidence.

### 1. COMPLETE — preserve UI, modify only the API

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

### 2. PARTIAL — unresolved reference

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

### 3. Fail closed — conflicts with a protected element

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

The complete response also contains tokens, MeaningGraph, reading analysis, TaskGraph, references, compatibility intent/task views, metrics, and version data. See [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) for the full contract.

## Where to find details

| Topic | Document |
|---|---|
| Documentation index | [`docs/README.md`](docs/README.md) |
| MCP / REST / Python API | [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) |
| Environment / runtime configuration | [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) |
| Japanese reading and MeaningGraph contract | [`docs/JAPANESE_READING_CONTRACT.md`](docs/JAPANESE_READING_CONTRACT.md) |
| Semantic quality contract | [`docs/SEMANTIC_QUALITY_CONTRACT.md`](docs/SEMANTIC_QUALITY_CONTRACT.md) |
| Performance / release gates | [`docs/PERFORMANCE_AND_RELEASE_CONTRACT.md`](docs/PERFORMANCE_AND_RELEASE_CONTRACT.md) |
| Development / CI / evidence | [`docs/DEVELOPMENT_AND_CI.md`](docs/DEVELOPMENT_AND_CI.md) |
| Source map | [`docs/SOURCE_MAP.md`](docs/SOURCE_MAP.md) |
| Language runtime | [`docs/LANGUAGE_DATA_RUNTIME.md`](docs/LANGUAGE_DATA_RUNTIME.md) |
| Dictionary supply chain | [`docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md`](docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md) |
| Production HTTP | [`docs/PRODUCTION_HTTP_DEPLOYMENT.md`](docs/PRODUCTION_HTTP_DEPLOYMENT.md) |
| OSS / hosted commercial boundary | [`docs/COMMERCIAL_AND_DISTRIBUTION_MODEL.md`](docs/COMMERCIAL_AND_DISTRIBUTION_MODEL.md) |
| Astera hosted API architecture | [`docs/ASTERA_HOSTED_API_ARCHITECTURE.md`](docs/ASTERA_HOSTED_API_ARCHITECTURE.md) |
| Security | [`SECURITY.md`](SECURITY.md) |
| Contributions | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| License / third-party notices | [`LICENSE`](LICENSE) / [`NOTICE.md`](NOTICE.md) |
| Governance / brand | [`GOVERNANCE.md`](GOVERNANCE.md) / [`TRADEMARK.md`](TRADEMARK.md) |

Program code is MIT-licensed. Third-party data may remain under its own source license. Treat measured performance as authoritative only together with the corresponding CI evidence and commit.
