"""Generated review notes stay inspectable without obscuring learner pages.

All language strings come from existing development resources. Matching and
review policy are exercised, not replaced or linguistically approved here.
"""
import copy
import io
import tempfile
import unicodedata
from pathlib import Path

import fitz
from docx import Document
from PIL import Image
from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .services.extraction_service import ExtractionService
from .services.models import FileType
from .services.pipeline_service import PipelineService
from .services.reconstruction_service import ReconstructionService as Reconstruction
from .services.translation_dataset import TranslationDataset
from . import test_reconstruction_integrity as reconstruction_fixtures


TERMS = ("alert", "abundantt", "Sit down", "Unmatched qzxvjk expression", "Visiting")


def render_usage(page, usage):
    """Run MuPDF's actual PDF View/Print paths, including annotations."""
    pixmap = fitz.Pixmap(fitz.csRGB, page.rect.irect, 0)
    pixmap.clear_with(255)
    matrix = fitz.mupdf.FzMatrix(1, 0, 0, 1, 0, 0)
    device = fitz.mupdf.fz_new_draw_device(matrix, pixmap.this)
    try:
        fitz.mupdf.pdf_run_page_with_usage(
            fitz.mupdf.pdf_page_from_fz_page(page.this), device,
            matrix, usage, fitz.mupdf.FzCookie(),
        )
        fitz.mupdf.fz_close_device(device)
    finally:
        del device
    return pixmap


def assert_hidden_notes(test, page):
    notes = [a for a in page.annots() or [] if a.info.get("title") == "Translation review"]
    test.assertTrue(notes)
    for note in notes:
        test.assertTrue(note.flags & fitz.PDF_ANNOT_IS_HIDDEN)
        test.assertTrue(note.flags & fitz.PDF_ANNOT_IS_NO_VIEW)
        test.assertFalse(note.flags & fitz.PDF_ANNOT_IS_PRINT)
        test.assertIn("validation", note.info["content"])
    clean = page.get_pixmap(annots=False).samples
    test.assertEqual(page.get_pixmap(annots=True).samples, clean)
    # Compare each usage with the same renderer. get_pixmap and the low-level
    # draw device use different antialiasing / color-conversion defaults.
    for usage in ("View", "Print"):
        test.assertEqual(render_usage(page, usage).samples,
                         render_without_annotations(page, usage).samples)


def render_without_annotations(page, usage):
    """Annotation-free in-memory control; never edits or saves the source."""
    with fitz.open(stream=page.parent.tobytes(), filetype="pdf") as control:
        clean_page = control[page.number]
        for note in list(clean_page.annots() or []):
            clean_page.delete_annot(note)
        return render_usage(clean_page, usage)


class PdfReviewVisibilityTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pdf-review-visibility-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = TranslationDataset(data_mode="development_unverified")
        self.records = {text: self.dataset.translate_phrase_with_metadata(
            text, "english", "tagabawa") for text in TERMS}

    def source(self, author_note=False):
        path = self.root / "source.pdf"
        with fitz.open() as doc:
            for terms in (TERMS[:3], TERMS[3:]):
                page = doc.new_page(width=612, height=792)
                for index, text in enumerate(terms):
                    page.insert_text((72, 100 + 60 * index), text, fontsize=12)
                stream = io.BytesIO()
                Image.new("RGB", (30, 20), "green").save(stream, "PNG")
                page.insert_image(fitz.Rect(72, 350, 132, 390), stream=stream.getvalue())
                if author_note:
                    note = page.add_text_annot((300, 400), "Original author's note")
                    note.set_info(title="Original author")
                    note.update()
            doc.save(path)
        return path

    def test_native_all_review_outcomes_hide_notes_for_view_and_print(self):
        source = self.source()
        source_bytes = source.read_bytes()
        original_records = copy.deepcopy(self.records)
        output = self.root / "translated.pdf"
        warnings = []
        self.assertTrue(Reconstruction.reconstruct_pdf(
            str(source), ExtractionService.extract_pdf_text_and_layout(str(source)),
            self.records, str(output), layout_warnings=warnings), warnings)
        self.assertEqual(self.records, original_records)
        self.assertTrue(all(r["needs_review"] and r["validation_status"] == "unverified"
                            for r in self.records.values()))
        self.assertEqual(self.records["abundantt"]["match_method"], "fuzzy")
        self.assertEqual(self.records["Sit down"]["match_method"], "unknown")
        self.assertTrue(any("validation" in w for w in warnings))
        with fitz.open(output) as doc:
            self.assertEqual(len(doc), 2)
            text = unicodedata.normalize("NFC", "".join(p.get_text() for p in doc))
            for record in self.records.values():
                self.assertIn(unicodedata.normalize("NFC", record["translated"]), text)
            self.assertIn("Sit down", text)
            self.assertIn("Unmatched qzxvjk expression", text)
            for page in doc:
                assert_hidden_notes(self, page)
                self.assertEqual(len(page.get_images()), 1)
        self.assertEqual(source.read_bytes(), source_bytes)

    def test_docx_paginated_output_keeps_text_images_and_hidden_notes(self):
        source = self.root / "source.docx"
        document = Document()
        for _ in range(9):
            for text in TERMS:
                document.add_paragraph(text)
        document.add_table(rows=1, cols=1).cell(0, 0).text = "alert"
        stream = io.BytesIO()
        Image.new("RGB", (30, 20), "green").save(stream, "PNG")
        document.add_picture(io.BytesIO(stream.getvalue()))
        document.save(source)
        before = source.read_bytes()
        layout = ExtractionService.extract_docx_text_and_layout(str(source))
        output = self.root / "translated.pdf"
        warnings = []
        self.assertTrue(Reconstruction.create_docx_pdf(layout, self.records, str(output), warnings), warnings)
        with fitz.open(output) as doc:
            self.assertGreater(len(doc), 1)
            self.assertEqual(sum(len(p.get_images()) for p in doc), 1)
            for page in doc:
                assert_hidden_notes(self, page)
            self.assertEqual("".join(p.get_text() for p in doc).count("Unmatched qzxvjk expression"), 9)
        self.assertTrue(any("table borders" in w for w in warnings))
        self.assertEqual(source.read_bytes(), before)

    def test_image_backed_compatibility_uses_same_hidden_note_policy(self):
        source = self.root / "image.png"
        Image.new("RGB", (300, 200), (230, 242, 234)).save(source)
        before = source.read_bytes()
        pipeline = PipelineService.__new__(PipelineService)
        pipeline.reconstruction_service = Reconstruction()
        layout = [{"width": 300, "height": 200, "blocks": [{"type": "text",
            "lines": [{"text": "alert", "bbox": [30, 30, 150, 55], "size": 12}]}]}]
        output = self.root / "translated.pdf"
        self.assertTrue(pipeline._create_output_pdf(layout, self.records, str(output),
            input_file_path=str(source), file_type=FileType.PNG))
        with fitz.open(output) as doc:
            assert_hidden_notes(self, doc[0])
            self.assertIn(self.records["alert"]["translated"], doc[0].get_text())
            self.assertEqual(len(doc[0].get_images()), 1)
        self.assertEqual(source.read_bytes(), before)

    def test_source_authors_annotations_are_not_removed_or_hidden(self):
        source = self.source(author_note=True)
        before = source.read_bytes()
        output = self.root / "translated.pdf"
        self.assertTrue(Reconstruction.reconstruct_pdf(str(source),
            ExtractionService.extract_pdf_text_and_layout(str(source)), self.records, str(output)))
        with fitz.open(output) as doc:
            for page in doc:
                author = [a for a in page.annots() or [] if a.info.get("title") == "Original author"]
                self.assertEqual(len(author), 1)
                self.assertFalse(author[0].flags & fitz.PDF_ANNOT_IS_HIDDEN)
                self.assertTrue(author[0].flags & fitz.PDF_ANNOT_IS_PRINT)
                generated = [a for a in page.annots() or [] if a.info.get("title") == "Translation review"]
                self.assertTrue(generated)
                self.assertTrue(all(a.flags & fitz.PDF_ANNOT_IS_HIDDEN for a in generated))
        self.assertEqual(source.read_bytes(), before)

    def test_view_and_print_pixel_checks_detect_visible_note_control(self):
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((72, 100), "alert")
            note = page.add_text_annot((300, 100), "Visible control note")
            note.set_flags(fitz.PDF_ANNOT_IS_PRINT)
            note.update()
            for usage in ("View", "Print"):
                self.assertNotEqual(render_usage(page, usage).samples,
                                    render_without_annotations(page, usage).samples)


class PdfReviewPersistenceTests(TestCase):
    # Reuse the existing isolated pipeline fixture, not its test methods.
    setUp = reconstruction_fixtures.ReconstructionPersistenceTests.setUp
    run_job = reconstruction_fixtures.ReconstructionPersistenceTests.run_job

    def run_review_job(self, kind="pdf"):
        if kind == "pdf":
            with fitz.open() as doc:
                page = doc.new_page()
                for index, text in enumerate(TERMS):
                    page.insert_text((72, 90 + 60 * index), text)
                content = doc.tobytes()
        else:
            path = Path(self.temp.name) / "source.docx"
            document = Document()
            for text in TERMS:
                document.add_paragraph(text)
            document.save(path)
            content = path.read_bytes()
        job = self.run_job("review." + kind, content, target="tagabawa")
        self.assertEqual(job.status, "completed", job.error)
        return job

    def test_pipeline_persists_unverified_provenance_and_unknown_links(self):
        job = self.run_review_job()
        segments = list(job.segments.order_by("segment_index"))
        self.assertEqual(len(segments), len(TERMS))
        for segment in segments:
            expected = self.pipeline.translation_dataset.translate_phrase_with_metadata(
                segment.source_text, "english", "tagabawa")
            self.assertTrue(segment.needs_review)
            self.assertEqual(segment.metadata["validation_status"], "unverified")
            for key in ("matched_entry_id", "provenance_status", "resource_metadata", "warnings"):
                self.assertEqual(segment.metadata.get(key), expected.get(key))
        self.assertEqual(job.unknown_records.count(), 2)
        for unknown in job.unknown_records.select_related("segment"):
            self.assertEqual(unknown.segment.job_id, job.pk)
            self.assertTrue(unknown.segment.needs_review)
            self.assertEqual(unknown.review_status, "pending")
        self.assertTrue(any("validation" in w for w in job.metadata["layout_warnings"]))
        with fitz.open(job.output_file_path) as doc:
            for page in doc:
                assert_hidden_notes(self, page)

    def test_learner_denied_and_authorized_validator_and_admin_keep_review_access(self):
        job = self.run_review_job("docx")
        url = reverse("translator:review_manifest", args=[job.pk])
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(codename="review_language_entry"))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("unverified", body)
        self.assertIn("Unmatched qzxvjk expression", body)
        self.assertIn("provenance_status", body)
        self.assertEqual(self.client.get(reverse("translator:validator_queue")).status_code, 200)
        self.user.user_permissions.clear()
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(job.unknown_records.count(), 2)
        self.assertTrue(all(s.needs_review for s in job.segments.all()))
