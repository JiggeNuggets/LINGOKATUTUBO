"""Read-only inventory and parity analysis for Translation Resources cutover."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .resource_management import normalize_resource_value, usable_language_count
from .translation_dataset import _normalize_lookup_text


LANGUAGES = ("tagabawa", "english", "filipino", "cebuano")
CLASSIFICATIONS = (
    "valid_unique_resource",
    "exact_duplicate_after_normalization",
    "auto_split_or_generated",
    "corpus_only_phrase",
    "incomplete",
    "conflicting_translation",
    "possible_ocr_artifact",
    "unsupported_direction",
    "malformed",
    "needs_manual_review",
)


def raw_key(values: dict[str, Any]) -> tuple[str, ...]:
    """A four-language key with whitespace tidied but no match normalization."""
    return tuple(normalize_resource_value(values.get(language, "")) for language in LANGUAGES)


def normalized_key(values: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        _normalize_lookup_text(values.get(language, ""), strip_diacritics=True)
        for language in LANGUAGES
    )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_legacy_rows(project_root: Path | None = None) -> list[dict[str, Any]]:
    """Load the two legacy runtime sources without mutating either source."""
    root = project_root or _project_root()
    json_path = root / "translator" / "services" / "translation_data.json"
    csv_path = root / "datasets" / "cleaned" / "cross_lingual_cleaned_v1.csv"
    payload = json.loads(json_path.read_text(encoding="utf-8-sig"))
    json_rows = payload.get("rows", payload.get("entries", payload)) if isinstance(payload, dict) else payload
    if not isinstance(json_rows, list):
        raise ValueError("translation_data.json does not contain a list of rows.")
    rows = []
    for number, row in enumerate(json_rows, start=1):
        rows.append({
            "origin": "json", "row_number": number,
            "original_row_identifier": row.get("id", number),
            "tagabawa": row.get("tagabawa", row.get("tagabawa_source", "")),
            "english": row.get("english", row.get("english_source", "")),
            "filipino": row.get("filipino", row.get("filipino_source", row.get("tagalog", ""))),
            "cebuano": row.get("cebuano", row.get("cebuano_source", "")),
            "source": row.get("source", ""),
        })
    with csv_path.open(encoding="utf-8-sig", newline="") as source_file:
        for number, row in enumerate(csv.DictReader(source_file), start=2):
            rows.append({
                "origin": "csv", "row_number": number,
                "original_row_identifier": row.get("record_id", number),
                "tagabawa": row.get("bagobo_text", row.get("tagabawa", "")),
                "english": row.get("english_text", row.get("english", "")),
                "filipino": row.get("tagalog_text", row.get("filipino", "")),
                "cebuano": row.get("cebuano_text", row.get("cebuano", "")),
                "source": "cross_lingual_cleaned_v1.csv",
            })
    return rows


def load_database_rows() -> list[dict[str, Any]]:
    """Return active canonical records only; importing models stays lazy."""
    from translator.models import PhrasebookEntry

    return [
        {
            "origin": "database", "row_number": entry.pk,
            "original_row_identifier": entry.pk,
            "tagabawa": entry.tagabawa, "english": entry.english,
            "filipino": entry.filipino, "cebuano": entry.cebuano,
            "source": entry.source,
        }
        for entry in PhrasebookEntry.objects.filter(is_active=True).order_by("pk")
    ]


def _groups(rows: list[dict[str, Any]], key_function) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[key_function(row)].append(row)
    return grouped


def _inventory(rows: list[dict[str, Any]]) -> dict[str, int]:
    raw_groups = _groups(rows, raw_key)
    normalized_groups = _groups(rows, normalized_key)
    return {
        "rows": len(rows),
        "unique_four_language_keys": len(raw_groups),
        "unique_normalized_keys": len(normalized_groups),
        "duplicate_rows": len(rows) - len(raw_groups),
        "duplicate_key_groups": sum(1 for group in raw_groups.values() if len(group) > 1),
        "duplicate_normalized_rows": len(rows) - len(normalized_groups),
        "duplicate_normalized_key_groups": sum(1 for group in normalized_groups.values() if len(group) > 1),
    }


def _looks_malformed(values: dict[str, Any]) -> bool:
    joined = " ".join(normalize_resource_value(values.get(language, "")) for language in LANGUAGES)
    return not joined or "\ufffd" in joined or bool(re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", joined))


def _looks_generated(values: dict[str, Any]) -> bool:
    joined = " ".join(normalize_resource_value(values.get(language, "")) for language in LANGUAGES)
    return bool(re.search(r"(?:_{3,}|\[unknown|unknown_for_review|\[\?\])", joined, re.IGNORECASE))


def _looks_ocr_artifact(values: dict[str, Any]) -> bool:
    joined = " ".join(normalize_resource_value(values.get(language, "")) for language in LANGUAGES)
    return bool(re.search(r"(?:\b[Il1]{5,}\b|\b[O0]{5,}\b|[^\w\s]{5,})", joined, re.UNICODE))


def _shared_term_conflicts(values: dict[str, Any], database_term_index) -> set[tuple[str, ...]]:
    candidates: set[tuple[str, ...]] = set()
    for language in LANGUAGES:
        term = _normalize_lookup_text(values.get(language, ""), strip_diacritics=True)
        if term:
            candidates.update(database_term_index[(language, term)])
    candidates.discard(normalized_key(values))
    return candidates


def classify_legacy_only(legacy_only_groups, database_groups) -> list[dict[str, Any]]:
    """Conservative structural classification; never asserts linguistic quality."""
    database_term_index: dict[tuple[str, str], set[tuple[str, ...]]] = defaultdict(set)
    for database_key in database_groups:
        for language, term in zip(LANGUAGES, database_key):
            if term:
                database_term_index[(language, term)].add(database_key)
    classifications = []
    for key, rows in legacy_only_groups.items():
        sample = rows[0]
        values = {language: sample.get(language, "") for language in LANGUAGES}
        origins = sorted({row["origin"] for row in rows})
        shared_conflicts = _shared_term_conflicts(values, database_term_index)
        if _looks_malformed(values):
            classification, recommendation, reason = "malformed", "EXCLUDE", "No usable text or invalid control/replacement characters."
        elif usable_language_count(values) < 2:
            classification, recommendation, reason = "incomplete", "MANUAL_REVIEW_REQUIRED", "Fewer than two usable language values."
        elif _looks_generated(values):
            classification, recommendation, reason = "auto_split_or_generated", "EXCLUDE", "Contains generated placeholder or split-marker text."
        elif _looks_ocr_artifact(values):
            classification, recommendation, reason = "possible_ocr_artifact", "MANUAL_REVIEW_REQUIRED", "Contains a structural OCR-artifact pattern."
        elif shared_conflicts:
            classification, recommendation, reason = "conflicting_translation", "MANUAL_REVIEW_REQUIRED", "Shares one or more normalized language terms with a differently keyed database record."
        elif origins == ["csv"]:
            classification, recommendation, reason = "corpus_only_phrase", "KEEP_LEGACY_ONLY", "Present only in the cleaned legacy corpus; no validation or migration decision is implied."
        elif len(origins) > 1:
            classification, recommendation, reason = "needs_manual_review", "MANUAL_REVIEW_REQUIRED", "Appears in multiple sources but has no canonical database key."
        else:
            classification, recommendation, reason = "valid_unique_resource", "IMPORT_CANDIDATE", "Structurally complete, unique, and without a detected database-term conflict."
        staging_status = {
            "malformed": "POSSIBLE_OCR_ARTIFACT",
            "incomplete": "INCOMPLETE",
            "auto_split_or_generated": "POSSIBLE_OCR_ARTIFACT",
            "possible_ocr_artifact": "POSSIBLE_OCR_ARTIFACT",
            "conflicting_translation": "CONFLICT",
        }.get(classification, "READY_FOR_ADMIN_REVIEW")
        classifications.append({
            "key": key, "origins": origins, "row_count": len(rows),
            "classification": classification, "recommendation": recommendation,
            "reason": reason, "shared_database_key_count": len(shared_conflicts),
            "conflict_database_keys": [list(value) for value in sorted(shared_conflicts)],
            "staging_status": staging_status,
            "source_files": sorted({
                "translation_data.json" if row["origin"] == "json" else "cross_lingual_cleaned_v1.csv"
                for row in rows
            }),
            "original_row_identifiers": [row.get("original_row_identifier") for row in rows],
            "values": values,
            "completeness": usable_language_count(values),
            "normalized_key": list(key),
            "duplicate_status": "unique_normalized_legacy_key",
            "conflict_status": bool(shared_conflicts),
            "character_anomaly_status": _looks_ocr_artifact(values) or _looks_malformed(values),
            "phrase_length_words": max(
                (len(normalize_resource_value(values.get(language, "")).split()) for language in LANGUAGES),
                default=0,
            ),
            "current_legacy_runtime_usable": usable_language_count(values) >= 2,
        })
    return classifications


def analyze_resource_inventory() -> dict[str, Any]:
    legacy_rows = load_legacy_rows()
    database_rows = load_database_rows()
    json_rows = [row for row in legacy_rows if row["origin"] == "json"]
    csv_rows = [row for row in legacy_rows if row["origin"] == "csv"]
    legacy_groups = _groups(legacy_rows, normalized_key)
    database_groups = _groups(database_rows, normalized_key)
    overlap = set(legacy_groups).intersection(database_groups)
    legacy_only = {key: legacy_groups[key] for key in set(legacy_groups).difference(database_groups)}
    database_only = {key: database_groups[key] for key in set(database_groups).difference(legacy_groups)}
    classifications = classify_legacy_only(legacy_only, database_groups)
    counts = Counter(item["classification"] for item in classifications)
    recommendations = Counter(item["recommendation"] for item in classifications)
    conflict_count = sum(1 for item in classifications if item["classification"] == "conflicting_translation")
    return {
        "json": _inventory(json_rows), "csv": _inventory(csv_rows),
        "legacy": _inventory(legacy_rows), "database": _inventory(database_rows),
        "overlap_unique_normalized_keys": len(overlap),
        "legacy_only_unique_normalized_keys": len(legacy_only),
        "database_only_unique_normalized_keys": len(database_only),
        "conflicting_legacy_only_keys": conflict_count,
        "classification_summary": dict(sorted(counts.items())),
        "recommendation_summary": dict(sorted(recommendations.items())),
        "legacy_only": classifications,
        "database_only": [{"key": key, "row_count": len(rows)} for key, rows in database_only.items()],
    }


def staging_summary(report: dict[str, Any] | None = None) -> dict[str, int]:
    report = report or analyze_resource_inventory()
    statuses = Counter(item["staging_status"] for item in report["legacy_only"])
    return {
        "legacy_only": report["legacy_only_unique_normalized_keys"],
        "ready_for_admin_review": statuses["READY_FOR_ADMIN_REVIEW"],
        "incomplete": statuses["INCOMPLETE"],
        "possible_duplicate": statuses["POSSIBLE_DUPLICATE"],
        "conflict": statuses["CONFLICT"],
        "possible_ocr_artifact": statuses["POSSIBLE_OCR_ARTIFACT"],
        "manual_language_review": statuses["MANUAL_LANGUAGE_REVIEW"],
    }


def _first_usable(rows, source_language: str, target_language: str, predicate=None):
    predicate = predicate or (lambda value: True)
    for row in rows:
        source = normalize_resource_value(row.get(source_language, ""))
        target = normalize_resource_value(row.get(target_language, ""))
        if source and target and predicate(source):
            return row
    return None


def _mutate_for_fuzzy(text: str) -> str:
    """A small deterministic spelling change, never a generated translation."""
    if len(text) < 6:
        return text + "x"
    index = max(1, len(text) // 2)
    replacement = "x" if text[index].lower() != "x" else "z"
    return text[:index] + replacement + text[index + 1:]


def run_matching_parity_matrix() -> list[dict[str, Any]]:
    """Compare controlled inputs against the two real runtime modes, read-only."""
    from .translation_dataset import TranslationDataset

    report = analyze_resource_inventory()
    database_rows = load_database_rows()
    legacy_only = report["legacy_only"]
    legacy = TranslationDataset(data_mode="development_unverified")
    database = TranslationDataset(data_mode="development_resources")
    cases = []

    def add_case(name, text, source, target, expected_difference=False, reason="Shared-resource parity expected."):
        legacy_result = legacy.translate_phrase_with_metadata(text, source, target)
        database_result = database.translate_phrase_with_metadata(text, source, target)
        comparable = (legacy_result.get("translated"), legacy_result.get("method")) == (
            database_result.get("translated"), database_result.get("method")
        )
        cases.append({
            "case": name, "input": text, "source_language": source, "target_language": target,
            "development_unverified": {"translated": legacy_result.get("translated"), "method": legacy_result.get("method"), "similarity": legacy_result.get("match_score")},
            "development_resources": {"translated": database_result.get("translated"), "method": database_result.get("method"), "similarity": database_result.get("match_score")},
            "same_result": comparable, "expected_difference": expected_difference, "reason": reason,
        })

    exact = _first_usable(database_rows, "english", "tagabawa")
    if exact:
        source = normalize_resource_value(exact["english"])
        add_case("exact", source, "english", "tagabawa")
        add_case("normalized_case_punctuation_whitespace", f"  {source.upper()}!  ", "english", "tagabawa")
    phrase = _first_usable(database_rows, "english", "tagabawa", lambda value: len(value.split()) >= 2)
    if phrase:
        add_case("multi_word_phrase", normalize_resource_value(phrase["english"]), "english", "tagabawa")
    fuzzy_source = _first_usable(
        database_rows, "english", "tagabawa",
        lambda value: len(re.sub(r"\s+", "", value)) >= 12,
    )
    if fuzzy_source:
        add_case("fuzzy", _mutate_for_fuzzy(normalize_resource_value(fuzzy_source["english"])), "english", "tagabawa")
    short = _first_usable(database_rows, "english", "tagabawa", lambda value: 1 < len(value) <= 4 and value.isalpha())
    if short:
        add_case("short_word_fuzzy_rejection", normalize_resource_value(short["english"]) + "x", "english", "tagabawa")
    alias = _first_usable(database_rows, "filipino", "cebuano")
    if alias:
        add_case("tagalog_bisaya_aliases", normalize_resource_value(alias["filipino"]), "tagalog", "bisaya")
    reverse = _first_usable(database_rows, "tagabawa", "english")
    if reverse:
        add_case("bagobo_tagabawa_to_english", normalize_resource_value(reverse["tagabawa"]), "bagobo-tagabawa", "english")
    if exact and phrase and normalize_resource_value(exact["english"]) != normalize_resource_value(phrase["english"]):
        add_case("segmented", f"{normalize_resource_value(exact['english'])}. {normalize_resource_value(phrase['english'])}", "english", "tagabawa")
    add_case("unknown_source_preserved", "LingoKatutuboParityAbsentTerm", "english", "tagabawa")
    if legacy_only:
        conflict = next((row for row in legacy_only if row["classification"] == "conflicting_translation"), legacy_only[0])
        values = dict(zip(LANGUAGES, conflict["key"]))
        if values["english"] and values["tagabawa"]:
            add_case(
                "legacy_only_expected_difference", values["english"], "english", "tagabawa", True,
                "Legacy-only resource is intentionally absent from development_resources pending review/import.",
            )
    return cases
