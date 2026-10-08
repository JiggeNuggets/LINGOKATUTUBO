"""Import JSON/CSV language resources as pending governed records."""

import csv
import hashlib
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from translator.models import LanguageResourceImportBatch, LanguageResourceIssue, PhrasebookEntry


LANG_COLUMNS = {
    "english": "english", "english_text": "english", "en": "english",
    "tagabawa": "tagabawa", "bagobo": "tagabawa", "bagobo_text": "tagabawa", "bgs": "tagabawa",
    "filipino": "filipino", "tagalog": "filipino", "tagalog_text": "filipino",
    "cebuano": "cebuano", "cebuano_text": "cebuano", "bisaya": "cebuano",
}


def normalized(value):
    return re.sub(r"[^\w]+", "", str(value or "").casefold())


class Command(BaseCommand):
    help = "Import a JSON/CSV language resource without verification, approval, or destructive replacement."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True)
        parser.add_argument("--batch", "--batch-name", dest="batch_name", required=True)
        parser.add_argument("--report", "--report-path", dest="report_path", required=True)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--skip-duplicates", action="store_true")

    def handle(self, *args, **options):
        if options["dry_run"] == options["commit"]:
            raise CommandError("Choose exactly one of --dry-run or --commit.")
        source = Path(options["source"])
        if not source.is_file():
            raise CommandError("Source file does not exist.")
        rows = self._rows(source)
        self._validate_rows(rows)
        checksum = hashlib.sha256(source.read_bytes()).hexdigest()
        report = {"source": str(source), "checksum": checksum, "mode": "dry-run" if options["dry_run"] else "commit", "processed": 0, "created": 0, "skipped": 0, "duplicates": 0, "conflicts": 0, "incomplete": 0, "requires_review": 0, "issues": []}
        batch_identifier = f'{options["batch_name"]}--dry-run' if options["dry_run"] else options["batch_name"]
        if LanguageResourceImportBatch.objects.filter(identifier=batch_identifier).exists():
            raise CommandError(f"Batch identifier already exists: {batch_identifier}")
        batch = LanguageResourceImportBatch.objects.create(
            identifier=batch_identifier,
            source_filename=str(source),
            source_checksum_sha256=checksum,
            is_dry_run=options["dry_run"],
            report_path=options["report_path"],
        )
        for row_number, raw in enumerate(rows, start=2):
            report["processed"] += 1
            row = self._canonical_row(raw)
            issue_types = self._issues(row)
            existing = list(PhrasebookEntry.objects.all())
            exact = next((entry for entry in existing if all(getattr(entry, key) == value for key, value in row.items())), None)
            normalized_match = next((entry for entry in existing if all(normalized(getattr(entry, key)) == normalized(value) for key, value in row.items()) and entry != exact), None)
            possible_match = next((entry for entry in existing if entry != exact and entry != normalized_match and (normalized(entry.english) == normalized(row["english"]) or normalized(entry.tagabawa) == normalized(row["tagabawa"]))), None)
            conflict = any(normalized(entry.english) == normalized(row["english"]) and normalized(entry.tagabawa) != normalized(row["tagabawa"]) for entry in existing) if row["english"] else False
            if exact:
                issue_types.append("exact_duplicate")
            elif normalized_match:
                issue_types.append("normalized_duplicate")
            elif possible_match:
                issue_types.append("possible_duplicate")
            if conflict:
                issue_types.append("conflicting_translation")
            report["duplicates"] += sum(kind in {"exact_duplicate", "normalized_duplicate"} for kind in issue_types)
            report["conflicts"] += int("conflicting_translation" in issue_types)
            report["incomplete"] += int("incomplete_record" in issue_types)
            report["requires_review"] += int(bool(issue_types))
            report["issues"].append({"row": row_number, "categories": issue_types})
            if exact or normalized_match or (options["skip_duplicates"] and issue_types):
                report["skipped"] += 1
                continue
            if options["dry_run"]:
                report["created"] += 1
                continue
            with transaction.atomic():
                entry = PhrasebookEntry.objects.create(
                    **row,
                    source=f"import:{source.name}",
                    import_batch=batch,
                    validation_status="pending",
                    is_sme_verified=False,
                    is_approved_for_runtime=False,
                    license_status="unrecorded",
                    cultural_sensitivity_status="unreviewed",
                    access_restriction="pending_review",
                    needs_review=True,
                    has_unresolved_conflict=conflict,
                )
                for category in set(issue_types + ["validation_required"]):
                    LanguageResourceIssue.objects.create(batch=batch, entry=entry, category=category, source_row_number=row_number)
            report["created"] += 1
        for field, value in {"rows_processed": report["processed"], "rows_created": report["created"], "rows_skipped": report["skipped"], "rows_duplicated": report["duplicates"], "rows_conflicting": report["conflicts"], "rows_incomplete": report["incomplete"], "rows_requiring_review": report["requires_review"]}.items():
            setattr(batch, field, value)
        batch.save()
        report["batch"] = batch.identifier
        destination = Path(options["report_path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(json.dumps({key: report[key] for key in report if key != "issues"}))

    def _rows(self, source):
        if source.suffix.lower() == ".json":
            value = json.loads(source.read_text(encoding="utf-8-sig"))
            rows = value.get("rows", value) if isinstance(value, dict) else value
            if not isinstance(rows, list):
                raise CommandError("JSON source must be a list or an object with a 'rows' list.")
            return rows
        if source.suffix.lower() == ".csv":
            with source.open(encoding="utf-8-sig", newline="") as handle:
                return list(csv.DictReader(handle))
        raise CommandError("Only JSON and CSV source files are supported.")

    def _validate_rows(self, rows):
        if not rows:
            raise CommandError("Source contains no rows; no batch was created.")
        if not all(isinstance(row, dict) for row in rows):
            raise CommandError("Every source row must be an object with named columns.")
        columns = {str(key).strip().casefold() for row in rows for key in row}
        if not columns.intersection(LANG_COLUMNS):
            raise CommandError("Source has no supported language columns; no batch was created.")

    def _canonical_row(self, raw):
        result = {key: "" for key in ("english", "tagabawa", "filipino", "cebuano")}
        for key, value in raw.items():
            canonical = LANG_COLUMNS.get(str(key).strip().casefold())
            if canonical:
                result[canonical] = str(value or "").strip()
        return result

    def _issues(self, row):
        issues = []
        if sum(bool(value) for value in row.values()) < 2 or not all(row.values()):
            issues.append("incomplete_record")
        if any("�" in value or re.search(r"[\x00-\x08]", value) for value in row.values()):
            issues.append("possible_ocr_artifact")
        issues.extend(["missing_provenance", "missing_license"])
        return issues
