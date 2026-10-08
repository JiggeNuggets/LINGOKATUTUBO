import json
from pathlib import Path

from django.core.management.base import BaseCommand

from translator.services.resource_parity import analyze_resource_inventory


class Command(BaseCommand):
    help = "Read-only inventory comparison of legacy and active database translation resources."

    def add_arguments(self, parser):
        parser.add_argument("--json-output", type=Path, help="Optional JSON report path.")

    def handle(self, *args, **options):
        report = analyze_resource_inventory()
        output_path = options.get("json_output")
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(f"Wrote {output_path}")
        self.stdout.write(json.dumps({
            "legacy": report["legacy"], "database": report["database"],
            "overlap": report["overlap_unique_normalized_keys"],
            "legacy_only": report["legacy_only_unique_normalized_keys"],
            "database_only": report["database_only_unique_normalized_keys"],
            "classification_summary": report["classification_summary"],
            "recommendation_summary": report["recommendation_summary"],
        }, ensure_ascii=False, indent=2))
