import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from .models import DocumentPage, OCRCorrection, OCRResult, PhrasebookEntry, TranslationJob, TranslationSegment, UnknownTranslationRecord
from .services.translation_dataset import TranslationDataset


class Phase3TranslationSafetyTests(TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.dataset = Path(self.tempdir.name) / "synthetic.json"
        self.dataset.write_text(json.dumps({"rows": [
            {"english": "hello", "tagabawa": "mabuhay"},
            {"english": "go", "tagabawa": "lakaw"},
        ]}), encoding="utf-8")

    def test_exact_and_normalized_results_are_structured(self):
        result = TranslationDataset(str(self.dataset), include_default_corpus=False).translate_phrase_with_metadata("Hello!", "english", "tagabawa")
        self.assertEqual(result["match_method"], "normalized")
        self.assertEqual(result["displayed_text"], "Mabuhay!")
        self.assertEqual(result["source_text"], "Hello!")
        self.assertEqual(result["validation_status"], "unverified")
        self.assertIn("provenance_status", result)

    def test_fuzzy_requires_threshold_and_review(self):
        with patch.dict(os.environ, {"TRANSLATION_FUZZY_THRESHOLD": "0.75", "TRANSLATION_FUZZY_SHORT_THRESHOLD": "0.75"}):
            result = TranslationDataset(str(self.dataset), include_default_corpus=False).translate_phrase_with_metadata("helo", "english", "tagabawa")
        self.assertEqual(result["match_method"], "fuzzy")
        self.assertTrue(result["review_required"])
        self.assertEqual(result["matched_term"], "hello")

    def test_short_word_fuzzy_protection_and_unknown_preservation(self):
        with patch.dict(os.environ, {"TRANSLATION_FUZZY_THRESHOLD": "0.50", "TRANSLATION_FUZZY_SHORT_THRESHOLD": "1.0"}):
            result = TranslationDataset(str(self.dataset), include_default_corpus=False).translate_phrase_with_metadata("do", "english", "tagabawa")
        self.assertEqual(result["match_method"], "unknown")
        self.assertEqual(result["displayed_text"], "do")
        self.assertTrue(result["review_required"])

    def test_verified_only_has_no_unverified_fallback(self):
        pending = PhrasebookEntry.objects.create(english="hello", tagabawa="pending")
        data = TranslationDataset(data_mode="verified_only")
        self.assertFalse(data.is_loaded)
        self.assertEqual(pending.validation_status, "pending")


class Phase3ReviewPersistenceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("phase3")
        self.job = TranslationJob.objects.create(owner=self.user, original_filename="fixture.txt", file_type="txt")
        self.page = DocumentPage.objects.create(job=self.job, page_number=1)

    def test_unknown_record_and_ocr_correction_preserve_originals(self):
        segment = TranslationSegment.objects.create(job=self.job, page=self.page, segment_index=1, source_text="unknown", translated_text="unknown", source_language="english", target_language="tagabawa", method="unknown", needs_review=True)
        unknown = UnknownTranslationRecord.objects.create(job=self.job, page=self.page, segment=segment, source_text="unknown", normalized_text="unknown", source_language="english", target_language="tagabawa")
        ocr = OCRResult.objects.create(job=self.job, page=self.page, text="raw ocr", status="pending_review")
        correction = OCRCorrection.objects.create(ocr_result=ocr, page=self.page, original_ocr_text="raw ocr", corrected_text="corrected", author=self.user)
        ocr.refresh_from_db()
        self.assertEqual(unknown.review_status, "pending")
        self.assertEqual(ocr.text, "raw ocr")
        self.assertEqual(correction.status, "proposed")

    def test_evaluation_command_writes_both_reports(self):
        fixture = Path(tempfile.mkdtemp()) / "evaluation.json"
        self.addCleanup(lambda: fixture.parent.rmdir() if fixture.parent.exists() and not list(fixture.parent.iterdir()) else None)
        fixture.write_text(json.dumps({"cases": [{"id": "synthetic-1", "source_text": "hello", "expected_text": "mabuhay", "human_reviewed": False}]}), encoding="utf-8")
        output = fixture.parent / "report.json"
        call_command("evaluate_translation_pipeline", "--dataset", str(fixture), "--output", str(output))
        self.assertTrue(output.exists())
        self.assertTrue(output.with_suffix(".txt").exists())
        self.assertIn("technical_matching", json.loads(output.read_text(encoding="utf-8")))
