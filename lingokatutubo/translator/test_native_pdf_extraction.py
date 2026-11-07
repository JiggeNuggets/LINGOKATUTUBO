"""Native PDF routing and pipeline regressions with temporary files and no DB."""

import base64
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import fitz
from django.test import SimpleTestCase

from .services.detection_service import DetectionService
from .services.extraction_service import ExtractionService
from .services.file_service import FileService
from .services.language_detection_service import LanguageDetectionService
from .services.models import DetectionType, FileType
from .services.pipeline_service import JobStatus, PipelineService
from .services.reconstruction_service import ReconstructionService
from .services.translation_dataset import TranslationDataset


class NativePdfExtractionTests(SimpleTestCase):
    """Use real PDF extraction/reconstruction and existing file-backed entries."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dataset = TranslationDataset(
            dataset_path=str(Path(__file__).parent / "services" / "translation_data.json"),
            include_default_corpus=False,
            include_validated_imports=False,
            data_mode="development_unverified",
        )

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lingokatutubo-native-pdf-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.pipeline = PipelineService.__new__(PipelineService)
        self.pipeline.file_service = FileService(upload_dir=str(self.root), storage_layout="legacy")
        self.pipeline.detection_service = DetectionService()
        self.pipeline.extraction_service = ExtractionService()
        self.pipeline.reconstruction_service = ReconstructionService()
        self.pipeline.translation_dataset = self.dataset
        self.pipeline.language_service = LanguageDetectionService(self.dataset)
        self.pipeline.jobs = {}
        self.pipeline.job_update_callback = None
        self.pipeline.ocr_service = Mock(
            dpi=72, low_confidence_threshold=0.60, _compute_page_ocr_summary=None,
        )
        for name in ("resolve_tesseract_language", "_ocr_image", "extract_pdf_text_and_layout", "is_available"):
            getattr(self.pipeline.ocr_service, name).side_effect = AssertionError(
                "Native PDF processing must not invoke OCR"
            )

    def write_pdf(self, texts, *, image=False):
        path = self.root / "source.pdf"
        with fitz.open() as doc:
            for page_index, text in enumerate(texts):
                page = doc.new_page(width=612, height=792)
                if text:
                    page.insert_text((72, 100), text, fontsize=12)
                if image is True or (isinstance(image, set) and page_index in image):
                    pixel = base64.b64decode(
                        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/"
                        "x8AAwMCAO+j/csAAAAASUVORK5CYII="
                    )
                    page.insert_image(fitz.Rect(72, 160, 152, 240), stream=pixel)
                    page.draw_rect(fitz.Rect(200, 160, 300, 240), color=(1, 0, 0))
            doc.save(path)
        return path

    def extract(self, path):
        job = JobStatus("isolated-extraction")
        layout, error = self.pipeline._extract_hybrid_pdf(str(path), ["eng"], job)
        self.assertIsNone(error)
        return layout, job

    def run_pipeline(self, path):
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        with patch.object(self.pipeline, "_translate_layout", wraps=self.pipeline._translate_layout) as translate:
            ok = self.pipeline.process_translation(
                "isolated-pipeline", str(path), FileType.PDF,
                source_language="english", target_language="filipino",
            )
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
        return ok, self.pipeline.jobs["isolated-pipeline"], translate

    def assert_no_ocr(self):
        self.pipeline.ocr_service.resolve_tesseract_language.assert_not_called()
        self.pipeline.ocr_service._ocr_image.assert_not_called()
        self.pipeline.ocr_service.extract_pdf_text_and_layout.assert_not_called()
        self.pipeline.ocr_service.is_available.assert_not_called()

    def test_readable_native_text_below_threshold_uses_native_extraction(self):
        for size in (1, 28, 49, 50, 60):
            with self.subTest(native_characters=size):
                path = self.write_pdf(["A" * size])
                self.assertEqual(DetectionService.detect_pdf_type(str(path)), DetectionType.DIGITAL)
                layout, job = self.extract(path)
                self.assertEqual(layout[0]["blocks"][0]["lines"][0]["text"], "A" * size)
                self.assertEqual(job.metadata["page_extraction_methods"], {"0": "digital"})
                self.assertEqual(job.metadata["extraction_method"], "direct_pdf_text")
        self.assert_no_ocr()

    def test_ordinary_text_pdf_reaches_translation(self):
        text = "This ordinary native PDF contains enough readable text to exceed the old threshold."
        ok, job, translate = self.run_pipeline(self.write_pdf([text]))
        self.assertTrue(ok, job.error)
        translate.assert_called_once()
        layout = translate.call_args.args[0]
        self.assertEqual(layout[0]["blocks"][0]["lines"][0]["text"], text)
        self.assertEqual(job.status, "completed")
        self.assert_no_ocr()

    def test_sparse_native_pdf_completes_using_existing_dataset_entry(self):
        ok, job, translate = self.run_pipeline(self.write_pdf(["alert"]))
        self.assertTrue(ok, job.error)
        translate.assert_called_once()
        self.assertEqual(job.status, "completed")
        output = self.pipeline.file_service.get_output_path(job.job_id, "translated.pdf")
        expected = self.dataset.translate_phrase("alert", "english", "filipino")
        with fitz.open(output) as doc:
            self.assertEqual(len(doc), 1)
            self.assertIn("".join(expected.split()), "".join(doc[0].get_text().split()))
        self.assertEqual(len(job.metadata["preview_original"]), 1)
        self.assertEqual(len(job.metadata["preview_translated"]), 1)
        self.assert_no_ocr()

    def test_multiple_sparse_and_dense_pages_reach_translation_in_order(self):
        texts = ["alert", "A longer native PDF page with ordinary text well above fifty characters.", "day"]
        ok, job, translate = self.run_pipeline(self.write_pdf(texts))
        self.assertTrue(ok, job.error)
        layout = translate.call_args.args[0]
        self.assertEqual([p["blocks"][0]["lines"][0]["text"] for p in layout], texts)
        self.assertEqual(job.metadata["page_extraction_methods"], {"0": "digital", "1": "digital", "2": "digital"})
        self.assertEqual(job.metadata["translated_page_count"], 3)
        self.assert_no_ocr()

    def test_embedded_image_and_graphic_survive_native_pipeline(self):
        path = self.write_pdf(["alert"], image=True)
        with fitz.open(path) as source:
            source_image = source.extract_image(source[0].get_images()[0][0])["image"]
        ok, job, translate = self.run_pipeline(path)
        self.assertTrue(ok, job.error)
        self.assertIn("image", [b["type"] for b in translate.call_args.args[0][0]["blocks"]])
        output = self.pipeline.file_service.get_output_path(job.job_id, "translated.pdf")
        with fitz.open(output) as doc:
            self.assertEqual(doc[0].rect, fitz.Rect(0, 0, 612, 792))
            self.assertEqual(len(doc[0].get_images()), 1)
            self.assertEqual(doc.extract_image(doc[0].get_images()[0][0])["image"], source_image)
            self.assertTrue(any(d["rect"] == fitz.Rect(200, 160, 300, 240) for d in doc[0].get_drawings()))
        self.assert_no_ocr()

    def test_native_extraction_exception_fails_before_translation(self):
        path = self.write_pdf(["alert"])
        with patch.object(ExtractionService, "_extract_page_digital", side_effect=RuntimeError("isolated extraction error")):
            ok, job, translate = self.run_pipeline(path)
        self.assertFalse(ok)
        self.assertEqual(job.status, "failed")
        self.assertIn("isolated extraction error", job.error)
        translate.assert_not_called()
        self.assert_no_ocr()

    def test_missing_pdf_returns_extraction_error(self):
        job = JobStatus("missing-pdf")
        layout, error = self.pipeline._extract_hybrid_pdf(str(self.root / "missing.pdf"), None, job)
        self.assertEqual(layout, [])
        self.assertTrue(error)
        self.assert_no_ocr()

    def test_corrupt_pdf_returns_extraction_error(self):
        path = self.root / "corrupt.pdf"
        path.write_bytes(b"%PDF-1.7\ninvalid document")
        layout, error = self.pipeline._extract_hybrid_pdf(str(path), None, JobStatus("corrupt-pdf"))
        self.assertEqual(layout, [])
        self.assertTrue(error)
        self.assert_no_ocr()

    def test_empty_file_fails_without_translation_or_output(self):
        path = self.root / "empty.pdf"
        path.write_bytes(b"")
        ok, job, translate = self.run_pipeline(path)
        self.assertFalse(ok)
        self.assertEqual(job.status, "failed")
        translate.assert_not_called()
        self.assertFalse((Path(self.pipeline.file_service.get_job_dir(job.job_id)) / "translated.pdf").exists())
        self.assert_no_ocr()

    def test_blank_pdf_is_rejected_without_ocr(self):
        ok, job, translate = self.run_pipeline(self.write_pdf([""]))
        self.assertFalse(ok)
        self.assertEqual(job.status, "failed")
        self.assertIn("no readable native text", job.error)
        translate.assert_not_called()
        self.assert_no_ocr()

    def test_wholly_image_pdf_is_rejected_without_ocr(self):
        ok, job, translate = self.run_pipeline(self.write_pdf([""], image=True))
        self.assertFalse(ok)
        self.assertEqual(job.status, "failed")
        self.assertIn("Scanned or textless PDFs are not supported", job.error)
        translate.assert_not_called()
        self.assert_no_ocr()

    def test_image_only_and_blank_pages_are_preserved_in_text_based_pdf(self):
        path = self.write_pdf(["alert", "", ""], image={1})
        with fitz.open(path) as source:
            preserved_pixels = [source[i].get_pixmap().samples for i in (1, 2)]
        ok, job, translate = self.run_pipeline(path)
        self.assertTrue(ok, job.error)
        self.assertEqual(job.metadata["page_extraction_methods"], {"0": "digital", "1": "preserved", "2": "preserved"})
        layout = translate.call_args.args[0]
        self.assertFalse(any(b["type"] == "text" for p in layout[1:] for b in p["blocks"]))
        with fitz.open(self.pipeline.file_service.get_output_path(job.job_id, "translated.pdf")) as output:
            self.assertEqual(len(output), 3)
            self.assertEqual([output[i].get_pixmap().samples for i in (1, 2)], preserved_pixels)
        self.assert_no_ocr()

    def test_corrupt_document_fails_before_translation_without_ocr(self):
        path = self.root / "corrupt.pdf"
        path.write_bytes(b"%PDF-1.7\ninvalid document")
        ok, job, translate = self.run_pipeline(path)
        self.assertFalse(ok)
        self.assertEqual(job.status, "failed")
        self.assertIn("Could not read PDF document", job.error)
        translate.assert_not_called()
        self.assert_no_ocr()

    def test_tiny_nonreadable_span_is_not_promoted_to_native(self):
        path = self.root / "tiny.pdf"
        with fitz.open() as doc:
            doc.new_page().insert_text((72, 100), "x", fontsize=1)
            doc.save(path)
        with fitz.open(path) as doc:
            self.assertFalse(DetectionService.page_has_native_text(doc[0]))
        self.assertEqual(DetectionService.detect_pdf_type(str(path)), DetectionType.SCANNED)
