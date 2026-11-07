"""Read-only, file-backed T06 matching evaluation. No ORM queries or imports."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from django.core.management.base import BaseCommand, CommandError

from translator.services.translation_dataset import (
    SUPPORTED_LANGS, TranslationDataset, _has_conflict, _first_result,
)


class Command(BaseCommand):
    help = "Evaluate reproducible matching against existing files; no claim of linguistic accuracy."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)
        parser.add_argument("--limit-per-direction", type=int, default=25)

    def handle(self, *args, **options):
        limit = options["limit_per_direction"]
        if limit < 1:
            raise CommandError("limit-per-direction must be positive")
        with patch("translator.services.translation_dataset.safe_print"):
            data = TranslationDataset(data_mode="development_unverified")
        if not data.is_loaded:
            raise CommandError("File-backed language resources are unavailable")
        root = Path(__file__).resolve().parents[3]
        sources = [Path(data.dataset_path), root / "datasets/cleaned/cross_lingual_cleaned_v1.csv"]
        sources += sorted((root / "datasets/validated").glob("*.csv"))
        output = Path(options["output"])
        if output.resolve() in {path.resolve() for path in sources}:
            raise CommandError("The evaluation report must not overwrite a language resource")
        cases, directions = [], {}
        with patch("translator.services.translation_dataset.safe_print"):
            for source in SUPPORTED_LANGS:
                for target in SUPPORTED_LANGS:
                    if source == target:
                        continue
                    direction = f"{source}->{target}"
                    index = data._phrase_indices[source]
                    target_key = f"{target}_source"
                    # Raw, case-insensitive source buckets; normalized collisions
                    # are additionally guarded by the actual lookup.
                    raw_keys = sorted({r[f"{source}_source"].strip().lower() for r in data.data
                                       if r.get(f"{source}_source") and r.get(target_key)})
                    conflict_keys = [key for key in raw_keys if _has_conflict(index.get(key, []), target_key)]
                    unique_keys = [key for key in raw_keys if not _has_conflict(index.get(key, []), target_key)
                                   and not key.endswith((".", "?", "!", ","))]
                    exact_cases = []
                    for key in unique_keys[:limit]:
                        expected, row = _first_result(index[key], target_key)
                        result = data.translate_phrase_with_metadata(key, source, target)
                        case = {
                            "id": f"{direction}:{row.get('id', key)}",
                            "source_text": key, "source_language": source, "target_language": target,
                            "expected_text": expected, "entry_id": row.get("id"),
                            "reference_validated": False, "kind": "exact",
                            "passed": result["translated"] == expected and result["match_method"] == "exact"
                                      and result["review_required"],
                        }
                        exact_cases.append(case)
                    cases.extend(exact_cases)
                    conflict_passed = 0
                    for key in conflict_keys:
                        result = data.translate_phrase_with_metadata(key, source, target)
                        conflict_passed += (result["translated"] == key and result["review_required"]
                                            and result["match_method"] == "unknown")
                    original = "T06 qzxvkj untranslated 981723."
                    unknown = data.translate_phrase_with_metadata(original, source, target)
                    directions[direction] = {
                        "rows_with_both_languages": sum(bool(r.get(f"{source}_source") and r.get(target_key)) for r in data.data),
                        "distinct_source_keys": len(raw_keys), "conflicting_source_keys": len(conflict_keys),
                        "conflicts_safely_retained": conflict_passed,
                        "exact_cases": len(exact_cases), "exact_passed": sum(c["passed"] for c in exact_cases),
                        "unknown_preserved_and_flagged": unknown["translated"] == original and unknown["review_required"],
                    }
        report = {
            "purpose": "Automated resource matching correctness; not linguistic or cultural accuracy.",
            "mode": data.data_mode, "loaded_rows": len(data.data),
            "row_sources": dict(Counter(r.get("source", "legacy_json") for r in data.data)),
            "sources": [{"path": str(p.relative_to(root)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                        for p in sources if p.is_file()],
            "sme_validated_reference_count": 0, "linguistic_accuracy": None,
            "limit_per_direction": limit, "directions": directions,
            "exact_case_count": len(cases), "exact_passed": sum(c["passed"] for c in cases),
            "cases": cases,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(f"Matching evaluation: {report['exact_passed']}/{len(cases)} exact cases; report {output}")
        if not all(d["exact_cases"] and d["exact_cases"] == d["exact_passed"]
                   and d["conflicting_source_keys"] == d["conflicts_safely_retained"]
                   and d["unknown_preserved_and_flagged"] for d in directions.values()):
            raise CommandError("Matching evaluation contains failures; see report")
