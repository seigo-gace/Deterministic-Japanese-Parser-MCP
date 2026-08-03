from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import promoter


def test_sync_metadata_updates_bilingual_counts_versions_and_notice(tmp_path):
    manifest_path = tmp_path / "dictionaries/system/metaphors/manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps({
            "dictionary_version": "1.2.0",
            "metaphor_entries": 1,
        }),
        encoding="utf-8",
    )
    readme = """| 比喩・慣用・語用表現 | **1** |
| 決定論的Intent Pattern | **1** |
| 類義語Canonical Group | **1** |
| Task / Workflow Template | **1** |
| Workflow | **1** |
| Gold Corpus | **1** |
| Open lexical records | **0** |
| Metaphor, idiom, and pragmatic expressions | **1** |
| Deterministic intent patterns | **1** |
| Canonical synonym groups | **1** |
| Task / workflow templates | **1** |
| Workflows | **1** |
| Gold Corpus cases | **1** |
| Open lexical records | **0** |
"""
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    (tmp_path / "NOTICE.md").write_text(
        "# Third-party notices\n",
        encoding="utf-8",
    )
    version_path = tmp_path / "src/deterministic_japanese_parser_mcp/version.py"
    version_path.parent.mkdir(parents=True)
    version_path.write_text(
        'VERSION = {\n'
        '    "dictionary_version": "1.2.0",\n'
        '    "rule_version": "1.2.0",\n'
        '    "metaphor_dictionary_version": "1.2.0",\n'
        '}\n',
        encoding="utf-8",
    )
    proposal = {
        "proposal_id": "PROP-1",
        "kind": "lexicon",
        "evidence": [{
            "dataset": "Wikidata Lexemes",
            "version": "fixture-1",
            "license": "CC0-1.0",
            "source_id": "L1",
            "source_sha256": "abc",
            "attribution": "Wikidata contributors",
        }],
    }
    counts = {
        "metaphors": 452,
        "rules": 339,
        "synonym_groups": 101,
        "templates": 63,
        "workflows": 42,
        "gold": 649,
        "lexicon_records": 10,
    }
    promoter.sync_metadata(
        tmp_path,
        counts,
        [proposal],
        "fixture-batch",
    )
    updated_readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert updated_readme.count("| Open lexical records | **10** |") == 2
    updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert updated_manifest["dictionary_version"] == "1.2.1"
    assert updated_manifest["open_lexicon_records"] == 10
    updated_version = version_path.read_text(encoding="utf-8")
    assert '"dictionary_version": "1.2.1"' in updated_version
    assert '"rule_version": "1.2.0"' in updated_version
    assert '"metaphor_dictionary_version": "1.2.0"' in updated_version
    notice = (tmp_path / "NOTICE.md").read_text(encoding="utf-8")
    assert "fixture-batch" in notice
    assert "Wikidata contributors" in notice
