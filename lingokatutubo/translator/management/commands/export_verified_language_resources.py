import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from translator.models import PhrasebookEntry
from translator.services.governance import GOVERNANCE_POLICY_VERSION, eligibility_reasons, runtime_eligible_entries


class Command(BaseCommand):
    help = "Export only runtime-eligible governed language resources with a manifest and checksum."

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=("json", "csv"), required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--dataset-version", required=True)
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--actor", required=True, help="Username of an authorized export operator.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        user_model = get_user_model()
        try:
            actor = user_model.objects.get(username=options["actor"])
        except user_model.DoesNotExist as error:
            raise CommandError("Export actor does not exist.") from error
        if not (actor.is_superuser or actor.has_perm("translator.manage_language_resources")):
            raise CommandError("Export actor lacks language-resource export authorization.")
        entries = list(PhrasebookEntry.objects.select_related("import_batch"))
        eligible = runtime_eligible_entries(entries)
        exclusions = {}
        for entry in entries:
            for reason in eligibility_reasons(entry):
                exclusions[reason] = exclusions.get(reason, 0) + 1
        payload = [{key: getattr(entry, key) for key in ("english", "tagabawa", "filipino", "cebuano", "part_of_speech", "word_sense", "source_title", "source_page", "source_owner", "license_status", "validation_status")} for entry in eligible]
        source_batches = sorted({
            (entry.import_batch.identifier, entry.import_batch.source_checksum_sha256)
            for entry in eligible if entry.import_batch_id
        })
        manifest = {"dataset_version": options["dataset_version"], "exported_at": datetime.now(timezone.utc).isoformat(), "record_count": len(payload), "excluded_count": len(entries) - len(payload), "exclusion_reasons": exclusions, "governance_policy_version": GOVERNANCE_POLICY_VERSION, "export_actor": actor.username, "source_batches": [{"identifier": identifier, "sha256": checksum} for identifier, checksum in source_batches], "dry_run": options["dry_run"]}
        if not options["dry_run"]:
            output = Path(options["output"]); output.parent.mkdir(parents=True, exist_ok=True)
            if options["format"] == "json": output.write_text(json.dumps({"rows": payload}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            else:
                with output.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=payload[0].keys() if payload else ["english", "tagabawa", "filipino", "cebuano"]); writer.writeheader(); writer.writerows(payload)
            manifest["sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
        Path(options["manifest"]).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(json.dumps(manifest))
