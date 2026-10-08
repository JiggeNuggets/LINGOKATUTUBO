import json
import tempfile
from pathlib import Path

from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.test import TestCase

from .models import LanguageEntryReview, LanguageResourceImportBatch, PhrasebookEntry
from .services.governance import eligibility_reasons, is_runtime_eligible, review_entry


class Phase2GovernanceTests(TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.source = Path(self.tempdir.name) / "synthetic.json"
        self.report = Path(self.tempdir.name) / "import-report.json"
        self.source.write_text(json.dumps({"rows": [{"english": "Synthetic hello", "tagabawa": "Synthetic greeting", "filipino": "Synthetic Filipino", "cebuano": "Synthetic Cebuano"}]}), encoding="utf-8")

    def import_command(self, *args):
        call_command("import_language_resources", "--source", str(self.source), "--batch-name", "synthetic-batch", "--report-path", str(self.report), *args)

    def test_dry_run_creates_no_phrasebook_records(self):
        self.import_command("--dry-run")
        self.assertEqual(PhrasebookEntry.objects.count(), 0)
        self.assertEqual(json.loads(self.report.read_text())["created"], 1)
        self.assertEqual(LanguageResourceImportBatch.objects.get().is_dry_run, True)

    def test_commit_import_is_pending_and_not_runtime_approved(self):
        self.import_command("--commit")
        entry = PhrasebookEntry.objects.get()
        self.assertEqual(entry.validation_status, "pending")
        self.assertFalse(entry.is_approved_for_runtime)
        self.assertEqual(entry.access_restriction, "pending_review")

    def test_existing_verified_entry_is_not_overwritten(self):
        existing = PhrasebookEntry.objects.create(english="Synthetic hello", tagabawa="Synthetic greeting", filipino="Synthetic Filipino", cebuano="Synthetic Cebuano", validation_status="verified", is_approved_for_runtime=True)
        self.import_command("--commit")
        existing.refresh_from_db()
        self.assertEqual(PhrasebookEntry.objects.count(), 1)
        self.assertTrue(existing.is_approved_for_runtime)

    def test_duplicate_is_reported_without_merge(self):
        PhrasebookEntry.objects.create(english="Synthetic hello", tagabawa="Synthetic greeting", filipino="Synthetic Filipino", cebuano="Synthetic Cebuano")
        self.import_command("--commit")
        report = json.loads(self.report.read_text())
        self.assertGreaterEqual(report["duplicates"], 1)
        self.assertEqual(PhrasebookEntry.objects.count(), 1)

    def test_role_setup_does_not_grant_validator_rights_to_administrator(self):
        call_command("setup_governance_roles")
        administrator = Group.objects.get(name="Administrator")
        validator = Group.objects.get(name="Validator")
        review_permission = Permission.objects.get(codename="review_language_entry")
        self.assertNotIn(review_permission, administrator.permissions.all())
        self.assertIn(review_permission, validator.permissions.all())

    def test_only_runtime_eligible_entry_exports(self):
        pending = PhrasebookEntry.objects.create(english="Pending", tagabawa="Pending tag", validation_status="pending")
        eligible = PhrasebookEntry.objects.create(english="Eligible", tagabawa="Eligible tag", filipino="Eligible fil", cebuano="Eligible ceb", source_title="Synthetic source", source_owner="Synthetic owner", license_status="permitted", cultural_sensitivity_status="approved", access_restriction="public", validation_status="verified", is_approved_for_runtime=True, required_reviews=0)
        self.assertFalse(is_runtime_eligible(pending))
        self.assertTrue(is_runtime_eligible(eligible), eligibility_reasons(eligible))
        output = Path(self.tempdir.name) / "verified.json"; manifest = Path(self.tempdir.name) / "manifest.json"
        actor = User.objects.create_user("exporter")
        actor.user_permissions.add(Permission.objects.get(codename="manage_language_resources"))
        call_command("export_verified_language_resources", "--format", "json", "--output", str(output), "--dataset-version", "test-v1", "--manifest", str(manifest), "--actor", actor.username)
        rows = json.loads(output.read_text())["rows"]
        self.assertEqual([row["english"] for row in rows], ["Eligible"])
        self.assertIn("sha256", json.loads(manifest.read_text()))

    def test_validator_review_requires_permission_and_creates_audit(self):
        entry = PhrasebookEntry.objects.create(english="Review", tagabawa="Review tag")
        user = User.objects.create_user("validator")
        with self.assertRaises(PermissionError):
            review_entry(entry=entry, reviewer=user, decision="verify", notes="Synthetic review")
        user.user_permissions.add(Permission.objects.get(codename="review_language_entry"))
        user = User.objects.get(pk=user.pk)  # Refresh Django's permission cache.
        review_entry(entry=entry, reviewer=user, decision=LanguageEntryReview.Decision.REQUEST_REVIEW, notes="Needs another reviewer")
        self.assertEqual(entry.reviews.count(), 1)
