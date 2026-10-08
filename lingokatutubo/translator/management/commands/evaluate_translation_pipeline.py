"""Reproducible Phase 3 technical translation-pipeline evaluation."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from translator.models import TranslationJob, TranslationSegment
from translator.services.translation_dataset import TranslationDataset


class Command(BaseCommand):
    help = "Evaluate technical phrasebook matching; it does not claim linguistic translation accuracy."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", required=True, help="Authorized JSON or CSV evaluation fixture")
        parser.add_argument("--source-language", default="english")
        parser.add_argument("--target-language", default="tagabawa")
        parser.add_argument("--output", required=True, help="JSON report path (a .txt summary is also created)")
        parser.add_argument("--include-layout", action="store_true")
        parser.add_argument("--include-ocr", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dataset_path = Path(options["dataset"])
        if not dataset_path.is_file():
            raise CommandError(f"Evaluation dataset not found: {dataset_path}")
        cases = self._load_cases(dataset_path)
        if not cases:
            raise CommandError("Evaluation dataset contains no cases.")
        if options["dry_run"]:
            self.stdout.write(f"Dry run: {len(cases)} authorized evaluation case(s) would be evaluated.")
            return

        engine = TranslationDataset(data_mode="development_unverified")
        started = time.perf_counter()
        counts = {key: 0 for key in ("exact", "normalized", "fuzzy", "segmented", "unknown", "source_retained", "machine_suggestion")}
        exact_expected = normalized_expected = 0
        validated_references = 0
        details = []
        for case in cases:
            source = str(case.get("source_text") or case.get("source") or "")
            source_language = case.get("source_language", options["source_language"])
            target_language = case.get("target_language", options["target_language"])
            result = engine.translate_phrase_with_metadata(source, source_language, target_language)
            method = result.get("match_method", "unknown")
            counts[method] = counts.get(method, 0) + 1
            expected = case.get("expected_text") or case.get("expected")
            is_validated = bool(case.get("human_reviewed") or case.get("reference_validated"))
            if expected is not None and is_validated:
                validated_references += 1
                if result.get("displayed_text", result.get("translated")) == expected:
                    exact_expected += 1
                if self._normalise(result.get("displayed_text", result.get("translated", ""))) == self._normalise(expected):
                    normalized_expected += 1
            details.append({
                "case_id": case.get("id"), "match_method": method,
                "review_required": result.get("review_required"),
                "validation_status": result.get("validation_status"),
                "reference_validated": is_validated,
            })
        elapsed = round(time.perf_counter() - started, 4)
        total = len(cases)
        report = {
            "report_type": "phase3_translation_pipeline_evaluation",
            "dataset": str(dataset_path),
            "case_count": total,
            "technical_matching": {
                "exact_match_rate": self._rate(counts["exact"], total),
                "normalized_match_rate": self._rate(counts["normalized"], total),
                "fuzzy_match_rate": self._rate(counts["fuzzy"], total),
                "segmented_match_rate": self._rate(counts["segmented"], total),
                "unknown_rate": self._rate(counts["unknown"], total),
                "counts": counts,
            },
            "linguistic_validation": {
                "validated_reference_count": validated_references,
                "exact_match_rate_on_validated_references": self._rate(exact_expected, validated_references),
                "normalized_match_rate_on_validated_references": self._rate(normalized_expected, validated_references),
                "disclaimer": "Technical matching is not linguistic translation accuracy. No rate is claimed for unvalidated reference data.",
            },
            "processing": {"processing_time_seconds": elapsed, "failed_job_rate": self._failed_job_rate()},
            "runtime_eligibility": {"data_mode": engine.data_mode, "dataset_loaded": engine.is_loaded},
            "cases": details,
        }
        if options["include_ocr"]:
            report["ocr"] = self._ocr_metrics()
        if options["include_layout"]:
            report["layout"] = self._layout_metrics()

        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = output.with_suffix(".txt")
        summary.write_text(self._summary(report), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"JSON report: {output}"))
        self.stdout.write(self.style.SUCCESS(f"Human-readable report: {summary}"))

    @staticmethod
    def _load_cases(path: Path):
        if path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as handle:
                return list(csv.DictReader(handle))
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw.get("cases", raw.get("rows", [])) if isinstance(raw, dict) else raw

    @staticmethod
    def _rate(numerator, denominator):
        return round(numerator / denominator, 4) if denominator else None

    @staticmethod
    def _normalise(value):
        return " ".join(str(value).casefold().split())

    @staticmethod
    def _failed_job_rate():
        total = TranslationJob.objects.count()
        return Command._rate(TranslationJob.objects.filter(status="failed").count(), total)

    @staticmethod
    def _ocr_metrics():
        results = TranslationJob.objects.filter(ocr_results__confidence__isnull=False).distinct()
        values = [v for job in results for v in job.ocr_results.values_list("confidence", flat=True) if v is not None]
        return {"mean_confidence": round(sum(values) / len(values), 4) if values else None,
                "cer": None, "wer": None,
                "disclaimer": "CER/WER require fixture ground truth and are reported by ocr_benchmark."}

    @staticmethod
    def _layout_metrics():
        completed = TranslationJob.objects.filter(status="completed")
        warning_jobs = 0
        for job in completed.only("metadata"):
            warnings = (job.metadata or {}).get("layout_warnings", [])
            warning_jobs += bool(warnings)
        total = completed.count()
        return {"pdf_reconstruction_success_rate": Command._rate(completed.exclude(output_file_path="").count(), total),
                "layout_overflow_rate": Command._rate(warning_jobs, total),
                "missing_text_rate": None,
                "disclaimer": "Missing-text rate requires a human-reviewed layout fixture."}

    @staticmethod
    def _summary(report):
        m = report["technical_matching"]
        return "\n".join([
            "Phase 3 Translation Pipeline Evaluation",
            "Technical phrasebook matching only — not a linguistic translation accuracy claim.",
            f"Cases: {report['case_count']}",
            f"Exact: {m['exact_match_rate']}; normalized: {m['normalized_match_rate']}; fuzzy: {m['fuzzy_match_rate']}; segmented: {m['segmented_match_rate']}; unknown: {m['unknown_rate']}",
            f"Processing time: {report['processing']['processing_time_seconds']}s",
        ]) + "\n"
