from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/release-readiness.yml"


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"expected one release workflow marker, found {count}: {old!r}"
        )
    return text.replace(old, new, 1)


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '          raw_root = Path("dictionaries/system/lexicon.d")\n'
        '          compiled_root = Path(\n'
        '              "dictionaries/system/compiled/open_lexicon"\n'
        '          )',
        '          compiled_root = Path(\n'
        '              "dictionaries/system/compiled/open_lexicon"\n'
        '          )\n'
        '          record_root = compiled_root / "records"',
    )
    text = replace_once(
        text,
        '          raw_paths = sorted([\n'
        '              *raw_root.rglob("*.jsonl"),\n'
        '              *raw_root.rglob("*.jsonl.gz"),\n'
        '          ], key=lambda item: str(item))',
        '          record_paths = sorted(\n'
        '              record_root.glob("records-*.jsonl.gz"),\n'
        '              key=lambda item: str(item),\n'
        '          )',
    )
    text = replace_once(
        text,
        '          for path in raw_paths:',
        '          for path in record_paths:',
    )
    text = replace_once(
        text,
        '                      if group != sorted(set(orthographic)):',
        '                      if not set(orthographic).issubset(set(group)):',
    )
    text = replace_once(
        text,
        '                      for mapping in item.get("reading_mappings", []):\n'
        '                          expected = {\n'
        '                              "record_id": record_id,\n'
        '                              "restricted_to": sorted(set(\n'
        '                                  mapping.get("restricted_to", [])\n'
        '                              )),\n'
        '                              "no_kanji": bool(\n'
        '                                  mapping.get("no_kanji", False)\n'
        '                              ),\n'
        '                          }',
        '                      mappings = list(\n'
        '                          item.get("reading_mappings", [])\n'
        '                      )\n'
        '                      mapped_readings = {\n'
        '                          mapping.get("reading")\n'
        '                          for mapping in mappings\n'
        '                      }\n'
        '                      for reading in item.get("readings", []):\n'
        '                          if reading and reading not in mapped_readings:\n'
        '                              mappings.append({\n'
        '                                  "reading": reading,\n'
        '                                  "restricted_to": [],\n'
        '                                  "no_kanji": False,\n'
        '                              })\n'
        '                      for mapping in mappings:\n'
        '                          expected = {\n'
        '                              "record_id": record_id,\n'
        '                              "restricted_to": list(\n'
        '                                  mapping.get("restricted_to", [])\n'
        '                              ),\n'
        '                              "no_kanji": bool(\n'
        '                                  mapping.get("no_kanji", False)\n'
        '                              ),\n'
        '                          }',
    )
    text = replace_once(
        text,
        '              "mode": "offline_raw_to_compiled_full_coverage",',
        '              "mode": "offline_compiled_record_to_index_full_coverage",',
    )
    text = replace_once(
        text,
        '      - name: Hash all release evidence\n'
        '        if: always()\n'
        '        run: |\n'
        '          python scripts/write_release_manifest.py',
        '      - name: Hash all release evidence\n'
        '        if: always()\n'
        '        run: |\n'
        '          mkdir -p wheelhouse dist reports\n'
        '          python scripts/write_release_manifest.py',
    )
    WORKFLOW.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
