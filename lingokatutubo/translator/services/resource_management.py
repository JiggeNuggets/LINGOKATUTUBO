"""Non-destructive helpers for the administrator Translation Resources UI."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from typing import Any, Iterable

from .translation_dataset import _normalize_lang, _normalize_lookup_text


LANGUAGE_FIELDS = ("tagabawa", "english", "filipino", "cebuano")
RESOURCE_FIELDS = LANGUAGE_FIELDS + ("part_of_speech", "topic", "source", "notes", "is_active")
_COLUMN_ALIASES = {
    "bagobo": "tagabawa", "bagobo tagabawa": "tagabawa", "bagobo-tagabawa": "tagabawa",
    "tagabawa": "tagabawa", "bgs": "tagabawa",
    "english": "english", "en": "english", "eng": "english",
    "filipino": "filipino", "tagalog": "filipino", "fil": "filipino", "tgl": "filipino",
    "cebuano": "cebuano", "bisaya": "cebuano", "ceb": "cebuano",
    "entry type": "part_of_speech", "entry_type": "part_of_speech", "type": "part_of_speech",
    "category": "topic", "topic": "topic", "source": "source", "notes": "notes",
    "active": "is_active", "is active": "is_active", "is_active": "is_active",
}


def normalize_resource_value(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalized_entry_key(values: dict[str, Any]) -> tuple[str, ...]:
    return tuple(_normalize_lookup_text(values.get(field, ""), strip_diacritics=True) for field in LANGUAGE_FIELDS)


def exact_entry_key(values: dict[str, Any]) -> tuple[str, ...]:
    return tuple(normalize_resource_value(values.get(field, "")) for field in LANGUAGE_FIELDS)


def usable_language_count(values: dict[str, Any]) -> int:
    return sum(bool(normalize_resource_value(values.get(field, ""))) for field in LANGUAGE_FIELDS)


def resource_values(entry) -> dict[str, Any]:
    return {field: getattr(entry, field) for field in RESOURCE_FIELDS}


def duplicate_report(values: dict[str, Any], entries: Iterable, *, exclude_id=None) -> dict[str, list]:
    """Return matching entries without changing records or resolving conflicts."""
    exact_key = exact_entry_key(values)
    normalized_key = normalized_entry_key(values)
    source_terms = {
        _normalize_lookup_text(values.get(field, ""), strip_diacritics=True)
        for field in LANGUAGE_FIELDS
        if normalize_resource_value(values.get(field, ""))
    }
    exact, normalized, conflicts = [], [], []
    for entry in entries:
        if exclude_id is not None and entry.pk == exclude_id:
            continue
        current = resource_values(entry)
        if exact_entry_key(current) == exact_key:
            exact.append(entry)
            continue
        if normalized_entry_key(current) == normalized_key:
            normalized.append(entry)
            continue
        current_terms = {
            _normalize_lookup_text(current.get(field, ""), strip_diacritics=True)
            for field in LANGUAGE_FIELDS
            if normalize_resource_value(current.get(field, ""))
        }
        # A shared source term with a differing multilingual record is a warning,
        # never an automatic replacement.
        if source_terms.intersection(current_terms) and normalized_entry_key(current) != normalized_key:
            conflicts.append(entry)
    return {"exact": exact, "normalized": normalized, "conflicts": conflicts}


def _canonical_column(name: Any) -> str | None:
    raw = " ".join(str(name or "").strip().lower().replace("_", " ").split())
    if raw in _COLUMN_ALIASES:
        return _COLUMN_ALIASES[raw]
    language = _normalize_lang(raw)
    return language if language in LANGUAGE_FIELDS else None


def _active_value(value: Any) -> bool:
    return str(value or "").strip().lower() not in {"0", "false", "no", "inactive", "off"}


def parse_resource_upload(name: str, content: bytes) -> list[dict[str, Any]]:
    """Parse a CSV/JSON upload into UI fields. Does not write to disk or DB."""
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix == "csv":
        raw_rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    elif suffix == "json":
        payload = json.loads(content.decode("utf-8-sig"))
        raw_rows = payload.get("rows", payload.get("entries", payload)) if isinstance(payload, dict) else payload
        if not isinstance(raw_rows, list):
            raise ValueError("JSON must contain a list or a rows/entries list.")
    else:
        raise ValueError("Upload a CSV or JSON resource file.")
    if len(raw_rows) > 2_000:
        raise ValueError("Imports are limited to 2,000 rows at a time.")
    rows = []
    for number, raw in enumerate(raw_rows, start=2):
        if not isinstance(raw, dict):
            rows.append({"row_number": number, "values": {}, "status": "invalid", "reason": "Row is not an object."})
            continue
        values = {field: "" for field in RESOURCE_FIELDS}
        values["source"] = "translation_resources_import"
        values["is_active"] = True
        for column, value in raw.items():
            field = _canonical_column(column)
            if field:
                values[field] = _active_value(value) if field == "is_active" else normalize_resource_value(value)
        status = "ready" if usable_language_count(values) >= 2 else "invalid"
        rows.append({
            "row_number": number,
            "values": values,
            "status": status,
            "reason": "" if status == "ready" else "At least two language values are required.",
        })
    return rows


def build_import_preview(name: str, content: bytes, entries: Iterable) -> dict[str, Any]:
    """Classify import rows for a confirmation screen without persistent changes."""
    rows = parse_resource_upload(name, content)
    existing = list(entries)
    seen_exact: set[tuple[str, ...]] = set()
    summary = {"processed": len(rows), "ready": 0, "duplicates": 0, "conflicts": 0, "invalid": 0}
    for item in rows:
        if item["status"] == "invalid":
            summary["invalid"] += 1
            continue
        key = exact_entry_key(item["values"])
        report = duplicate_report(item["values"], existing)
        if key in seen_exact or report["exact"]:
            item.update(status="duplicate", reason="A matching resource already exists.")
            summary["duplicates"] += 1
        elif report["normalized"]:
            item.update(status="normalized_duplicate", reason="A normalized matching resource already exists.")
            summary["duplicates"] += 1
        elif report["conflicts"]:
            item.update(status="conflict", reason="A related term has a different translation.")
            summary["conflicts"] += 1
        else:
            seen_exact.add(key)
            summary["ready"] += 1
    return {
        "source_name": name,
        "checksum": hashlib.sha256(content).hexdigest(),
        "rows": rows,
        "summary": summary,
    }
