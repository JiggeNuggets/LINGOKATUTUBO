"""Focused Phase 1 regression tests for stabilized public surfaces."""

import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import PhrasebookEntry, UserActivityLog


@override_settings(
    LINGOKATUTUBO_QUICK_TRANSLATE_MAX_TEXT_LENGTH=20,
    LINGOKATUTUBO_QUICK_TRANSLATE_MAX_REQUEST_BYTES=200,
    LINGOKATUTUBO_QUICK_TRANSLATE_RATE_LIMIT=2,
    LINGOKATUTUBO_QUICK_TRANSLATE_RATE_WINDOW_SECONDS=60,
)
class QuickTranslationEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("phase1-user", password="safe-test-password")
        self.url = reverse("translator:quick_translate")

    def _post(self, payload, **kwargs):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            **kwargs,
        )

    def test_get_is_rejected_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["ok"], False)

    def test_anonymous_user_is_rejected(self):
        response = self._post({"text": "Hello"})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("Hello", response.content.decode())

    def test_invalid_content_type_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"text": "Hello"})
        self.assertEqual(response.status_code, 415)

    def test_oversized_request_is_rejected(self):
        self.client.force_login(self.user)
        response = self._post({"text": "x" * 21})
        self.assertEqual(response.status_code, 413)

    def test_missing_text_is_rejected(self):
        self.client.force_login(self.user)
        response = self._post({"target_language": "english"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Text is required.")

    @patch("translator.quick_translate.quick_translate_text")
    def test_rate_limit_is_enforced(self, translate):
        translate.return_value = {"translated": "test"}
        self.client.force_login(self.user)
        self.assertEqual(self._post({"text": "one"}).status_code, 200)
        self.assertEqual(self._post({"text": "two"}).status_code, 200)
        response = self._post({"text": "three"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(translate.call_count, 2)

    @patch("translator.quick_translate.quick_translate_text")
    def test_authenticated_json_request_succeeds_without_logging_text(self, translate):
        translate.return_value = {
            "original": "Hello",
            "translated": "Test translation",
            "translation_status": "exact_match",
            "review_required": False,
        }
        self.client.force_login(self.user)
        response = self._post({"text": "Hello", "source_language": "english"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        event = UserActivityLog.objects.get(action="quick_translate")
        self.assertEqual(event.metadata["text_length"], 5)
        self.assertNotIn("Hello", json.dumps(event.metadata))

    @patch("translator.quick_translate.quick_translate_text")
    def test_public_response_hides_matching_metadata(self, translate):
        translate.return_value = {
            "original": "Hello", "translated": "Test translation",
            "source_language": "english", "target_language": "tagabawa",
            "method": "fuzzy_match", "confidence": 0.91,
            "dataset_loaded": True, "matched_entry_id": "secret-resource-id",
            "needs_review": True,
        }
        self.client.force_login(self.user)
        payload = self._post({"text": "Hello", "source_language": "english"}).json()
        self.assertTrue(payload["ok"])
        for private_key in ("method", "confidence", "dataset_loaded", "matched_entry_id", "translation_status"):
            self.assertNotIn(private_key, payload)
        self.assertTrue(payload["review_required"])

    @patch("translator.quick_translate.quick_translate_text", side_effect=RuntimeError("private failure"))
    def test_server_error_is_safe(self, _translate):
        self.client.force_login(self.user)
        response = self._post({"text": "Hello"})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private failure", response.content.decode())

    def test_csrf_is_enforced_for_json_post(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(
            self.url,
            data=json.dumps({"text": "Hello"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/json")

class PhrasebookGovernanceTests(TestCase):
    def test_existing_style_entry_defaults_to_pending_and_edits_keep_history(self):
        entry = PhrasebookEntry.objects.create(
            english="Synthetic source", tagabawa="Synthetic target", source="test fixture"
        )
        self.assertEqual(entry.validation_status, "pending")
        self.assertFalse(entry.is_approved_for_runtime)
        self.assertEqual(entry.revisions.count(), 1)
        entry.notes = "Synthetic revision only"
        entry.save()
        entry.refresh_from_db()
        self.assertEqual(entry.revision_number, 2)
        self.assertEqual(entry.revisions.count(), 2)
        self.assertEqual(entry.revisions.order_by("revision_number").first().snapshot["english"], "Synthetic source")
