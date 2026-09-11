from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_source_authored_meaning_release_workflow_uses_github_release_not_drive() -> None:
    text = (ROOT / ".github/workflows/source-authored-meaning-data-release.yml").read_text(encoding="utf-8")

    assert "Source-authored Meaning Data Release" in text
    assert "gh release download" in text
    assert "GOOGLE_DRIVE" not in text
    assert "drive" not in text.lower()
    assert "source_authored_meaning_release_contract.py" in text
    assert "mcp-source-authored-meaning-factory-v1.zip" in text
    assert "mcp-auxiliary-source-role-shard-*.zip" in text
    assert "mcp-collected-raw-factory-input-v1.zip.part-*" in text
    assert "--require-raw-factory-input" in text
    assert "fecb5469bfd792ac0144587287dd04b29bad73f61abb6abd913ccb437f2ac629" in text
