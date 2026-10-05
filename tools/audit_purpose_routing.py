#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

profiles = json.loads(
    (ROOT / "config/source_payload_profiles.json").read_text(encoding="utf-8")
)
contract = json.loads(
    (ROOT / "config/purpose_routing_contract.json").read_text(encoding="utf-8")
)

sources = profiles["sources"]
expected = int(profiles["expected_source_count"])
roles = contract["roles"]

declared = sorted({
    role
    for source in sources
    for role in source.get("source_roles", [])
})

unknown = sorted(set(declared) - set(roles))
unused = sorted(set(roles) - set(declared))

rows = []
counts = Counter()

for source in sorted(sources, key=lambda x: x["source_id"]):
    for role in sorted(source.get("source_roles", [])):
        route = roles.get(role)
        if route is None:
            status = "UNKNOWN_ROLE"
        elif not source.get("public_runtime_eligible"):
            status = "DISTRIBUTION_BLOCKED"
        else:
            status = "PURPOSE_DECLARED"

        counts[status] += 1
        rows.append({
            "source_id": source["source_id"],
            "source_role": role,
            "rights_lane": source["rights_lane"],
            "public_runtime_eligible": bool(source["public_runtime_eligible"]),
            "status": status,
            "consumers": (route or {}).get("consumers", []),
            "allowed": (route or {}).get("allowed", []),
            "forbidden": (route or {}).get("forbidden", [])
        })

direct = (
    ROOT / "tools/compile_direct_final_runtime.py"
).read_text(encoding="utf-8")

flattening = {
    "semantic_targets_lexicon_fixed":
        '"semantic_targets": ["lexicon"]' in direct,
    "feature_type_empty_fixed":
        '"feature_type": ""' in direct,
    "task_candidates_empty_fixed":
        '"task_candidates": []' in direct,
    "pragmatic_not_applicable":
        '"pragmatic": "not-applicable"' in direct,
    "task_not_applicable":
        '"task": "not-applicable"' in direct
}

report = {
    "source_count": len(sources),
    "expected_source_count": expected,
    "declared_role_count": len(declared),
    "declared_roles": declared,
    "unknown_roles": unknown,
    "unused_contract_roles": unused,
    "status_counts": dict(sorted(counts.items())),
    "direct_final_flattening": flattening,
    "ledger": rows
}

out = ROOT / "reports/purpose-routing"
out.mkdir(parents=True, exist_ok=True)

(out / "ledger.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8"
)

print(f"SOURCE_COUNT={len(sources)}")
print(f"EXPECTED_SOURCE_COUNT={expected}")
print(f"DECLARED_ROLE_COUNT={len(declared)}")
print(f"UNKNOWN_ROLE_COUNT={len(unknown)}")
print(f"UNUSED_CONTRACT_ROLE_COUNT={len(unused)}")
print(
    "DIRECT_FINAL_FLATTENING="
    + ("DETECTED" if any(flattening.values()) else "NONE")
)

if len(sources) != expected or unknown:
    print("OVERALL=FAIL")
    raise SystemExit(1)

print("OVERALL=BASELINE_PASS")
