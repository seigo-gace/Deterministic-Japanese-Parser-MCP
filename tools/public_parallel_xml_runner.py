#!/usr/bin/env python3
"""Run the existing NICT parallel normalizer with auditable XML repair.

The original source tarball is never modified. Strict ElementTree parsing is tried
first. Only XML 1.0-forbidden code points or a bare ampersand exactly at the parser
error position may be repaired in memory. Every repair records archive member,
source payload SHA-256, repaired payload SHA-256, position, context and original
code point. Any other parse error remains fail-closed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tarfile
from typing import Any
import xml.etree.ElementTree as ET

import public_parallel_sources as parallel

REPORT_PATH = Path("reports/public-parallel-xml-repairs.json")
ORIGINAL_FROMSTRING = ET.fromstring
ORIGINAL_EXTRACTFILE = tarfile.TarFile.extractfile
PAYLOAD_MEMBERS: dict[str, str] = {}
REPAIRS: list[dict[str, Any]] = []
FAILURES: list[dict[str, Any]] = []


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def xml10_allowed(codepoint: int) -> bool:
    return (
        codepoint in (0x09, 0x0A, 0x0D)
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


def absolute_index(text: str, line: int, column: int) -> int | None:
    if line <= 0 or column < 0:
        return None
    lines = text.splitlines(keepends=True)
    if line > len(lines):
        return None
    current = lines[line - 1]
    if column >= len(current):
        return None
    return sum(len(value) for value in lines[: line - 1]) + column


def context_for(text: str, index: int | None, radius: int = 80) -> str:
    if index is None:
        return ""
    start = max(0, index - radius)
    end = min(len(text), index + radius + 1)
    return text[start:end].replace("\r", "\\r").replace("\n", "\\n")


class RecordingReader:
    def __init__(self, handle: Any, member_name: str) -> None:
        self._handle = handle
        self._member_name = member_name

    def read(self, *args: Any, **kwargs: Any) -> Any:
        value = self._handle.read(*args, **kwargs)
        full_read = not args or args[0] in (-1, None)
        if (
            full_read
            and isinstance(value, (bytes, bytearray))
            and self._member_name.casefold().endswith(".xml")
        ):
            PAYLOAD_MEMBERS[sha256_bytes(bytes(value))] = self._member_name
        return value

    def __enter__(self) -> "RecordingReader":
        return self

    def __exit__(self, *args: Any) -> Any:
        return self._handle.__exit__(*args) if hasattr(self._handle, "__exit__") else None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._handle, name)


def recording_extractfile(self: tarfile.TarFile, member: Any) -> Any:
    handle = ORIGINAL_EXTRACTFILE(self, member)
    if handle is None:
        return None
    member_name = member.name if hasattr(member, "name") else str(member)
    return RecordingReader(handle, member_name)


def safe_fromstring(payload: Any, parser: Any = None) -> ET.Element:
    try:
        return ORIGINAL_FROMSTRING(payload, parser=parser)
    except ET.ParseError as first_error:
        if not isinstance(payload, (bytes, bytearray)):
            raise
        raw = bytes(payload)
        raw_sha = sha256_bytes(raw)
        member = PAYLOAD_MEMBERS.get(raw_sha, "<unmapped-xml-member>")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as decode_error:
            failure = {
                "archive_member": member,
                "source_payload_sha256": raw_sha,
                "parse_error": str(first_error),
                "repair_status": "FAILED_UNSUPPORTED_ENCODING_ERROR",
                "decode_error": str(decode_error),
            }
            FAILURES.append(failure)
            raise RuntimeError(f"unsupported Kyoto XML encoding error: {failure}") from first_error

        line, column = getattr(first_error, "position", (0, 0))
        error_index = absolute_index(text, int(line), int(column))
        replacements: list[dict[str, Any]] = []
        repaired_chars = list(text)

        forbidden_indexes = [
            index for index, char in enumerate(text) if not xml10_allowed(ord(char))
        ]
        if forbidden_indexes:
            for index in forbidden_indexes:
                char = text[index]
                replacements.append(
                    {
                        "kind": "xml10_forbidden_codepoint",
                        "absolute_character_index": index,
                        "codepoint": f"U+{ord(char):04X}",
                        "replacement": "U+FFFD",
                        "context": context_for(text, index),
                    }
                )
                repaired_chars[index] = "\ufffd"
            repaired_text = "".join(repaired_chars)
        elif error_index is not None and text[error_index] == "&":
            tail = text[error_index : error_index + 64]
            if re.match(r"^&(amp|lt|gt|apos|quot|#[0-9]+|#x[0-9A-Fa-f]+);", tail):
                failure = {
                    "archive_member": member,
                    "source_payload_sha256": raw_sha,
                    "parse_error": str(first_error),
                    "repair_status": "FAILED_ENTITY_WAS_ALREADY_WELL_FORMED",
                    "line": line,
                    "column": column,
                    "context": context_for(text, error_index),
                }
                FAILURES.append(failure)
                raise RuntimeError(f"unsupported Kyoto XML parse error: {failure}") from first_error
            replacements.append(
                {
                    "kind": "bare_ampersand",
                    "absolute_character_index": error_index,
                    "codepoint": "U+0026",
                    "replacement": "&amp;",
                    "context": context_for(text, error_index),
                }
            )
            repaired_text = text[:error_index] + "&amp;" + text[error_index + 1 :]
        else:
            failure = {
                "archive_member": member,
                "source_payload_sha256": raw_sha,
                "parse_error": str(first_error),
                "repair_status": "FAILED_UNSUPPORTED_PARSE_ERROR",
                "line": line,
                "column": column,
                "error_codepoint": (
                    f"U+{ord(text[error_index]):04X}" if error_index is not None else ""
                ),
                "context": context_for(text, error_index),
            }
            FAILURES.append(failure)
            raise RuntimeError(f"unsupported Kyoto XML parse error: {failure}") from first_error

        repaired_payload = repaired_text.encode("utf-8")
        try:
            root = ORIGINAL_FROMSTRING(repaired_payload, parser=parser)
        except ET.ParseError as second_error:
            failure = {
                "archive_member": member,
                "source_payload_sha256": raw_sha,
                "repaired_payload_sha256": sha256_bytes(repaired_payload),
                "parse_error": str(first_error),
                "repair_parse_error": str(second_error),
                "repair_status": "FAILED_AFTER_ALLOWLISTED_REPAIR",
                "line": line,
                "column": column,
                "replacements": replacements,
            }
            FAILURES.append(failure)
            raise RuntimeError(f"Kyoto XML still invalid after allowlisted repair: {failure}") from second_error

        REPAIRS.append(
            {
                "archive_member": member,
                "source_payload_sha256": raw_sha,
                "repaired_payload_sha256": sha256_bytes(repaired_payload),
                "parse_error": str(first_error),
                "line": line,
                "column": column,
                "repair_status": "REPAIRED_IN_MEMORY",
                "replacements": replacements,
            }
        )
        return root


def write_repair_report() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "status": "FAILURE" if FAILURES else ("REPAIRED" if REPAIRS else "NO_REPAIR_REQUIRED"),
        "repair_count": len(REPAIRS),
        "failed_repairs": len(FAILURES),
        "source_archive_modified": False,
        "allowed_repair_kinds": ["xml10_forbidden_codepoint", "bare_ampersand"],
        "repairs": REPAIRS,
        "failures": FAILURES,
    }
    REPORT_PATH.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    tarfile.TarFile.extractfile = recording_extractfile
    ET.fromstring = safe_fromstring
    try:
        return parallel.main()
    finally:
        write_repair_report()


if __name__ == "__main__":
    raise SystemExit(main())
