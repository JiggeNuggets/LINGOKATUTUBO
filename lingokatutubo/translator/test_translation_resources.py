import json
import os
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import LanguageResourceImportBatch, PhrasebookEntry
from .services.translation_dataset import TranslationDataset, reset_translation_dataset
from .views import _staging_key


class TranslationResourcesTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user("resource-manager", password="safe-password")
        self.manager.user_permissions.add(Permission.objects.get(codename="manage_language_resources"))
        self.user = User.objects.create_user("ordinary-user", password="safe-password")
        self.entry = PhrasebookEntry.objects.create(
            tagabawa="Madayaw", english="Good", filipino="Mabuti", cebuano="Maayo",
            topic="greeting", part_of_speech="phrase", source="test",
        )

    def _login_manager(self):
        self.client.force_login(self.manager)

    def test_normal_user_cannot_access_resource_or_match_tester_routes(self):
        self.client.force_login(self.user)
        for url in [
            reverse("translator:translation_resources"),
            reverse("translator:translation_resource_add"),
            reverse("translator:translation_resources_import"),
            reverse("translator:translation_resources_match_tester"),
            reverse("translator:legacy_resource_staging"),
        ]:
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_active_resource_requires_two_language_values(self):
        self._login_manager()
        response = self.client.post(reverse("translator:translation_resource_add"), {
            "tagabawa": "Usa", "english": "", "filipino": "", "cebuano": "",
            "source": "test", "is_active": "on",
        })
        self.assertContains(response, "at least two usable language values", status_code=200)
        self.assertEqual(PhrasebookEntry.objects.count(), 1)

    def test_exact_duplicate_is_blocked_and_edit_creates_revision(self):
        self._login_manager()
        duplicate = self.client.post(reverse("translator:translation_resource_add"), {
            "tagabawa": "Madayaw", "english": "Good", "filipino": "Mabuti", "cebuano": "Maayo",
            "source": "test", "is_active": "on",
        })
        self.assertContains(duplicate, "exact duplicate", status_code=200)
        self.assertEqual(PhrasebookEntry.objects.count(), 1)
        response = self.client.post(reverse("translator:translation_resource_edit", args=[self.entry.id]), {
            "tagabawa": "Madayaw", "english": "Very good", "filipino": "Mabuti", "cebuano": "Maayo",
            "source": "test", "is_active": "on",
        })
        self.assertRedirects(response, reverse("translator:translation_resources"))
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.revision_number, 2)
        self.assertEqual(self.entry.revisions.count(), 2)

    def test_development_resources_is_active_database_only(self):
        dataset = TranslationDataset(data_mode="development_resources")
        result = dataset.translate_phrase_with_metadata("Good", "english", "tagabawa")
        self.assertEqual(result["translated"], "Madayaw")
        self.entry.is_active = False
        self.entry.save()
        inactive_dataset = TranslationDataset(data_mode="development_resources")
        self.assertEqual(
            inactive_dataset.translate_phrase_with_metadata("Good", "english", "tagabawa")["method"],
            "unknown_for_review",
        )

    def test_verified_only_does_not_fall_back_to_active_unverified_entry(self):
        dataset = TranslationDataset(data_mode="verified_only")
        self.assertFalse(dataset.is_loaded)
        self.assertEqual(
            dataset.translate_phrase_with_metadata("Good", "english", "tagabawa")["method"],
            "unknown_for_review",
        )

    def test_import_preview_confirmation_and_export_are_non_destructive(self):
        self._login_manager()
        source = b"tagabawa,english,filipino,cebuano,source\nBago,New,Bago,Bag-o,community\nMadayaw,Good,Mabuti,Maayo,community\n"
        upload = SimpleUploadedFile("resources.csv", source, content_type="text/csv")
        response = self.client.post(reverse("translator:translation_resources_import"), {"file": upload})
        self.assertContains(response, "Dry-run preview")
        self.assertEqual(PhrasebookEntry.objects.count(), 1)
        response = self.client.post(reverse("translator:translation_resources_import_confirm"))
        self.assertRedirects(response, reverse("translator:translation_resources"))
        self.assertEqual(PhrasebookEntry.objects.count(), 2)
        batch = LanguageResourceImportBatch.objects.get()
        self.assertEqual(batch.rows_created, 1)
        self.assertEqual(batch.rows_duplicated, 1)
        export = self.client.get(reverse("translator:translation_resources_export"))
        self.assertEqual(export.status_code, 200)
        self.assertIn(b"tagabawa,english", export.content)

    def test_match_tester_uses_active_resource_mode(self):
        self._login_manager()
        response = self.client.post(reverse("translator:translation_resources_match_tester"), {
            "source_language": "english", "target_language": "tagabawa", "text": "Good",
        })
        self.assertContains(response, "Madayaw")
        self.assertContains(response, "Match type")

    def test_legacy_staging_is_non_destructive_until_confirmed_import(self):
        self._login_manager()
        record = {
            "normalized_key": ["staged", "staged phrase", "inilaan", "giandam"],
            "values": {"tagabawa": "Staged", "english": "Staged phrase", "filipino": "Inilaan", "cebuano": "Giandam"},
            "staging_status": "READY_FOR_ADMIN_REVIEW", "reason": "Structurally complete.",
            "source_files": ["cross_lingual_cleaned_v1.csv"], "original_row_identifiers": ["TEST-1"],
            "completeness": 4,
        }
        report = {"legacy_only": [record], "legacy_only_unique_normalized_keys": 1}
        staging_key = _staging_key(record)
        with patch("translator.views.analyze_resource_inventory", return_value=report):
            response = self.client.get(reverse("translator:legacy_resource_staging"))
            self.assertContains(response, "Legacy Resource Staging")
            self.assertEqual(PhrasebookEntry.objects.count(), 1)
            self.client.post(reverse("translator:legacy_resource_staging_action"), {"staging_key": staging_key, "action": "import"})
            self.assertEqual(PhrasebookEntry.objects.count(), 1)
            response = self.client.post(reverse("translator:legacy_resource_staging_import_confirm"))
        self.assertRedirects(response, reverse("translator:legacy_resource_staging"))
        self.assertEqual(PhrasebookEntry.objects.count(), 2)
        imported = PhrasebookEntry.objects.get(english="Staged phrase")
        self.assertTrue(imported.is_active)
        self.assertEqual(imported.source, "legacy_corpus_csv")

    def test_database_mode_preserves_matching_cascade_and_language_aliases(self):
        PhrasebookEntry.objects.create(tagabawa="Hello", english="Hello", filipino="Kamusta", cebuano="Kumusta")
        PhrasebookEntry.objects.create(tagabawa="Go", english="Go", filipino="Pumunta", cebuano="Lakaw")
        PhrasebookEntry.objects.create(tagabawa="Madayaw kaayo", english="Very good", filipino="Napakabuti", cebuano="Maayo kaayo")
        PhrasebookEntry.objects.create(tagabawa="Only source", english="", filipino="Sangkap", cebuano="")
        dataset = TranslationDataset(data_mode="development_resources")
        self.assertEqual(dataset.translate_phrase_with_metadata("good", "english", "tagabawa")["method"], "exact_phrase")
        self.assertEqual(dataset.translate_phrase_with_metadata(" GOOD! ", "english", "tagabawa")["method"], "normalized_phrase")
        self.assertEqual(dataset.translate_phrase_with_metadata("Verry good", "english", "tagabawa")["method"], "fuzzy_match")
        self.assertEqual(dataset.translate_phrase_with_metadata("Hello. Good", "english", "tagabawa")["method"], "segmented_phrase")
        self.assertEqual(dataset.translate_phrase_with_metadata("Kamusta", "tagalog", "bisaya")["translated"], "Kumusta")
        self.assertEqual(dataset.translate_phrase_with_metadata("Sangkap", "filipino", "english")["method"], "unknown_for_review")
        unknown = dataset.translate_phrase_with_metadata("No resource here", "english", "tagabawa")
        self.assertEqual(unknown["translated"], "No resource here")
        self.assertEqual(unknown["method"], "unknown_for_review")

    def test_admin_change_propagates_to_match_tester_quick_and_document_pipeline(self):
        from .services.pipeline_service import PipelineService

        self._login_manager()
        with patch.dict(os.environ, {"TRANSLATION_DATA_MODE": "development_resources"}):
            reset_translation_dataset()
            response = self.client.post(reverse("translator:translation_resource_add"), {
                "tagabawa": "Pangandam", "english": "Parity staging fixture", "filipino": "Paghahandang pansubok", "cebuano": "Andam nga pagsulay",
                "source": "test fixture", "is_active": "on",
            })
            self.assertRedirects(response, reverse("translator:translation_resources"))
            entry = PhrasebookEntry.objects.get(english="Parity staging fixture")
            matcher = self.client.post(reverse("translator:translation_resources_match_tester"), {
                "source_language": "english", "target_language": "tagabawa", "text": "Parity staging fixture",
            })
            self.assertContains(matcher, "Pangandam")
            quick = self.client.post(reverse("translator:quick_translate"), data=json.dumps({
                "text": "Parity staging fixture", "source_language": "english", "target_language": "tagabawa",
            }), content_type="application/json")
            self.assertEqual(quick.json()["translated"], "Pangandam")
            service = PipelineService()
            layout = [{"blocks": [{"type": "text", "lines": [{"text": "Parity staging fixture"}]}]}]
            translated = service._translate_layout(layout, "english", "tagabawa", [])
            self.assertEqual(translated["0_0_0"]["translated"], "Pangandam")
            self.client.post(reverse("translator:translation_resource_toggle", args=[entry.id]))
            reset_translation_dataset()
            self.assertEqual(
                self.client.post(reverse("translator:quick_translate"), data=json.dumps({
                    "text": "Parity staging fixture", "source_language": "english", "target_language": "tagabawa",
                }), content_type="application/json").json()["translated"],
                "Parity staging fixture",
            )
            self.client.post(reverse("translator:translation_resource_toggle", args=[entry.id]))
            self.assertEqual(
                self.client.post(reverse("translator:quick_translate"), data=json.dumps({
                    "text": "Parity staging fixture", "source_language": "english", "target_language": "tagabawa",
                }), content_type="application/json").json()["translated"],
                "Pangandam",
            )
        reset_translation_dataset()

    def tearDown(self):
        reset_translation_dataset()
