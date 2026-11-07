"""T06 technical matching checks; copied resource text is not an SME gold set."""
import copy
import csv
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import fitz
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from django.db import OperationalError, IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from . import services
from .models import PhrasebookEntry, TranslationJob, UnknownTranslationRecord
from .services.translation_dataset import TranslationDataset, SUPPORTED_LANGS
from .services.pipeline_service import PipelineService
from .services.translation_review import public_translation_status
from .services.language_detection_service import LanguageDetectionService, get_language_detection_service
from .services.detection_service import DetectionService
from .services.extraction_service import ExtractionService
from .services.reconstruction_service import ReconstructionService

RESOURCE = Path(__file__).parent / "services" / "translation_data.json"


def resource_rows():
    raw = json.loads(RESOURCE.read_text(encoding="utf-8-sig"))
    return copy.deepcopy(raw["rows"] if isinstance(raw, dict) else raw)


class MatchingIntegrityTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lingokatutubo-t06-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rows = resource_rows()[:4]

    def dataset(self, rows=None, **kwargs):
        path = self.root / "resources.json"
        path.write_text(json.dumps({"rows": self.rows if rows is None else rows}), encoding="utf-8")
        return TranslationDataset(str(path), data_mode="development_unverified", **kwargs)

    def test_all_twelve_directions_exact_and_review(self):
        data = self.dataset([self.rows[0]])
        for source in SUPPORTED_LANGS:
            for target in SUPPORTED_LANGS:
                if source == target:
                    continue
                with self.subTest(source=source, target=target):
                    result = data.translate_phrase_with_metadata(self.rows[0][source], source, target)
                    self.assertEqual(result["translated"], self.rows[0][target])
                    self.assertEqual(result["match_method"], "exact")
                    self.assertTrue(result["review_required"])
                    self.assertEqual(result["validation_status"], "unverified")
                    self.assertEqual(result["matched_entry_id"], self.rows[0]["id"])

    def test_language_aliases_use_correct_direction(self):
        data = self.dataset()
        for alias, canonical in [("bgs", "tagabawa"), ("Bagobo_Tagabawa", "tagabawa"),
                                 ("Tagalog", "filipino"), ("Bisaya", "cebuano"), ("en", "english")]:
            result = data.translate_phrase_with_metadata(self.rows[0][canonical], alias, "filipino")
            self.assertEqual(result["translated"], self.rows[0]["filipino"])

    def test_unknown_preserved_in_twelve_directions(self):
        data = self.dataset()
        original = "T06 qzxvkj untranslated 981723."
        for source in SUPPORTED_LANGS:
            for target in SUPPORTED_LANGS:
                if source != target:
                    result = data.translate_phrase_with_metadata(original, source, target)
                    self.assertEqual(result["translated"], original)
                    self.assertEqual(result["match_method"], "unknown")
                    self.assertTrue(result["review_required"])
                    self.assertIn("qzxvkj", result["unknown_tokens"])

    def test_missing_hello_is_retained_without_fabricating_an_entry(self):
        data = TranslationDataset(data_mode="development_unverified")
        for source in ["Hello", "Hello?"]:
            result = data.translate_phrase_with_metadata(source, "english", "tagabawa")
            self.assertEqual(result["translated"], source)
            self.assertEqual(result["match_method"], "unknown")
            self.assertTrue(result["review_required"])

    def test_normalized_match_is_still_unverified(self):
        result = self.dataset().translate_phrase_with_metadata("ALERT!", "en", "Tagalog")
        self.assertEqual(result["translated"], "Alisto!")
        self.assertEqual(result["match_method"], "normalized")
        self.assertTrue(result["needs_review"])

    def test_fuzzy_is_suggestion_even_for_verified_entry(self):
        row = dict(self.rows[1], validation_status="verified")
        result = self.dataset([row]).translate_phrase_with_metadata("abundantt", "english", "tagabawa")
        self.assertEqual(result["match_method"], "fuzzy")
        self.assertEqual(result["translated"], row["tagabawa"])
        self.assertTrue(result["review_required"])
        self.assertEqual(result["validation_status"], "verified")  # entry, not query, status
        self.assertLess(result["confidence"], 1)
        self.assertTrue(result["warnings"])

    def test_numbers_and_short_typos_do_not_fuzzy_match(self):
        data = self.dataset()
        for source in ["1234", "dax"]:
            result = data.translate_phrase_with_metadata(source, "english", "tagabawa")
            self.assertEqual(result["translated"], source)
            self.assertEqual(result["match_method"], "unknown")

    def test_conflicting_rows_preserve_source_in_both_orders(self):
        one = self.rows[0]
        other = dict(self.rows[1], english=one["english"])
        for rows in [[one, other], [other, one]]:
            result = self.dataset(rows).translate_phrase_with_metadata("alert", "english", "tagabawa")
            self.assertEqual(result["translated"], "alert")
            self.assertEqual(result["match_method"], "unknown")
            self.assertTrue(result["review_required"])
            self.assertIn("Conflicting", " ".join(result["warnings"]))

    def test_duplicate_rows_choose_stable_evidence(self):
        one = self.rows[0]
        other = dict(one, id="duplicate-copy", source="duplicate-copy")
        results = [self.dataset(rows).translate_phrase_with_metadata("alert", "english", "tagabawa")
                   for rows in [[one, other], [other, one]]]
        self.assertEqual(results[0], results[1])

    def test_fuzzy_skips_closest_row_missing_target(self):
        one = self.rows[1]
        other = dict(one, english="abundantt", tagabawa="")
        result = self.dataset([one, other]).translate_phrase_with_metadata("abundants", "english", "tagabawa")
        self.assertEqual(result["match_method"], "fuzzy")
        self.assertEqual(result["translated"], one["tagabawa"])

    def test_fuzzy_equal_score_conflicts_are_not_order_dependent(self):
        first = next(row for row in resource_rows() if len(row["english"]) > 24)
        query = first["english"]
        first = dict(first, english=query[:-1] + "x")
        other = dict(self.rows[0], english=query[:-1] + "z")
        for rows in [[first, other], [other, first]]:
            result = self.dataset(rows).translate_phrase_with_metadata(query, "english", "tagabawa")
            self.assertEqual(result["translated"], query)
            self.assertTrue(result["review_required"])

    def test_segmented_match_retains_component_review_and_attribution(self):
        result = self.dataset().translate_phrase_with_metadata("alert. abundant.", "english", "filipino")
        self.assertEqual(result["method"], "segmented_phrase")
        self.assertTrue(result["review_required"])
        self.assertEqual([r["matched_entry_id"] for r in result["components"]],
                         [self.rows[0]["id"], self.rows[1]["id"]])

    def test_verified_segment_components_keep_their_status(self):
        rows = [dict(row, validation_status="verified") for row in self.rows]
        result = self.dataset(rows).translate_phrase_with_metadata("alert. abundant.", "english", "filipino")
        self.assertEqual(result["method"], "segmented_phrase")
        self.assertFalse(result["review_required"])
        self.assertTrue(all(r["validation_status"] == "verified" for r in result["components"]))

    def test_cached_pipeline_refreshes_dataset_after_explicit_reset(self):
        from .services import pipeline_service as module
        original = self.dataset([self.rows[0]])
        replacement = self.dataset([self.rows[1]])
        pipeline = PipelineService.__new__(PipelineService)
        pipeline.translation_dataset = original
        with patch.object(module, "_pipeline_service", pipeline), patch.object(
                module, "get_translation_dataset", return_value=replacement):
            refreshed = module.get_pipeline_service()
        self.assertIs(refreshed.translation_dataset, replacement)
        self.assertIs(refreshed.language_service.dataset, replacement)

    def test_evaluation_is_reproducible_and_database_free(self):
        output = self.root / "report.json"
        call_command("evaluate_matching_resources", output=str(output), limit_per_direction=2)
        first = output.read_bytes()
        call_command("evaluate_matching_resources", output=str(output), limit_per_direction=2)
        self.assertEqual(output.read_bytes(), first)
        report = json.loads(first)
        self.assertEqual(report["exact_passed"], 24)
        self.assertIsNone(report["linguistic_accuracy"])
        self.assertEqual(len(report["directions"]), 12)

    def test_evaluation_cannot_overwrite_source_files(self):
        before = RESOURCE.read_bytes()
        with self.assertRaises(CommandError):
            call_command("evaluate_matching_resources", output=str(RESOURCE), limit_per_direction=1)
        self.assertEqual(RESOURCE.read_bytes(), before)

    def test_csv_preserves_validation_and_attribution_without_auto_approval(self):
        row = dict(self.rows[0], validation_status="verified", source_title="Copied test reference",
                   revision_number=7, needs_review="false", access_restriction="public")
        path = self.root / "resources.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
        data = TranslationDataset(str(path), data_mode="development_unverified")
        result = data.translate_phrase_with_metadata("alert", "english", "tagabawa")
        self.assertEqual(result["validation_status"], "verified")
        self.assertFalse(result["review_required"])
        self.assertEqual(result["runtime_approval_status"], "not_approved")
        self.assertEqual(result["matched_entry_revision"], 7)
        self.assertEqual(result["resource_metadata"]["source_title"], row["source_title"])

    def test_xlsx_preserves_same_metadata(self):
        from openpyxl import Workbook
        row = dict(self.rows[0], validation_status="verified", needs_review="true", revision_number=4)
        path = self.root / "resources.xlsx"
        book = Workbook()
        book.active.append(list(row))
        book.active.append(list(row.values()))
        book.save(path)
        book.close()
        result = TranslationDataset(str(path), data_mode="development_unverified").translate_phrase_with_metadata(
            "alert", "english", "tagabawa")
        self.assertTrue(result["review_required"])
        self.assertEqual(result["validation_status"], "verified")
        self.assertEqual(result["matched_entry_revision"], 4)

    def test_reloading_unavailable_source_clears_old_success(self):
        data = self.dataset()
        Path(data.dataset_path).unlink()
        data.load()
        self.assertFalse(data.is_loaded)
        self.assertEqual(data.data, [])
        self.assertEqual(data.translate_phrase("alert"), "alert")

    def test_unavailable_resources_stop_document_translation(self):
        data = self.dataset([])
        pipeline = PipelineService.__new__(PipelineService)
        pipeline.translation_dataset = data
        with self.assertRaisesRegex(RuntimeError, "resources are unavailable"):
            pipeline._translate_layout([{"blocks": []}], "english", "tagabawa")

    def test_identity_is_not_claimed_as_linguistic_verification(self):
        result = self.dataset().translate_phrase_with_metadata("alert", "english", "en")
        self.assertEqual(result["match_method"], "source_retained")
        self.assertEqual(result["validation_status"], "not_applicable")
        self.assertFalse(result["review_required"])

    def test_public_status_distinguishes_suggestion_from_retained_source(self):
        fuzzy = public_translation_status("fuzzy_match", .95, False)
        self.assertTrue(fuzzy["review_required"])
        self.assertNotIn("Original text retained", fuzzy["reason"])
        self.assertIn("Original text retained", public_translation_status("unknown", 0, True)["reason"])

    def test_language_detector_refreshes_replaced_dataset(self):
        from .services import language_detection_service as module
        original = self.dataset([self.rows[0]])
        replacement = self.dataset([self.rows[1]])
        with patch.object(module, "_service", LanguageDetectionService(original)):
            service = get_language_detection_service(replacement)
            self.assertIs(service.dataset, replacement)
            self.assertIn(self.rows[1]["tagabawa"], service.tagabawa_words)
            self.assertNotIn(self.rows[0]["tagabawa"], service.tagabawa_words)


class DatabaseResourceIntegrationTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lingokatutubo-t06-db-")
        self.addCleanup(self.temp.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.temp.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        connection_patch = patch("translator.services.close_old_connections")
        connection_patch.start()
        self.addCleanup(connection_patch.stop)
        self.user = get_user_model().objects.create_user("t06-isolated")
        self.row = resource_rows()[0]

    def entry(self, **extra):
        fields = {lang: self.row[lang] for lang in SUPPORTED_LANGS}
        fields.update(extra)
        return PhrasebookEntry.objects.create(**fields)

    def test_verified_only_remains_fail_closed(self):
        self.entry()
        data = TranslationDataset(data_mode="verified_only")
        self.assertFalse(data.is_loaded)
        self.assertEqual(data.translate_phrase("alert"), "alert")

    def test_approved_entry_requires_full_governance_and_keeps_source(self):
        entry = self.entry(validation_status="verified", is_approved_for_runtime=True,
                           source="Copied existing resource for policy test", source_title="Test policy fixture",
                           source_owner="Test fixture", license_status="permitted", access_restriction="public",
                           cultural_sensitivity_status="approved", required_reviews=0)
        result = TranslationDataset(data_mode="verified_only").translate_phrase_with_metadata("alert", "english", "filipino")
        self.assertEqual(result["translated"], self.row["filipino"])
        self.assertFalse(result["review_required"])
        self.assertEqual(result["resource_metadata"]["attribution"], entry.source)
        self.assertEqual(result["runtime_approval_status"], "approved")

    @override_settings(TRANSLATION_DATA_MODE="development_resources")
    def test_settings_mode_is_honored(self):
        self.entry()
        data = TranslationDataset()
        self.assertEqual(data.data_mode, "development_resources")
        self.assertEqual(len(data.data), 1)
        self.assertTrue(data.translate_phrase_with_metadata("alert")["review_required"])

    def test_database_outage_has_no_file_fallback(self):
        with patch.object(PhrasebookEntry.objects, "filter", side_effect=OperationalError("test unavailable")):
            for mode in ["verified_only", "development_resources"]:
                data = TranslationDataset(data_mode=mode)
                self.assertFalse(data.is_loaded)
                self.assertEqual(data.data, [])

    def test_quick_translation_resource_outage_is_safe_503(self):
        self.client.force_login(self.user)
        with patch("translator.services._get_translation_dataset", return_value=Mock(is_loaded=False)):
            response = self.client.post(reverse("translator:quick_translate"),
                                        json.dumps({"text": "alert", "source_language": "english",
                                                    "target_language": "filipino"}),
                                        content_type="application/json")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["ok"])
        self.assertNotIn("Traceback", response.content.decode())
        self.assertNotIn("translated", response.json())

    def test_quick_translation_keeps_unverified_review_status(self):
        self.client.force_login(self.user)
        data = TranslationDataset(str(RESOURCE), data_mode="development_unverified")
        with patch("translator.services._get_translation_dataset", return_value=data):
            response = self.client.post(reverse("translator:quick_translate"),
                                        json.dumps({"text": "alert", "source_language": "english",
                                                    "target_language": "filipino"}),
                                        content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["review_required"])
        self.assertNotIn("Original text retained", response.json()["reason"])

    def structure(self, method="unknown_for_review", needs_review=True):
        job = TranslationJob.objects.create(owner=self.user, original_filename="test.pdf", file_type="pdf",
                                            source_language="auto", target_language="filipino", status="processing")
        path = Path(self.temp.name) / "structure.json"
        path.write_text(json.dumps({"pages": [{"page_number": 1, "blocks": [{
            "type": "text", "lines": [{"source_text": "T06 qzxvkj untranslated", "translated_text": "T06 qzxvkj untranslated",
                                      "translation_method": method, "source_language": "english",
                                      "needs_review": needs_review, "review_required": needs_review,
                                      "matched_entry_id": self.row["id"], "validation_status": "unverified",
                                      "unknown_tokens": ["qzxvkj"], "resource_metadata": {"source": self.row["source"]}}]
        }]}]}), encoding="utf-8")
        return job, path

    def test_unknown_queue_links_segment_and_does_not_reset_review_decisions(self):
        job, path = self.structure()
        services._sync_structure_models(job.job_id, str(path), strict=True)
        record = UnknownTranslationRecord.objects.get(job=job)
        self.assertEqual(record.segment.source_language, "english")
        self.assertEqual(record.source_text, record.segment.source_text)
        self.assertTrue(record.segment.needs_review)
        record.review_status = "in_review"
        record.save()
        services._sync_structure_models(job.job_id, str(path), strict=True)
        record.refresh_from_db()
        self.assertEqual(record.review_status, "in_review")
        self.assertEqual(job.unknown_records.count(), 1)
        self.assertEqual(record.segment.metadata["unknown_tokens"], ["qzxvkj"])

    def test_fuzzy_and_unverified_review_flags_persist_without_unknown_queue(self):
        for method in ["exact_phrase", "fuzzy_match"]:
            job, path = self.structure(method=method)
            services._sync_structure_models(job.job_id, str(path), strict=True)
            segment = job.segments.get()
            self.assertTrue(segment.needs_review)
            self.assertEqual(segment.metadata["matched_entry_id"], self.row["id"])
            self.assertFalse(job.unknown_records.exists())

    def test_queue_failure_rolls_back_segments_with_completion_transaction(self):
        job, path = self.structure()
        with self.assertRaises(IntegrityError), transaction.atomic():
            with patch.object(UnknownTranslationRecord.objects, "get_or_create", side_effect=IntegrityError("test queue error")):
                services._sync_structure_models(job.job_id, str(path), strict=True)
        self.assertFalse(job.segments.exists())
        self.assertFalse(job.pages.exists())

    def test_real_native_pdf_to_atomic_completion_retains_evidence(self):
        pipeline = PipelineService.__new__(PipelineService)
        pipeline.file_service = services._get_file_service()
        pipeline.detection_service = DetectionService()
        pipeline.extraction_service = ExtractionService()
        pipeline.reconstruction_service = ReconstructionService()
        pipeline.translation_dataset = TranslationDataset(str(RESOURCE), data_mode="development_unverified")
        pipeline.language_service = LanguageDetectionService(pipeline.translation_dataset)
        pipeline.ocr_service = Mock()
        pipeline.jobs = {}
        pipeline.job_update_callback = services.sync_pipeline_job
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((72, 100), "alert")
            page.insert_text((72, 150), "T06 qzxvkj untranslated")
            content = pdf.tobytes()
        job = TranslationJob.objects.create(owner=self.user, original_filename="test.pdf", file_type="pdf",
                                            source_language="english", target_language="filipino")
        paths = services.save_uploaded_file(SimpleUploadedFile("test.pdf", content), job.job_id)
        job.input_file_path, job.upload_file_path = paths["input_file_path"], paths["upload_file_path"]
        job.save()
        with patch("translator.services._get_pipeline_service", return_value=pipeline):
            services._run_translation_job(job.job_id, job.input_file_path, "pdf", "english", "filipino", None)
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")
        segments = list(job.segments.all())
        self.assertEqual(len(segments), 2)
        self.assertTrue(all(s.needs_review for s in segments))
        self.assertEqual(segments[0].metadata["matched_entry_id"], self.row["id"])
        self.assertEqual(job.unknown_records.count(), 1)
        self.assertEqual(Path(job.upload_file_path).read_bytes(), content)
        with fitz.open(job.output_file_path) as output:
            self.assertIn("qzxvkj", output[0].get_text())
        self.assertEqual(pipeline.ocr_service.mock_calls, [])
