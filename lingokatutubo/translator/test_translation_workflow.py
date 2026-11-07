"""T04 integration and real Chrome tests; temporary database/media/profile only."""

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

import fitz
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.db import OperationalError
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from .models import DocumentPage, GeneratedOutput, TranslationJob, TranslationSegment, UploadedDocument
from .services.job_lifecycle import JobPersistenceError


class WorkflowFixtures:
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(prefix="lingokatutubo-t04-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        context = override_settings(MEDIA_ROOT=self.root, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
        context.enable()
        self.addCleanup(context.disable)
        cache.clear()
        self.user = get_user_model().objects.create(username="t04-user")
        self.client.force_login(self.user)

    def job(self, status="queued"):
        return TranslationJob.objects.create(
            owner=self.user, original_filename="workflow.pdf", file_type="pdf",
            source_language="english", target_language="filipino", status=status,
        )

    def pdf(self, path, text="alisto"):
        path.parent.mkdir(parents=True, exist_ok=True)
        with fitz.open() as doc:
            doc.new_page().insert_text((72, 100), text)
            doc.save(path)
        return path

    def output(self, job, kind=GeneratedOutput.OutputType.TRANSLATED_PDF):
        path = self.pdf(self.root / "jobs" / job.job_id / "translated" / f"{kind}.pdf")
        GeneratedOutput.objects.create(job=job, output_type=kind, file_path=str(path), file_format="pdf")
        return path

    def complete(self, job):
        self.output(job)
        page = DocumentPage.objects.create(job=job, page_number=1, extracted_text="alert")
        TranslationSegment.objects.create(
            job=job, page=page, segment_index=1, source_text="alert", translated_text="alisto",
            source_language="english", target_language="filipino", method="phrasebook_exact",
        )
        TranslationJob.objects.filter(pk=job.pk).update(status="completed", current_phase="completed")


class WorkflowIntegrationTests(WorkflowFixtures, TransactionTestCase):
    def test_completed_refresh_retains_state_and_record_based_actions(self):
        job = self.job()
        self.complete(job)
        for _ in range(2):
            response = self.client.get(reverse("translator:job_detail", args=[job.pk]))
            self.assertContains(response, "Translation Complete")
            self.assertContains(response,
                                f'href="{reverse("translator:job_download", args=[job.pk])}">Download PDF</a>',
                                count=1)
            self.assertNotContains(response, 'id="translation-job-processing-overlay"')
            self.assertEqual(response.content.count(b'id="job-terminal-preview-action"'), 1)
        payload = self.client.get(reverse("translator:status", args=[job.pk])).json()
        self.assertTrue(payload["can_download"])
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")

    def test_completed_without_output_keeps_preview_but_hides_download(self):
        job = self.job("completed")
        response = self.client.get(reverse("translator:job_detail", args=[job.pk]))
        self.assertContains(response, "Preview Document")
        self.assertContains(response, "download is currently unavailable")
        self.assertNotContains(response, ">Download PDF</a>")
        self.assertRedirects(self.client.get(reverse("translator:job_download", args=[job.pk])),
                             reverse("translator:job_detail", args=[job.pk]), fetch_redirect_response=False)

    def test_download_uses_translated_record_and_never_another_jobs_file(self):
        job = self.job("completed")
        correct = self.output(job)
        other = self.job("completed")
        job.output_file_path = str(self.output(other))
        job.save()
        response = self.client.get(reverse("translator:job_download", args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), correct.read_bytes())
        response.close()

    def test_original_archive_and_document_record_are_downloadable_only_by_owner(self):
        job = self.job("completed")
        original = self.pdf(self.root / "uploads" / job.job_id / "workflow.pdf", "alert")
        UploadedDocument.objects.create(owner=self.user, job=job, original_filename="workflow.pdf",
                                        file_type="pdf", file_path=str(original), file_size_bytes=original.stat().st_size)
        response = self.client.get(reverse("translator:job_download_original", args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), original.read_bytes())
        response.close()
        self.client.force_login(get_user_model().objects.create(username="other-owner"))
        self.assertEqual(self.client.get(reverse("translator:job_download_original", args=[job.pk])).status_code, 404)

    def test_bilingual_record_fallback_without_translated_file(self):
        self.user.is_superuser = True
        self.user.save()
        job = self.job("completed")
        path = self.output(job, GeneratedOutput.OutputType.BILINGUAL_ALTERNATING)
        response = self.client.get(reverse("translator:job_download", args=[job.pk]) + "?format=bilingual")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), path.read_bytes())
        response.close()

    def test_original_download_rejects_another_jobs_archive_path(self):
        job = self.job("completed")
        other = self.job("completed")
        job.upload_file_path = str(self.pdf(self.root / "uploads" / other.job_id / "private.pdf"))
        job.save()
        response = self.client.get(reverse("translator:job_download_original", args=[job.pk]))
        self.assertRedirects(response, reverse("translator:job_detail", args=[job.pk]), fetch_redirect_response=False)

    def test_missing_bilingual_output_does_not_offer_teacher_download(self):
        self.user.is_superuser = True
        self.user.save()
        job = self.job("completed")
        self.output(job)
        response = self.client.get(reverse("translator:job_detail", args=[job.pk]))
        self.assertNotContains(response, "?format=bilingual")

    def test_side_by_side_preview_uses_only_this_jobs_persisted_segments(self):
        job = self.job()
        self.complete(job)
        other = self.job("completed")
        TranslationSegment.objects.create(job=other, segment_index=1, source_text="other source",
                                           translated_text="other translation")
        response = self.client.get(reverse("translator:job_preview", args=[job.pk]))
        self.assertContains(response, "Original Document")
        self.assertContains(response, "Translated Document")
        self.assertContains(response, "alert")
        self.assertContains(response, "alisto")
        self.assertNotContains(response, "other translation")
        self.assertNotContains(response, "window.history.back()")

    def test_processing_refresh_keeps_status_controls_and_no_terminal_actions(self):
        job = self.job("processing")
        response = self.client.get(reverse("translator:job_detail", args=[job.pk]))
        self.assertContains(response, 'data-initial-status="processing"')
        self.assertContains(response, 'id="status-monitor-network"')
        self.assertContains(response, "Check status now")
        self.assertNotContains(response, 'id="translation-terminal-overlay"')


def chrome_binary():
    candidates = [os.environ.get("LINGOKATUTUBO_TEST_CHROME"), shutil.which("google-chrome"),
                  shutil.which("chromium"), r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
    return next((value for value in candidates if value and Path(value).is_file()), None)


class Chrome:
    """Small CDP client using the already installed Chrome and websockets."""
    def __init__(self):
        from websockets.sync.client import connect
        self.profile = tempfile.TemporaryDirectory(prefix="t04-chrome-", ignore_cleanup_errors=True)
        self.process = subprocess.Popen([
            chrome_binary(), "--headless=new", "--remote-debugging-port=0",
            f"--user-data-dir={self.profile.name}", "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "--disable-extensions", "--disable-sync", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            port_file = Path(self.profile.name) / "DevToolsActivePort"
            deadline = time.monotonic() + 15
            while True:
                try:
                    port = port_file.read_text().splitlines()[0]
                    if port.isdigit():
                        break
                except (FileNotFoundError, PermissionError, IndexError):
                    # Windows can expose the file before Chrome releases its
                    # write handle or finishes writing the port number.
                    pass
                if time.monotonic() > deadline:
                    raise TimeoutError("Headless Chrome did not start")
                if self.process.poll() is not None:
                    raise RuntimeError("Headless Chrome exited before publishing its port")
                time.sleep(0.1)
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as response:
                target = next(item for item in json.load(response) if item["type"] == "page")
            self.ws = connect(target["webSocketDebuggerUrl"], proxy=None, max_size=8 * 1024 * 1024)
            self.number = 0
            self.errors = []
            self.call("Runtime.enable")
            self.call("Page.enable")
        except BaseException:
            self.close()
            raise

    def call(self, method, params=None):
        self.number += 1
        number = self.number
        self.ws.send(json.dumps({"id": number, "method": method, "params": params or {}}))
        while True:
            result = json.loads(self.ws.recv(timeout=15))
            if result.get("method") == "Runtime.exceptionThrown":
                self.errors.append(result["params"])
            if result.get("id") == number:
                if "error" in result:
                    raise AssertionError(result["error"])
                return result.get("result", {})

    def evaluate(self, expression):
        result = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in result:
            raise AssertionError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    def wait(self, expression, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.evaluate(expression):
                    return
            except AssertionError as exc:
                if "context" not in str(exc).lower():
                    raise
            time.sleep(0.1)
        raise AssertionError(f"Browser condition timed out: {expression}")

    def navigate(self, url):
        self.call("Page.navigate", {"url": url})
        self.wait(f"location.href === {json.dumps(url)} && document.readyState === 'complete'")

    def choose(self, path):
        doc = self.call("DOM.getDocument")
        node = self.call("DOM.querySelector", {"nodeId": doc["root"]["nodeId"], "selector": "#translate-file"})
        self.call("DOM.setFileInputFiles", {"nodeId": node["nodeId"], "files": [str(path)]})

    def close(self):
        if hasattr(self, "ws"):
            self.ws.close()
        if hasattr(self, "process"):
            self.process.terminate()
            self.process.wait(timeout=10)
        self.profile.cleanup()


@skipUnless(chrome_binary() and importlib.util.find_spec("websockets"), "Installed Chrome/websockets required; no dependencies installed")
class WorkflowBrowserTests(WorkflowFixtures, StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        self.browser = Chrome()
        self.addCleanup(self.browser.close)
        self.browser.call("Network.setCookie", {"name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value, "url": self.live_server_url})

    def visit(self, name, job=None):
        self.browser.navigate(self.live_server_url + reverse("translator:" + name, args=[job.pk] if job else []))

    def submit(self, path=None):
        self.browser.choose(path or self.pdf(self.root / "incoming.pdf", "alert"))
        self.browser.evaluate("document.querySelector('#translate-flow-form').requestSubmit(); document.querySelector('#translate-flow-form').requestSubmit()")

    def test_202_navigation_duplicate_click_guard_and_back_restore(self):
        with patch("translator.services.submit_translation_task") as dispatch:
            self.visit("translate")
            self.submit()
            self.browser.wait("!!document.querySelector('[data-status-poller]')")
            self.assertEqual(TranslationJob.objects.count(), 1)
            dispatch.assert_called_once()
            job = TranslationJob.objects.get()
            self.assertIn(job.job_id, self.browser.evaluate("location.pathname"))
            self.visit("translate")
            self.assertEqual(self.browser.evaluate("document.querySelector('#translate-error-title').textContent"), "Your upload was accepted")
            self.assertTrue(self.browser.evaluate("document.querySelector('#translate-start').disabled"))
            self.assertEqual(TranslationJob.objects.count(), 1)
        self.assertEqual(self.browser.errors, [])

    def test_dispatch_uncertainty_survives_refresh_without_resubmit(self):
        with patch("translator.services.submit_translation_task", side_effect=JobPersistenceError("private broker")) as dispatch:
            self.visit("translate")
            self.submit()
            self.browser.wait("document.querySelector('#translate-error-title').textContent.includes('could not be confirmed')")
            job = TranslationJob.objects.get()
            self.assertIn(job.job_id, self.browser.evaluate("document.querySelector('#translate-review-upload').href"))
            self.visit("translate")
            self.assertIn("could not be confirmed", self.browser.evaluate("document.querySelector('#translate-error-title').textContent"))
            self.browser.evaluate("document.querySelector('#translate-flow-form').requestSubmit()")
            self.assertEqual(TranslationJob.objects.count(), 1)
            dispatch.assert_called_once()
            self.assertNotIn("private broker", self.browser.evaluate("document.body.innerText"))

    def test_network_loss_and_non_json_response_do_not_offer_automatic_retry(self):
        for body in ["throw new TypeError('private network')", "return new Response('<html>private server</html>', {status:503, headers:{'content-type':'text/html'}})"]:
            self.visit("translate")
            self.browser.evaluate("sessionStorage.clear(); window.fetch = async () => {" + body + "};")
            self.submit()
            self.browser.wait("!document.querySelector('#translate-error-stage').hidden")
            self.assertIn("could not be confirmed", self.browser.evaluate("document.querySelector('#translate-error-title').textContent"))
            self.assertTrue(self.browser.evaluate("document.querySelector('#translate-start').disabled"))
            self.assertNotIn("private", self.browser.evaluate("document.body.innerText"))
            self.assertEqual(TranslationJob.objects.count(), 0)
            self.browser.evaluate("sessionStorage.clear()")

    def test_validation_failure_is_actionable_and_allows_new_selection(self):
        self.visit("translate")
        bad = self.root / "unsupported.txt"
        bad.write_text("test")
        self.browser.choose(bad)
        self.assertIn("PDF or DOCX", self.browser.evaluate("document.querySelector('#translate-error-description').textContent"))
        self.assertEqual(TranslationJob.objects.count(), 0)
        self.browser.choose(self.pdf(self.root / "valid.pdf"))
        self.assertFalse(self.browser.evaluate("document.querySelector('#translate-start').disabled"))

    def test_docx_upload_is_accepted_and_navigates_to_its_job(self):
        from docx import Document
        document = Document()
        document.add_paragraph("alert")
        path = self.root / "incoming.docx"
        document.save(path)
        with patch("translator.services.submit_translation_task"):
            self.visit("translate")
            self.submit(path)
            self.browser.wait("!!document.querySelector('[data-status-poller]')")
        self.assertEqual(TranslationJob.objects.get().file_type, "docx")

    def test_confirmed_storage_failure_is_safe_and_does_not_lock_as_uncertain(self):
        with patch("translator.views.save_uploaded_file", side_effect=OSError("private storage")):
            self.visit("translate")
            self.submit()
            self.browser.wait("!document.querySelector('#translate-error-stage').hidden")
        self.assertEqual(TranslationJob.objects.get().status, "failed")
        self.assertTrue(self.browser.evaluate("document.querySelector('#translate-review-upload').hidden"))
        self.assertFalse(self.browser.evaluate("document.querySelector('#translate-file').disabled"))
        self.assertNotIn("private storage", self.browser.evaluate("document.body.innerText"))

    def test_uncertain_status_payload_preserves_polling_without_false_terminal(self):
        job = self.job("processing")
        self.visit("job_detail", job)
        self.browser.wait("Array.from(window.LingoKatutuboPolling.controllers.values()).every(c => !c.inFlight && c.lastData)")
        self.browser.evaluate("window.fetch = async () => new Response(JSON.stringify({status_uncertain:true}), {headers:{'content-type':'application/json'}}); document.querySelector('#reload-status-button').click()")
        self.browser.wait("!document.querySelector('#status-monitor-network').hidden")
        self.assertEqual(self.browser.evaluate("window.LingoKatutuboPolling.controllers.size"), 1)
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#translation-terminal-overlay')"))

    def test_status_outage_keeps_processing_then_completion_refreshes_actions(self):
        job = self.job("processing")
        with patch("translator.views._get_owned_job", side_effect=OperationalError("private database")):
            self.visit("job_detail", job)
            self.browser.wait("!document.querySelector('#status-monitor-network').hidden")
            self.assertNotIn("Translation Failed", self.browser.evaluate("document.body.innerText"))
            self.assertNotIn("private database", self.browser.evaluate("document.body.innerText"))
        self.complete(job)
        self.browser.evaluate("document.querySelector('#reload-status-button').click()")
        self.browser.wait("!!document.querySelector('#translation-terminal-overlay')")
        self.assertIn("Translation Complete", self.browser.evaluate("document.body.innerText"))
        self.assertTrue(self.browser.evaluate("document.querySelector('#job-terminal-preview-action').getBoundingClientRect().width > 0"))
        self.visit("job_detail", job)
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#translation-job-processing-overlay')"))
        self.assertEqual(self.browser.errors, [])

    def test_processing_failure_renders_safe_terminal_state(self):
        job = self.job("processing")
        self.visit("job_detail", job)
        TranslationJob.objects.filter(pk=job.pk).update(status="failed", error="private stack trace", phase_message="private stack trace")
        self.browser.evaluate("document.querySelector('#reload-status-button').click()")
        self.browser.wait("!!document.querySelector('#translation-terminal-overlay')")
        self.assertIn("Translation Failed", self.browser.evaluate("document.body.innerText"))
        self.assertNotIn("private stack trace", self.browser.evaluate("document.body.innerText"))
        self.assertEqual(self.browser.evaluate("window.LingoKatutuboPolling.controllers.size"), 0)
        self.assertEqual(self.browser.errors, [])

    def test_preview_has_correct_sides_download_and_back_destination(self):
        job = self.job()
        self.complete(job)
        self.visit("job_preview", job)
        self.assertIn("alert", self.browser.evaluate("document.querySelector('.document-page-col').innerText"))
        self.assertIn("alisto", self.browser.evaluate("document.querySelectorAll('.document-page-col')[1].innerText"))
        self.assertIn(str(job.pk), self.browser.evaluate("document.querySelector('#preview-download').href"))
        self.browser.evaluate("document.querySelector('.preview-back-link').click()")
        self.browser.wait("location.pathname === '/translate/history/'")
        self.assertEqual(self.browser.errors, [])
