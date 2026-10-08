"""Export SME-validated PhrasebookEntry rows to the runtime validated CSV.

The database/admin is the validation workspace; the file written here is what
the runtime TranslationDataset actually loads (datasets/validated/*.csv).
This legacy compatibility export is limited to historical admin-approved rows:
    is_active=True AND is_sme_verified=True AND needs_review=False.
New Phase 2 imports always set is_sme_verified=False and are never eligible
here; use export_verified_language_resources for governed runtime exports.
Rows already present in the base runtime dataset (translation_data.json +
cleaned corpus) are skipped so exports never duplicate shipped data.
"""

import csv
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from translator.models import PhrasebookEntry
from translator.services.translation_dataset import TranslationDataset

LANGUAGE_FIELDS = ("english", "tagabawa", "filipino", "cebuano")
CSV_COLUMNS = ["english", "tagabawa", "filipino", "cebuano", "topic", "source", "notes"]


class Command(BaseCommand):
    help = (
        "Export SME-verified, active, not-needs-review PhrasebookEntry rows "
        "to datasets/validated/ for the runtime translation dataset."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=None,
            help=(
                "Output CSV path. Defaults to "
                "datasets/validated/validated_phrasebook_<date>.csv"
            ),
        )

    def handle(self, *args, **options):
        output = options["output"]
        if output is None:
            output = (
                Path(settings.BASE_DIR)
                / "datasets"
                / "validated"
                / f"validated_phrasebook_{date.today().isoformat()}.csv"
            )
        output = Path(output)

        # Base dataset only (no validated imports): duplicates are judged
        # against shipped data, so re-running the export stays idempotent
        # with respect to translation_data.json and the cleaned corpus.
        base_dataset = TranslationDataset(include_validated_imports=False)

        entries = PhrasebookEntry.objects.filter(
            is_active=True,
            is_sme_verified=True,
            needs_review=False,
        ).order_by("topic", "english", "id")

        exported_rows = []
        skipped_duplicates = 0
        skipped_incomplete = 0
        for entry in entries:
            values = {field: (getattr(entry, field) or "").strip() for field in LANGUAGE_FIELDS}
            filled = {field: value for field, value in values.items() if value}
            # A translation needs at least a source and a target.
            if len(filled) < 2:
                skipped_incomplete += 1
                continue
            if self._is_runtime_duplicate(base_dataset, filled):
                skipped_duplicates += 1
                continue
            exported_rows.append(
                {
                    **values,
                    "topic": (entry.topic or "").strip(),
                    "source": "validated_import",
                    "notes": (entry.notes or "").strip(),
                }
            )

        if not exported_rows:
            self.stdout.write(
                self.style.WARNING(
                    "Nothing to export: no verified rows beyond the runtime dataset "
                    f"(skipped {skipped_duplicates} duplicate(s), "
                    f"{skipped_incomplete} incomplete)."
                )
            )
            return

        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(exported_rows)

        self.stdout.write(self.style.SUCCESS(f"Exported {len(exported_rows)} row(s) to {output}"))
        self.stdout.write(
            f"Skipped {skipped_duplicates} duplicate(s) already in the runtime dataset; "
            f"{skipped_incomplete} incomplete row(s)."
        )
        self.stdout.write("Restart the server to activate validated imports.")

    @staticmethod
    def _is_runtime_duplicate(dataset: TranslationDataset, filled: dict) -> bool:
        """True when an existing dataset row matches every filled field."""
        if not dataset.is_loaded:
            return False
        first_lang, first_value = next(iter(filled.items()))
        bucket = dataset._phrase_indices.get(first_lang, {}).get(
            first_value.strip().lower(), []
        )
        for row in bucket:
            if all(
                (row.get(f"{lang}_source", "") or "").strip().lower()
                == value.strip().lower()
                for lang, value in filled.items()
            ):
                return True
        return False
