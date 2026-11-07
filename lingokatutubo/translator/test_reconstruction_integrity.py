"""T07 artifact-level checks; resource strings are copied, never linguistically approved."""
import base64
import hashlib
import io
import json
import os
import shutil
import tempfile
import unicodedata
from pathlib import Path
from unittest.mock import Mock, patch

import fitz
from docx import Document
from PIL import Image
from django.test import SimpleTestCase, TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from .services.reconstruction_service import ReconstructionService as Reconstruction
from .services.extraction_service import ExtractionService
from .services.pipeline_service import PipelineService
from .services.translation_dataset import TranslationDataset
from .services.models import FileType


class ReconstructionIntegrityTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lingokatutubo-t07-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = TranslationDataset(data_mode="development_unverified")
        self.service = PipelineService.__new__(PipelineService)
        self.service.reconstruction_service = Reconstruction()
        self.service.translation_dataset = self.dataset
        self.image = io.BytesIO()
        Image.new("RGB", (48, 24), color=(30, 140, 80)).save(self.image, "PNG")

    def export(self, *paths):
        target = os.environ.get("LINGOKATUTUBO_T07_ARTIFACT_DIR")
        if target:
            folder = Path(target) / self._testMethodName
            folder.mkdir(parents=True, exist_ok=True)
            for path in paths:
                shutil.copyfile(path, folder / Path(path).name)

    def source(self, texts=("alert",), image=False, grid=False):
        source = self.root / "source.pdf"
        with fitz.open() as document:
            for text in texts:
                page = document.new_page(width=612, height=792)
                page.insert_text((72, 100), text, fontsize=12)
                if image:
                    page.insert_image(fitz.Rect(72, 220, 168, 268), stream=self.image.getvalue())
                if grid:
                    for x in [60, 250, 450]:
                        page.draw_line((x, 60), (x, 180), color=(0, 0, 0))
                    for y in [60, 120, 180]:
                        page.draw_line((60, y), (450, y), color=(0, 0, 0))
            document.save(source)
        return source

    def render(self, source, records, layout=None):
        layout = layout or ExtractionService.extract_pdf_text_and_layout(str(source))
        output = self.root / "translated.pdf"
        warnings = []
        before = source.read_bytes()
        ok = Reconstruction.reconstruct_pdf(str(source), layout, records, str(output), layout_warnings=warnings)
        self.assertEqual(source.read_bytes(), before)
        return ok, output, warnings

    def test_short_exact_translation_and_review_note(self):
        source = self.source()
        record = self.dataset.translate_phrase_with_metadata("alert", "english", "filipino")
        ok, output, warnings = self.render(source, {"alert": record})
        self.assertTrue(ok, warnings)
        with fitz.open(output) as pdf:
            self.assertIn("alisto", pdf[0].get_text())
            self.assertTrue(any("validation" in a.info["content"] for a in pdf[0].annots()))
        self.export(source, output)

    def test_long_translation_is_complete_and_reports_expansion(self):
        source = self.source()
        text = "This translated phrase is deliberately much longer than the original source region. " * 3
        ok, output, warnings = self.render(source, {"alert": text})
        self.assertTrue(ok, warnings)
        with fitz.open(output) as pdf:
            self.assertIn("".join(text.split()), "".join(pdf[0].get_text().split()))
        self.assertTrue(any("overflowed" in w for w in warnings))
        self.export(source, output)

    def test_unmatched_source_survives_with_persistent_review_indicator(self):
        source = self.source(("Unmatched qzxvjk expression",))
        text = "Unmatched qzxvjk expression"
        record = self.dataset.translate_phrase_with_metadata(text, "english", "tagabawa")
        ok, output, warnings = self.render(source, {text: record})
        self.assertTrue(ok, warnings)
        with fitz.open(output) as pdf:
            self.assertIn(text, pdf[0].get_text())
            self.assertNotIn("[UNKNOWN_FOR_REVIEW]", pdf[0].get_text())
            self.assertTrue(any("Original text retained" in a.info["content"] for a in pdf[0].annots()))
        self.export(source, output)

    def test_fuzzy_suggestion_retains_review_note(self):
        source = self.source(("abundantt",))
        record = self.dataset.translate_phrase_with_metadata("abundantt", "english", "filipino")
        self.assertEqual(record["match_method"], "fuzzy")
        self.assertTrue(record["review_required"])
        ok, output, warnings = self.render(source, {"abundantt": record})
        self.assertTrue(ok, warnings)
        with fitz.open(output) as pdf:
            self.assertIn(record["translated"], pdf[0].get_text())
            self.assertTrue(any("Suggested translation" in a.info["content"] for a in pdf[0].annots()))
        self.export(source, output)

    def test_legacy_missing_translation_markers_still_carry_review_notes(self):
        source = self.source()
        for record in ["[UNKNOWN_FOR_REVIEW]", {"translated": "[UNKNOWN_FOR_REVIEW]"}]:
            ok, output, warnings = self.render(source, {"alert": record})
            self.assertTrue(ok, warnings)
            with fitz.open(output) as pdf:
                self.assertIn("alert", pdf[0].get_text())
                self.assertNotIn("[UNKNOWN_FOR_REVIEW]", pdf[0].get_text())
                self.assertTrue(any("Original text retained" in a.info["content"] for a in pdf[0].annots()))

    def test_legacy_image_output_keeps_source_mask_without_covering_other_pixels(self):
        from PIL import ImageChops, ImageDraw
        path = self.root / "source.png"
        source = Image.new("RGB", (200, 120), (20, 40, 160))
        drawing = ImageDraw.Draw(source)
        drawing.text((20, 20), "alert", fill="white")
        drawing.text((100, 20), "NEIGHBOR", fill="white")
        drawing.rectangle((100, 65, 190, 100), fill=(30, 140, 80))
        source.save(path)
        before = path.read_bytes()
        layout = [{"width": 200, "height": 120, "blocks": [{"type": "text",
                   "bbox": [20, 20, 90, 45], "lines": [
                       {"text": "alert", "bbox": [20, 20, 90, 45], "size": 12}]}]}]
        output = self.root / "translated.pdf"
        records = {"alert": self.dataset.translate_phrase_with_metadata("alert", "english", "filipino")}
        self.assertTrue(self.service._create_output_pdf(layout, records, str(output),
                       input_file_path=str(path), file_type=FileType.PNG))
        self.assertEqual(path.read_bytes(), before)
        # A clean, white-page render gives an independent source-free reference
        # for every pixel in the source region, including underneath new glyphs.
        control = self.root / "control.pdf"
        self.assertTrue(self.service._create_output_pdf(layout, records, str(control)))
        with fitz.open(output) as pdf, fitz.open(control) as clean:
            self.assertIn("alisto", pdf[0].get_text())
            region = fitz.Rect(20, 20, 90, 45)
            actual = pdf[0].get_pixmap(clip=region, annots=False)
            expected = clean[0].get_pixmap(clip=region, annots=False)
            self.assertEqual(actual.samples, expected.samples, "Source glyph ghosting remains")
            self.assertNotEqual(expected.samples, b"\xff" * len(expected.samples),
                                "Translated glyphs must actually be visible")
            # Ignore only the original region's existing 0.75pt padding. All
            # remaining pixels, including adjacent raster text, must be exact.
            rendered = pdf[0].get_pixmap(annots=False)
            actual_image = Image.frombytes("RGB", (rendered.width, rendered.height), rendered.samples)
            difference = ImageChops.difference(actual_image, source)
            ImageDraw.Draw(difference).rectangle((19, 19, 91, 46), fill="black")
            self.assertIsNone(difference.getbbox(), "Pixels outside the source mask changed")
            embedded = pdf.extract_image(pdf[0].get_images()[0][0])["image"]
            self.assertEqual(Image.open(io.BytesIO(embedded)).convert("RGB").tobytes(), source.tobytes())
            pdf[0].get_pixmap(matrix=fitz.Matrix(3, 3)).save(self.root / "page-1.png")
        self.export(path, output, self.root / "page-1.png")

    def test_legacy_image_output_rejects_invalid_boxes_and_unfittable_text(self):
        path = self.root / "source.png"
        Image.new("RGB", (200, 120), (20, 40, 160)).save(path)
        before = path.read_bytes()
        for index, (bbox, text) in enumerate([
            (None, "alisto"),
            ([0, 0, 0, 0], "alisto"),
            ([20, 20, 20, 45], "alisto"),
            ([20, 20, 90, 20], "alisto"),
            ([20, 20, float("nan"), 45], "alisto"),
            ([20, 20, float("inf"), 45], "alisto"),
            ([-30, -30, -10, -10], "alisto"),
            ([300, 300, 350, 350], "alisto"),
            ([20, 20, 90, 45], "Complete translated content " * 100),
        ]):
            with self.subTest(bbox=bbox, overflow=len(text) > 100):
                layout = [{"width": 200, "height": 120, "blocks": [{"type": "text",
                           "bbox": bbox, "lines": [{"text": "alert", "bbox": bbox, "size": 12}]}]}]
                output = self.root / f"unsafe-{index}.pdf"
                warnings = []
                self.assertFalse(self.service._create_output_pdf(
                    layout, {"alert": {"translated": text}}, str(output),
                    input_file_path=str(path), file_type=FileType.PNG, layout_warnings=warnings))
                self.assertFalse(output.exists())
                self.assertTrue(any("not completed" in w for w in warnings), warnings)
                self.assertEqual(path.read_bytes(), before)

    def test_conflict_preserves_original_and_review_indicator(self):
        source = self.source(("Sit down",))
        record = self.dataset.translate_phrase_with_metadata("Sit down", "english", "tagabawa")
        self.assertEqual(record["match_method"], "unknown")
        ok, output, warnings = self.render(source, {"Sit down": record})
        self.assertTrue(ok, warnings)
        with fitz.open(output) as pdf:
            self.assertIn("Sit down", pdf[0].get_text())
            self.assertTrue(list(pdf[0].annots()))
        self.export(source, output)

    def test_accented_and_combining_orthography_survives(self):
        source = self.source(("Visiting",))
        target = self.dataset.translate_phrase("Visiting", "english", "tagabawa")
        ok, output, warnings = self.render(source, {"Visiting": unicodedata.normalize("NFD", target)})
        self.assertTrue(ok, warnings)
        with fitz.open(output) as pdf:
            self.assertIn(unicodedata.normalize("NFC", target), unicodedata.normalize("NFC", pdf[0].get_text()))
            self.assertNotIn("?", pdf[0].get_text())
            self.assertTrue(any(font[1] in {"ttf", "otf"} for font in pdf[0].get_fonts()))
        self.export(source, output)

    def test_multipage_images_and_grid_survive(self):
        source = self.source(("alert", "abundant"), image=True, grid=True)
        layout = ExtractionService.extract_pdf_text_and_layout(str(source))
        records = self.service._translate_layout(layout, "english", "filipino")
        ok, output, warnings = self.render(source, records, layout)
        self.assertTrue(ok, warnings)
        with fitz.open(source) as original, fitz.open(output) as pdf:
            self.assertEqual(len(pdf), len(original))
            for i, page in enumerate(pdf):
                self.assertEqual(page.rect, original[i].rect)
                for drawing in original[i].get_drawings():
                    self.assertIn(drawing["items"], [d["items"] for d in page.get_drawings()])
                self.assertEqual(pdf.extract_image(page.get_images()[0][0])["image"],
                                 original.extract_image(original[i].get_images()[0][0])["image"])
                self.assertEqual(page.get_pixmap(clip=fitz.Rect(72, 220, 168, 268)).samples,
                                 original[i].get_pixmap(clip=fitz.Rect(72, 220, 168, 268)).samples)
        self.export(source, output)

    def test_fitting_flags_are_accurate_without_deleting_words(self):
        for text, rect, expected in [
            ("alert", fitz.Rect(0, 0, 200, 24), (False, False)),
            ("alert", fitz.Rect(0, 0, 25, 14), (True, False)),
            ("This translation cannot fit", fitz.Rect(0, 0, 12, 12), (True, True)),
        ]:
            fitted, _, shrunk, overflow = Reconstruction._fit_text_to_rect(text, rect, "helv", 12)
            self.assertEqual((shrunk, overflow), expected)
            self.assertEqual("".join(fitted.split()), "".join(text.split()))

    def test_no_partial_success_when_text_exceeds_page(self):
        source = self.source()
        ok, output, warnings = self.render(source, {"alert": "Complete translated text " * 500})
        self.assertFalse(ok)
        self.assertFalse(output.exists())
        self.assertTrue(any("not completed" in w for w in warnings))

    def test_neighboring_content_cannot_be_overwritten_by_expansion(self):
        source = self.root / "source.pdf"
        with fitz.open() as pdf:
            page = pdf.new_page(width=320, height=220)
            page.insert_text((40, 70), "alert")
            page.insert_text((40, 90), "Protected next line")
            pdf.save(source)
        ok, output, warnings = self.render(source, {"alert": "Translated content " * 150,
                                                  "Protected next line": "Protected next line"})
        self.assertFalse(ok)
        self.assertFalse(output.exists())
        self.assertTrue(any("not completed" in w for w in warnings))

    def test_font_failure_does_not_substitute_source_or_claim_success(self):
        with fitz.open() as pdf:
            page = pdf.new_page()
            with patch.object(Reconstruction, "_font_candidates_for_line", return_value=[]):
                warnings = []
                ok = Reconstruction._insert_text_in_rect(page, fitz.Rect(72, 100, 200, 130),
                     "translated words", {}, warnings, 1, 1, 1, fallback_text="original words")
            self.assertFalse(ok)
            self.assertNotIn("original words", page.get_text())

    def test_unsupported_unicode_font_fails_without_replacing_orthography(self):
        with fitz.open() as pdf:
            page = pdf.new_page()
            with patch.object(Reconstruction, "_unicode_fontfile", return_value=None):
                warnings = []
                ok = Reconstruction._insert_text_in_rect(page, fitz.Rect(72, 100, 200, 130),
                     "kann\u0119", {}, warnings, 1, 1, 1)
            self.assertFalse(ok)
            self.assertNotIn("?", page.get_text())
            self.assertTrue(any("no Unicode PDF font" in w and "not completed" in w for w in warnings))

    def test_docx_tables_inline_images_and_text_keep_body_order(self):
        path = self.root / "source.docx"
        doc = Document()
        doc.add_paragraph("alert")
        table = doc.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "abundant"
        table.cell(0, 1).text = "Unmatched qzxvjk expression"
        doc.add_picture(io.BytesIO(self.image.getvalue()))
        doc.add_paragraph("Visiting")
        doc.save(path)
        before = path.read_bytes()
        layout = ExtractionService.extract_docx_text_and_layout(str(path))
        records = self.service._translate_layout(layout, "english", "filipino")
        output = self.root / "translated.pdf"
        warnings = []
        self.assertTrue(self.service._create_output_pdf(layout, records, str(output),
                        file_type=FileType.DOCX, layout_warnings=warnings), warnings)
        self.assertEqual(path.read_bytes(), before)
        with fitz.open(output) as pdf:
            content = "".join(p.get_text() for p in pdf)
            for term in ["alert", "abundant", "Unmatched qzxvjk expression", "Visiting"]:
                expected = self.dataset.translate_phrase(term, "english", "filipino")
                self.assertIn(expected, content)
            self.assertLess(content.index("alisto"), content.index("sagana"))
            self.assertEqual(sum(len(p.get_images()) for p in pdf), 1)
            self.assertTrue(any(list(p.annots()) for p in pdf))
        self.assertTrue(any("table borders" in w for w in warnings))
        self.export(path, output)

    def test_docx_long_translations_paginate_without_clipping(self):
        path = self.root / "source.docx"
        doc = Document()
        for _ in range(3):
            doc.add_paragraph("alert")
        doc.save(path)
        layout = ExtractionService.extract_docx_text_and_layout(str(path))
        text = "This translated content must remain complete. " * 100
        records = {"alert": {"translated": text, "method": "exact_phrase", "needs_review": True}}
        output = self.root / "translated.pdf"
        warnings = []
        self.assertTrue(self.service._create_output_pdf(layout, records, str(output),
                        file_type=FileType.DOCX, layout_warnings=warnings), warnings)
        with fitz.open(output) as pdf:
            self.assertGreater(len(pdf), 1)
            actual = "".join("".join(p.get_text().split()) for p in pdf)
            self.assertEqual(actual.count("".join(text.split())), 3)
        self.export(path, output)


class ReconstructionPersistenceTests(TestCase):
    def setUp(self):
        from . import services
        from .services.language_detection_service import LanguageDetectionService
        from .services.detection_service import DetectionService
        self.services = services
        self.temp = tempfile.TemporaryDirectory(prefix="lingokatutubo-t07-db-")
        self.addCleanup(self.temp.cleanup)
        settings_override = override_settings(MEDIA_ROOT=self.temp.name,
                                              LINGOKATUTUBO_NEURAL_TRANSLATION_ENABLED=False)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        connections = patch("translator.services.close_old_connections")
        connections.start()
        self.addCleanup(connections.stop)
        self.user = get_user_model().objects.create_user("t07-test-only")
        self.pipeline = PipelineService.__new__(PipelineService)
        self.pipeline.file_service = services._get_file_service()
        self.pipeline.detection_service = DetectionService()
        self.pipeline.extraction_service = ExtractionService()
        self.pipeline.reconstruction_service = Reconstruction()
        self.pipeline.translation_dataset = TranslationDataset(data_mode="development_unverified")
        self.pipeline.language_service = LanguageDetectionService(self.pipeline.translation_dataset)
        self.pipeline.ocr_service = Mock()
        self.pipeline.jobs = {}
        self.pipeline.job_update_callback = services.sync_pipeline_job

    def run_job(self, name, content, target="filipino"):
        from .models import TranslationJob
        job = TranslationJob.objects.create(owner=self.user, original_filename=name,
                    file_type=Path(name).suffix[1:], source_language="english", target_language=target)
        paths = self.services.save_uploaded_file(SimpleUploadedFile(name, content), job.job_id)
        job.input_file_path, job.upload_file_path = paths["input_file_path"], paths["upload_file_path"]
        job.save()
        with patch("translator.services._get_pipeline_service", return_value=self.pipeline):
            self.services._run_translation_job(job.job_id, job.input_file_path, job.file_type, "english", target, None)
        job.refresh_from_db()
        self.assertEqual(Path(job.upload_file_path).read_bytes(), content)
        self.assertEqual(self.pipeline.ocr_service.mock_calls, [])
        return job

    def test_docx_table_and_image_reach_atomic_completion_with_review_metadata(self):
        path = Path(self.temp.name) / "fixture.docx"
        document = Document()
        document.add_paragraph("alert")
        document.add_table(rows=1, cols=1).cell(0, 0).text = "T07 unmatched qzxvjk"
        image = io.BytesIO()
        Image.new("RGB", (24, 24), "green").save(image, "PNG")
        document.add_picture(io.BytesIO(image.getvalue()))
        document.save(path)
        job = self.run_job("fixture.docx", path.read_bytes())
        self.assertEqual(job.status, "completed", job.error)
        self.assertTrue(all(s.needs_review for s in job.segments.all()))
        self.assertEqual(job.unknown_records.count(), 1)
        self.assertTrue(job.segments.first().metadata.get("matched_entry_id"))
        self.assertTrue(job.generated_outputs.exists())
        self.assertTrue(any("table borders" in w for w in job.metadata["layout_warnings"]))
        with fitz.open(job.output_file_path) as pdf:
            self.assertIn("alisto", "".join(p.get_text() for p in pdf))
            self.assertEqual(sum(len(p.get_images()) for p in pdf), 1)

    def test_unrenderable_translation_is_failed_without_publishing_partial_completion(self):
        with fitz.open() as pdf:
            pdf.new_page().insert_text((72, 100), "alert")
            content = pdf.tobytes()
        records = {"0_0_0": {"original": "alert", "translated": "Complete translation " * 500,
                            "method": "exact_phrase", "needs_review": True}}
        with patch.object(self.pipeline, "_translate_layout", return_value=records):
            job = self.run_job("fixture.pdf", content)
        self.assertEqual(job.status, "failed")
        self.assertTrue(any("not completed" in w or "no replacement" in w for w in job.metadata["layout_warnings"]))
        self.assertFalse(job.generated_outputs.filter(output_type="translated_pdf").exists())
        self.assertNotIn("Traceback", job.phase_message)

    def test_paginated_docx_reaches_atomic_completion_with_more_output_pages(self):
        path = Path(self.temp.name) / "long.docx"
        document = Document()
        for _ in range(3):
            document.add_paragraph("alert")
        document.save(path)
        text = "Complete translated content must remain visible. " * 100
        records = {"alert": {"translated": text, "method": "layout_test_fixture", "needs_review": True}}
        with patch.object(self.pipeline, "_translate_layout", return_value=records):
            job = self.run_job("long.docx", path.read_bytes())
        self.assertEqual(job.status, "completed", job.error)
        self.assertGreater(job.metadata["translated_page_count"], job.metadata["layout_page_count"])
        self.assertEqual(job.segments.count(), 3)
        self.assertTrue(all(s.needs_review for s in job.segments.all()))
        with fitz.open(job.output_file_path) as pdf:
            actual = "".join("".join(p.get_text().split()) for p in pdf)
            self.assertEqual(actual.count("".join(text.split())), 3)
