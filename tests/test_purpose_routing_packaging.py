from __future__ import annotations

from pathlib import Path
import tomllib

from deterministic_japanese_parser_mcp import purpose_routing


ROOT = Path(__file__).resolve().parents[1]


def test_source_purpose_routing_config_is_available():
    assert purpose_routing.CONTRACT.is_file()
    assert (purpose_routing.CONFIG_ROOT / "source_payload_profiles.json").is_file()
    contract = purpose_routing.load_purpose_contract()
    assert isinstance(contract.get("roles"), dict)
    assert contract["roles"]


def test_runtime_routing_config_is_declared_as_installed_data():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    data_files = data["tool"]["setuptools"]["data-files"]
    config_files = data_files["share/deterministic-japanese-parser-mcp/config"]
    assert "config/purpose_routing_contract.json" in config_files
    assert "config/source_payload_profiles.json" in config_files
