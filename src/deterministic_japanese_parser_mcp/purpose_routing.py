from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "config/purpose_routing_contract.json"

@lru_cache(maxsize=1)
def load_purpose_contract() -> dict[str, Any]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))

def routes_for_roles(source_roles: list[str]) -> dict[str, Any]:
    contract = load_purpose_contract()
    roles = contract["roles"]

    consumers: set[str] = set()
    allowed: set[str] = set()
    forbidden: set[str] = set()
    unknown: list[str] = []

    for role in sorted(set(source_roles)):
        spec = roles.get(role)
        if spec is None:
            unknown.append(role)
            continue
        consumers.update(spec["consumers"])
        allowed.update(spec["allowed"])
        forbidden.update(spec["forbidden"])

    return {
        "source_roles": sorted(set(source_roles)),
        "consumers": sorted(consumers),
        "allowed": sorted(allowed),
        "forbidden": sorted(forbidden),
        "unknown_roles": unknown,
        "routing_valid": not unknown,
    }

def semantic_targets_for_roles(source_roles: list[str]) -> list[str]:
    mapping = {
        "lexical-definition": "lexicon",
        "semantic-class": "lexicon",
        "lexical-relation": "lexicon",
        "pragmatics": "language_feature",
        "usage": "language_feature",
        "sentiment": "language_feature",
        "entity": "language_feature",
    }

    targets = {
        mapping[role]
        for role in source_roles
        if role in mapping
    }

    return sorted(targets or {"lexicon"})

@lru_cache(maxsize=1)
def load_dataset_roles() -> dict[str, list[str]]:
    path = ROOT / "config/source_payload_profiles.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(row["source_id"]): sorted(set(row.get("source_roles", [])))
        for row in data["sources"]
    }

def routes_for_datasets(source_datasets: list[str]) -> dict[str, Any]:
    role_map = load_dataset_roles()
    unknown_datasets = sorted({
        str(dataset)
        for dataset in source_datasets
        if str(dataset) not in role_map
    })
    source_roles = sorted({
        role
        for dataset in source_datasets
        for role in role_map.get(str(dataset), [])
    })
    result = routes_for_roles(source_roles)
    result["source_datasets"] = sorted(set(map(str, source_datasets)))
    result["unknown_datasets"] = unknown_datasets
    result["routing_valid"] = (
        result["routing_valid"] and not unknown_datasets
    )
    return result

def purpose_role_bits() -> dict[str, int]:
    roles = sorted(load_purpose_contract()["roles"])
    return {name: 1 << i for i, name in enumerate(roles)}

def role_mask_for_datasets(source_datasets: list[str]) -> int:
    route = routes_for_datasets(source_datasets)
    if not route["routing_valid"]:
        raise ValueError(
            f"unroutable datasets={route['unknown_datasets']} "
            f"roles={route['unknown_roles']}"
        )
    bits = purpose_role_bits()
    return sum(bits[x] for x in route["source_roles"])
