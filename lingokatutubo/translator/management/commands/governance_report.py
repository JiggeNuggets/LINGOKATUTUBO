import json
from pathlib import Path

from django.core.management.base import BaseCommand

from translator.models import LanguageResourceIssue, PhrasebookEntry
from translator.services.governance import eligibility_reasons, runtime_eligible_entries


class Command(BaseCommand):
    help = "Write a privacy-safe language-resource governance summary."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        entries = list(PhrasebookEntry.objects.all())
        payload = {
            "total_records": len(entries),
            "by_validation_status": {status: sum(entry.validation_status == status for entry in entries) for status in ("pending", "under_review", "verified", "rejected", "restricted", "deprecated")},
            "runtime_approved": sum(entry.is_approved_for_runtime for entry in entries),
            "missing_provenance": sum(not entry.source_title or not entry.source_owner for entry in entries),
            "missing_license": sum(entry.license_status == "unrecorded" for entry in entries),
            "unresolved_issues": LanguageResourceIssue.objects.filter(is_resolved=False).count(),
            "export_eligible": len(runtime_eligible_entries(entries)),
            "eligibility_exclusions": {},
        }
        for entry in entries:
            for reason in eligibility_reasons(entry):
                payload["eligibility_exclusions"][reason] = payload["eligibility_exclusions"].get(reason, 0) + 1
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(str(output))
