"""T08 opt-in real HTTP/Chrome/PostgreSQL/thread-worker integration tests.

No worker, resource loader, pipeline, persistence, or completion-state mocks.
Faults are real test-database locks, malformed files, empty verified resources,
or Chrome network controls. Run only against a named disposable T08 database.
"""
import base64
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
from unittest import skipUnless
import zipfile

import fitz
from docx import Document
from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.urls import reverse

from .models import GeneratedOutput, PhrasebookEntry, SystemEventLog, TranslationJob
from .services import _run_translation_job
from .services.reconstruction_service import ReconstructionService
from .services.translation_dataset import get_translation_dataset, reset_translation_dataset
from .test_translation_workflow import Chrome, chrome_binary


class IntegrationChrome(Chrome):
    """Capture actual HTTP responses; optionally drop an accepted upload reply."""
    def __init__(self):
        self.responses = []
        self.dropped_uploads = []
        self.download_events = []
        self.drop_upload_response = False
        super().__init__()
        self.call("Network.enable")

    def call(self, method, params=None):
        self.number += 1
        number = self.number
        self.ws.send(json.dumps({"id": number, "method": method, "params": params or {}}))
        while True:
            result = json.loads(self.ws.recv(timeout=20))
            event = result.get("method")
            if event == "Runtime.exceptionThrown":
                self.errors.append(result["params"])
            if event == "Network.responseReceived":
                response = result["params"]["response"]
                self.responses.append({"url": response["url"], "status": response["status"]})
            if event in {"Browser.downloadWillBegin", "Browser.downloadProgress", "Page.downloadWillBegin"}:
                self.download_events.append({"method": event, **result["params"]})
            if event == "Fetch.requestPaused":
                paused = result["params"]
                drop = self.drop_upload_response and paused.get("responseStatusCode") == 202
                if drop:
                    self.dropped_uploads.append({"url": paused["request"]["url"], "status": 202})
                self.number += 1
                self.ws.send(json.dumps({"id": self.number,
                    "method": "Fetch.failRequest" if drop else "Fetch.continueResponse",
                    "params": {"requestId": paused["requestId"], **({"errorReason": "ConnectionClosed"} if drop else {})}}))
            if result.get("id") == number:
                if "error" in result:
                    raise AssertionError(result["error"])
                return result.get("result", {})


@skipUnless(os.environ.get("LINGOKATUTUBO_RUN_REAL_INTEGRATION") == "1",
            "T08 real-worker tests require explicit opt-in and a disposable T08 PostgreSQL database")
class RealTranslationIntegrationTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
            raise RuntimeError("T08 requires actual PostgreSQL")
        if not settings.DATABASES["default"]["NAME"].startswith("test_lingokatutubo_t08_"):
            raise RuntimeError("Refusing T08 integration against a non-T08 database")
        if settings.LINGOKATUTUBO_TASK_MODE != "thread":
            raise RuntimeError("This suite verifies the audited thread runner, not Celery or inline substitutes")
        if not chrome_binary():
            raise RuntimeError("Installed Chrome is required; no browser substitute is allowed")
        if not os.environ.get("LINGOKATUTUBO_T08_ARTIFACT_DIR"):
            raise RuntimeError("Provide an isolated T08 artifact directory")
        super().setUpClass()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lingokatutubo-t08-media-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.artifacts = Path(os.environ["LINGOKATUTUBO_T08_ARTIFACT_DIR"]) / self._testMethodName
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self.config = override_settings(MEDIA_ROOT=Path(os.environ["LINGOKATUTUBO_T08_ARTIFACT_DIR"]) / "server-media", SESSION_COOKIE_SECURE=False,
                                        CSRF_COOKIE_SECURE=False, LINGOKATUTUBO_NEURAL_TRANSLATION_ENABLED=False)
        self.config.enable()
        self.addCleanup(self.config.disable)
        cache.clear()
        reset_translation_dataset()
        self.browser = IntegrationChrome()
        self.addCleanup(self.browser.close)
        self.downloads = self.root / "downloads"
        self.downloads.mkdir()
        self.browser.call("Browser.setDownloadBehavior", {"behavior": "allowAndName",
                          "downloadPath": str(self.downloads), "eventsEnabled": True})
        self.evidence = {"test": self._testMethodName, "worker_mode": settings.LINGOKATUTUBO_TASK_MODE,
                         "jobs": [], "scenarios": {}}
        self.addCleanup(self.finish)
        self.user = get_user_model().objects.create_user("t08-user", password="T08-isolated-only-63842")
        self.sign_in(self.user.username)

    def finish(self):
        self.join_workers()
        self.evidence["browser_javascript_errors"] = self.browser.errors
        self.evidence["actual_http_responses"] = self.browser.responses
        self.evidence["actual_download_events"] = self.browser.download_events
        (self.artifacts / "evidence.json").write_text(json.dumps(self.evidence, indent=2) + "\n", encoding="utf-8")
        reset_translation_dataset()

    def join_workers(self):
        deadline = time.monotonic() + 25
        while True:
            workers = [t for t in threading.enumerate() if t.name.startswith("lingokatutubo-translation-")]
            if not workers:
                return
            if time.monotonic() >= deadline:
                self.fail("Real translation worker did not finish before isolated teardown")
            for worker in workers:
                worker.join(timeout=0.2)

    def until(self, predicate, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.05)
        self.fail("Timed out waiting for actual integration state")

    def sign_in(self, username):
        self.browser.call("Network.clearBrowserCookies")
        self.browser.navigate(self.live_server_url + reverse("translator:login"))
        self.browser.evaluate("sessionStorage.clear(); document.querySelector('[name=username]').value=" +
                              json.dumps(username) + "; document.querySelector('[name=password]').value=" +
                              json.dumps("T08-isolated-only-63842") + "; document.querySelector('form.auth-panel').requestSubmit()")
        self.browser.wait("location.pathname === '/translate/' && !!document.querySelector('#translate-flow-form')")
        self.assertNotIn("Log in to continue", self.browser.evaluate("document.body.innerText"))

    def screenshot(self, name):
        screenshot = self.browser.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        (self.artifacts / name).write_bytes(base64.b64decode(screenshot["data"]))

    def pdf(self, name, texts=("Visiting",), images=False, width=612, height=792, fontsize=12):
        path = self.root / name
        font = ReconstructionService._unicode_fontfile()
        image = io.BytesIO()
        Image.new("RGB", (48, 24), (30, 140, 80)).save(image, "PNG")
        with fitz.open() as doc:
            for text in texts:
                page = doc.new_page(width=width, height=height)
                point = (72, 100) if width > 100 else (2, 8)
                page.insert_text(point, text, fontsize=fontsize, fontname="t08font" if font else "helv", fontfile=font)
                if images:
                    page.insert_image(fitz.Rect(72, 220, 168, 268), stream=image.getvalue())
            doc.save(path)
        return path

    def submit(self, path, source="english", target="tagabawa", duplicate_click=False, uncertain=False):
        before = set(TranslationJob.objects.values_list("pk", flat=True))
        self.browser.navigate(self.live_server_url + reverse("translator:translate"))
        self.browser.evaluate("sessionStorage.clear()")
        # Revisit so the page's in-memory pending guard also starts clean.
        self.browser.navigate(self.live_server_url + reverse("translator:translate"))
        self.browser.choose(path)
        self.browser.evaluate("document.querySelector('#translate-source').value=" + json.dumps(source) +
                              "; document.querySelector('#translate-target').value=" + json.dumps(target) + ";")
        if uncertain:
            self.browser.drop_upload_response = True
            self.browser.call("Fetch.enable", {"patterns": [{"urlPattern": self.live_server_url + reverse("translator:upload"),
                                                             "requestStage": "Response"}]})
        self.browser.evaluate("document.querySelector('#translate-flow-form').requestSubmit();" +
                              ("document.querySelector('#translate-flow-form').requestSubmit();" if duplicate_click else ""))
        job = self.until(lambda: TranslationJob.objects.exclude(pk__in=before).first())
        if uncertain:
            self.browser.wait("document.querySelector('#translate-error-title').textContent.includes('could not be confirmed')", timeout=45)
        else:
            self.browser.wait("!!document.querySelector('[data-status-poller]')", timeout=45)
            self.assertIn(job.job_id, self.browser.evaluate("location.pathname"))
            self.assertTrue(any(r["status"] == 202 and r["url"].endswith(reverse("translator:upload"))
                                for r in self.browser.responses), self.browser.responses)
        self.assertEqual(TranslationJob.objects.exclude(pk__in=before).count(), 1)
        job.refresh_from_db()
        return job

    def snapshot(self, job):
        # One SQL statement: status and dependent counts share one PG snapshot.
        with connection.cursor() as cursor:
            cursor.execute("""SELECT status, current_phase,
                (SELECT count(*) FROM translator_generatedoutput o WHERE o.job_id=j.id AND output_type='translated_pdf'),
                (SELECT count(*) FROM translator_generatedoutput o WHERE o.job_id=j.id AND output_type='structure_json'),
                (SELECT count(*) FROM translator_documentpage p WHERE p.job_id=j.id),
                (SELECT count(*) FROM translator_translationsegment s WHERE s.job_id=j.id)
                FROM translator_translationjob j WHERE id=%s""", [job.pk])
            row = cursor.fetchone()
        result = dict(zip(["status", "phase", "translated_records", "structure_records", "pages", "segments"], row))
        if result["status"] == "completed":
            self.assertTrue(all(result[k] > 0 for k in ["translated_records", "structure_records", "pages", "segments"]), result)
        return result

    def terminal(self, job, expected="completed"):
        observations = []
        def poll():
            state = self.snapshot(job)
            if not observations or observations[-1] != state:
                observations.append(state)
            return state if state["status"] in {"completed", "failed"} else None
        final = self.until(poll, timeout=90)
        self.assertEqual(final["status"], expected, list(TranslationJob.objects.filter(pk=job.pk).values("error", "metadata")))
        self.join_workers()
        job.refresh_from_db()
        self.assertEqual(Path(job.upload_file_path).read_bytes(), Path(job.input_file_path).read_bytes())
        self.assertTrue(SystemEventLog.objects.filter(job=job, event_type="translation_job_dispatched",
                                                     metadata__task_mode="thread").exists())
        entry = {"id": job.job_id, "filename": job.original_filename, "source_language": job.source_language,
                 "target_language": job.target_language, "status": job.status, "observations": observations,
                 "metadata": job.metadata, "error": job.error,
                 "segments": list(job.segments.values("source_text", "translated_text", "method", "confidence", "needs_review", "metadata")),
                 "unknown_records": list(job.unknown_records.values("source_text", "reason", "review_status")),
                 "outputs": list(job.generated_outputs.values("output_type", "file_format", "file_path", "file_size_bytes"))}
        self.evidence["jobs"].append(entry)
        destination = self.artifacts / job.original_filename.replace(".", "_")
        destination.mkdir(exist_ok=True)
        shutil.copyfile(job.upload_file_path, destination / ("source." + job.file_type))
        for kind, path in [("translated.pdf", job.output_file_path), ("structure.json", job.structure_file_path)]:
            if path and Path(path).is_file():
                shutil.copyfile(path, destination / kind)
        if expected == "completed":
            self.assertTrue(all(s.needs_review for s in job.segments.all()))
            self.assertTrue(all(s.metadata.get("validation_status") == "unverified" for s in job.segments.all()))
            with fitz.open(job.output_file_path) as pdf:
                text = "".join(page.get_text() for page in pdf)
                entry.update(output_text=text, output_pages=len(pdf), review_notes=sum(len(list(p.annots())) for p in pdf),
                             embedded_images=sum(len(p.get_images()) for p in pdf))
                for index, page in enumerate(pdf):
                    page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(destination / f"page-{index+1}.png")
            self.assertGreater(entry["review_notes"], 0)
        return entry

    def preview_download(self, job, expected_terms):
        self.browser.navigate(self.live_server_url + reverse("translator:job_detail", args=[job.pk]))
        self.assertIn("Translation Complete", self.browser.evaluate("document.body.innerText"))
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#translation-job-processing-overlay')"))
        self.browser.evaluate("document.querySelector('#job-terminal-preview-action').click()")
        self.browser.wait("!!document.querySelector('#preview-app')")
        self.browser.wait("Array.from(document.querySelectorAll('.document-page-image')).length >= 2 && Array.from(document.querySelectorAll('.document-page-image')).every(i => i.complete && i.naturalWidth > 0)", timeout=45)
        self.assertIn(job.job_id, self.browser.evaluate("document.querySelector('#preview-download').href"))
        self.screenshot(job.original_filename + "-preview.png")
        before = set(self.downloads.iterdir())
        self.browser.evaluate("document.querySelector('#preview-download').click()")
        def completed_download():
            for path in self.downloads.iterdir():
                if path in before or path.suffix == ".crdownload" or not path.is_file():
                    continue
                with path.open("rb") as content:
                    if content.read(5) == b"%PDF-":
                        return path
            return None
        downloaded = self.until(completed_download, timeout=30)
        self.browser.evaluate("0")
        record = job.generated_outputs.get(output_type=GeneratedOutput.OutputType.TRANSLATED_PDF)
        expected = Path(record.file_path).read_bytes()
        self.assertEqual(downloaded.read_bytes(), expected)
        with fitz.open(downloaded) as pdf:
            content = "".join("".join(p.get_text().split()) for p in pdf)
        for term in expected_terms:
            self.assertIn("".join(term.split()), content)
        shutil.copyfile(downloaded, self.artifacts / (job.original_filename + "-download.pdf"))
        self.evidence["scenarios"][job.original_filename + "_preview_download"] = {
            "actual_browser_download": True, "matches_persisted_record": True,
            "sha256": hashlib.sha256(expected).hexdigest(), "expected_terms": expected_terms}
        self.assertEqual(self.browser.errors, [])

    @contextmanager
    def hold_completion(self):
        import psycopg2
        config = settings.DATABASES["default"]
        self.assertTrue(config["NAME"].startswith("test_lingokatutubo_t08_"))
        lock = psycopg2.connect(dbname=config["NAME"], user=config["USER"], password=config["PASSWORD"],
                                host=config["HOST"], port=config["PORT"])
        try:
            with lock.cursor() as cursor:
                cursor.execute("LOCK TABLE translator_generatedoutput IN SHARE MODE")
            yield
        finally:
            lock.rollback()
            lock.close()

    def wait_for_completion_lock(self):
        def waiting():
            with connection.cursor() as cursor:
                cursor.execute("""SELECT pid, wait_event_type, wait_event FROM pg_stat_activity
                    WHERE datname=current_database() AND pid<>pg_backend_pid()
                    AND wait_event_type='Lock' AND query ILIKE '%%translator_generatedoutput%%'""")
                return cursor.fetchone()
        return self.until(waiting)

    def test_real_pdf_atomic_completion_refresh_outage_and_duplicate_worker(self):
        source = self.pdf("native-images.pdf", texts=("Visiting", "alert"), images=True)
        before = source.read_bytes()
        with self.hold_completion():
            job = self.submit(source, duplicate_click=True)
            waiting = self.wait_for_completion_lock()
            state = self.snapshot(job)
            self.assertEqual(state["status"], "processing")
            self.assertEqual(state["translated_records"], 0)
            workers = [t.name for t in threading.enumerate() if t.name == "lingokatutubo-translation-" + job.job_id]
            self.assertEqual(len(workers), 1)
            duplicate = threading.Thread(target=_run_translation_job,
                args=(job.job_id, job.input_file_path, job.file_type, "english", "tagabawa", None),
                name="t08-duplicate-attempt")
            duplicate.start()
            self.addCleanup(duplicate.join, 25)
            status_url = self.browser.evaluate("document.querySelector('[data-status-poller]').dataset.statusUrl")
            self.browser.call("Network.setBlockedURLs", {"urls": [self.live_server_url + status_url]})
            self.browser.evaluate("document.querySelector('#reload-status-button').click()")
            self.browser.wait("!document.querySelector('#status-monitor-network').hidden")
            self.assertNotIn("Translation Failed", self.browser.evaluate("document.body.innerText"))
            self.browser.navigate(self.live_server_url + reverse("translator:job_detail", args=[job.pk]))
            self.assertEqual(self.browser.evaluate("document.querySelector('[data-status-poller]').dataset.initialStatus"), "processing")
            self.assertEqual(self.snapshot(job)["status"], "processing")
            self.screenshot("processing-network-outage.png")
            self.browser.call("Network.setBlockedURLs", {"urls": []})
            self.evidence["scenarios"].update(completion_lock_wait=list(waiting), actual_worker_threads=workers,
                status_during_blocked_completion=state, duplicate_active_attempt_submitted=True,
                refresh_retained_processing=True, actual_browser_status_network_block=True)
        entry = self.terminal(job)
        duplicate.join(timeout=25)
        self.assertFalse(duplicate.is_alive())
        self.assertEqual(SystemEventLog.objects.filter(job=job, event_type="translation_job_started").count(), 1)
        self.assertTrue(SystemEventLog.objects.filter(job=job, event_type="translation_job_duplicate_ignored").exists())
        self.assertEqual(source.read_bytes(), before)
        with fitz.open(source) as original, fitz.open(job.output_file_path) as output:
            self.assertEqual(len(output), 2)
            self.assertNotIn("Visiting", output[0].get_text())
            for i, page in enumerate(output):
                self.assertEqual(output.extract_image(page.get_images()[0][0])["image"],
                                 original.extract_image(original[i].get_images()[0][0])["image"])
                self.assertEqual(page.get_pixmap(clip=fitz.Rect(72, 220, 168, 268)).samples,
                                 original[i].get_pixmap(clip=fitz.Rect(72, 220, 168, 268)).samples)
        self.assertEqual(entry["metadata"]["extraction_method"], "direct_pdf_text")
        row = next(r for r in get_translation_dataset().data if r.get("english") == "Visiting")
        self.preview_download(job, [row["tagabawa"], "matasik"])
        before_state = (job.updated_at, job.segments.count(), job.generated_outputs.count(), Path(job.output_file_path).read_bytes())
        _run_translation_job(job.job_id, job.input_file_path, job.file_type, "english", "tagabawa", None)
        job.refresh_from_db()
        self.assertEqual((job.updated_at, job.segments.count(), job.generated_outputs.count(), Path(job.output_file_path).read_bytes()), before_state)
        self.assertEqual(TranslationJob.objects.count(), 1)

    def test_real_docx_retains_fuzzy_conflict_unknown_and_review_metadata(self):
        source = self.root / "table-and-review.docx"
        document = Document()
        document.add_paragraph("Visiting")
        table = document.add_table(rows=2, cols=2)
        for cell, text in zip([c for row in table.rows for c in row.cells], ["alert", "abundantt", "Sit down", "T08 qzxvkj"]):
            cell.text = text
        image = io.BytesIO()
        Image.new("RGB", (48, 24), (30, 140, 80)).save(image, "PNG")
        document.add_picture(io.BytesIO(image.getvalue()))
        document.save(source)
        before = source.read_bytes()
        job = self.submit(source)
        entry = self.terminal(job)
        segments = {s.source_text: s for s in job.segments.all()}
        self.assertEqual(segments["abundantt"].metadata["match_method"], "fuzzy")
        self.assertLess(segments["abundantt"].confidence, 1)
        self.assertTrue(segments["abundantt"].needs_review)
        for source_text in ["Sit down", "T08 qzxvkj"]:
            self.assertEqual(segments[source_text].translated_text, source_text)
            self.assertTrue(job.unknown_records.filter(segment=segments[source_text], review_status="pending").exists())
        self.assertTrue(any("Conflicting" in w for w in segments["Sit down"].metadata["warnings"]))
        self.assertFalse(job.unknown_records.filter(source_text="abundantt").exists())
        self.assertTrue(segments["Visiting"].metadata["matched_entry_id"])
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(entry["embedded_images"], 1)
        self.assertTrue(any("table borders" in w for w in job.metadata["layout_warnings"]))
        row = next(r for r in get_translation_dataset().data if r.get("english") == "Visiting")
        self.preview_download(job, [row["tagabawa"], "matasik", "kaduwannan", "Sit down", "T08 qzxvkj"])

    def test_all_twelve_directions_through_actual_pdf_upload_and_worker(self):
        row = next(r for r in get_translation_dataset().data if r.get("english") == "alert")
        languages = ["tagabawa", "english", "filipino", "cebuano"]
        directions = [(s, t) for s in languages for t in languages if s != t]
        for index, (source_language, target) in enumerate(directions):
            with self.subTest(source=source_language, target=target):
                if index and index % 4 == 0:
                    self.user = get_user_model().objects.create_user("t08-user-" + str(index), password="T08-isolated-only-63842")
                    self.sign_in(self.user.username)
                source = self.pdf(source_language + "-to-" + target + ".pdf", texts=(row[source_language],))
                job = self.submit(source, source_language, target)
                entry = self.terminal(job)
                self.assertIn(row[target], entry["output_text"])
                self.assertEqual(job.segments.get().metadata["match_method"], "exact")
                self.assertEqual(job.segments.get().translated_text, row[target])
                self.preview_download(job, [row[target]])
        self.assertEqual(TranslationJob.objects.filter(status="completed").count(), 12)

    def test_default_auto_detection_uses_actual_worker_and_resources(self):
        sentence = next(r for r in get_translation_dataset().data if r.get("id") == "FINAL-000162")
        source = self.pdf("automatic-source.pdf", texts=(sentence["english"], "Visiting"))
        job = self.submit(source, source="auto")
        self.terminal(job)
        self.assertEqual(job.source_language, "auto")
        self.assertEqual(job.metadata["detected_language"], "english")
        self.assertGreater(job.metadata["detection_confidence"], 0)
        row = next(r for r in get_translation_dataset().data if r.get("english") == "Visiting")
        self.preview_download(job, [sentence["tagabawa"], row["tagabawa"]])
        self.evidence["scenarios"]["default_automatic_detection"] = {
            "requested_source": job.source_language, "detected_source": job.metadata["detected_language"],
            "confidence": job.metadata["detection_confidence"], "actual_browser_download": True}

    def test_scanned_and_textless_pdf_fail_safely_and_remain_in_history(self):
        paths = []
        for scanned in [False, True]:
            path = self.root / ("scanned.pdf" if scanned else "textless.pdf")
            with fitz.open() as doc:
                page = doc.new_page()
                if scanned:
                    image = io.BytesIO()
                    Image.new("RGB", (100, 100), (30, 140, 80)).save(image, "PNG")
                    page.insert_image(page.rect, stream=image.getvalue())
                doc.save(path)
            paths.append(path)
        for path in paths:
            job = self.submit(path)
            self.terminal(job, "failed")
            self.assertIn("no readable native text", job.error)
            self.assertFalse(job.generated_outputs.filter(output_type="translated_pdf").exists())
            self.browser.navigate(self.live_server_url + reverse("translator:job_detail", args=[job.pk]))
            body = self.browser.evaluate("document.body.innerText")
            self.assertIn("Translation Failed", body)
            self.assertNotIn("Traceback", body)
            self.assertNotIn(str(self.root), body)
        self.browser.navigate(self.live_server_url + reverse("translator:history"))
        for path in paths:
            self.assertIn(path.name, self.browser.evaluate("document.body.innerText"))
        self.assertEqual(TranslationJob.objects.count(), 2)

    def test_unavailable_verified_resources_fail_without_file_fallback(self):
        self.assertEqual(PhrasebookEntry.objects.count(), 0)
        previous = os.environ.pop("TRANSLATION_DATA_MODE", None)
        try:
            with override_settings(TRANSLATION_DATA_MODE="verified_only"):
                reset_translation_dataset()
                source = self.pdf("resources-unavailable.pdf")
                job = self.submit(source)
                self.terminal(job, "failed")
                self.assertFalse(get_translation_dataset().is_loaded)
                self.assertFalse(job.generated_outputs.filter(output_type="translated_pdf").exists())
                self.assertTrue("resource" in job.error.lower(), job.error)
                self.evidence["scenarios"]["unavailable_resources"] = {"mode": "verified_only", "approved_entry_count": 0,
                    "real_worker_failed": True, "file_fallback": False}
        finally:
            if previous is not None:
                os.environ["TRANSLATION_DATA_MODE"] = previous
            reset_translation_dataset()

    def test_real_reconstruction_failure_never_publishes_partial_output(self):
        source = self.pdf("cannot-fit.pdf", width=30, height=30, fontsize=3)
        job = self.submit(source)
        self.terminal(job, "failed")
        self.assertTrue(any("not completed" in w or "no replacement" in w for w in job.metadata["layout_warnings"]))
        self.assertFalse(job.generated_outputs.filter(output_type="translated_pdf").exists())
        self.assertFalse(Path(job.input_file_path).parent.parent.joinpath("translated", "translated.pdf").exists())

    def test_real_worker_processing_exception_from_malformed_docx(self):
        path = self.root / "malformed.docx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", "malformed package XML")
            archive.writestr("word/document.xml", "<not-closed")
        job = self.submit(path)
        self.terminal(job, "failed")
        self.assertFalse(job.generated_outputs.filter(output_type="translated_pdf").exists())
        self.browser.navigate(self.live_server_url + reverse("translator:job_detail", args=[job.pk]))
        body = self.browser.evaluate("document.body.innerText")
        self.assertIn("Translation Failed", body)
        self.assertNotIn("Traceback", body)
        self.assertNotIn("XMLSyntaxError", body)
        self.assertNotIn(str(self.root), body)

    def test_lost_actual_202_response_recovers_via_history_without_resubmission(self):
        source = self.pdf("lost-response.pdf")
        job = self.submit(source, uncertain=True)
        self.assertTrue(self.browser.dropped_uploads)
        self.assertTrue(self.browser.evaluate("document.querySelector('#translate-start').disabled"))
        self.browser.drop_upload_response = False
        self.browser.call("Fetch.disable")
        self.browser.navigate(self.live_server_url + reverse("translator:translate"))
        self.assertIn("could not be confirmed", self.browser.evaluate("document.querySelector('#translate-error-title').textContent"))
        self.browser.evaluate("document.querySelector('#translate-flow-form').requestSubmit()")
        self.assertEqual(TranslationJob.objects.count(), 1)
        self.terminal(job)
        self.browser.evaluate("document.querySelector('#translate-review-upload').click()")
        self.browser.wait("location.pathname === '/translate/history/'")
        self.assertIn(source.name, self.browser.evaluate("document.body.innerText"))
        self.evidence["scenarios"]["lost_upload_response"] = {"actual_accepted_response_dropped": self.browser.dropped_uploads,
            "history_recovery": True, "job_count": 1, "automatic_resubmission": False}
        row = next(r for r in get_translation_dataset().data if r.get("english") == "Visiting")
        self.preview_download(job, [row["tagabawa"]])
