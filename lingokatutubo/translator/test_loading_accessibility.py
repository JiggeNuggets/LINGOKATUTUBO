"""T05 real-browser checks using temporary media, profiles, and test DB rows."""

import importlib.util
import base64
import os
import time
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse

from .models import TranslationJob
from .test_translation_workflow import Chrome, WorkflowFixtures, chrome_binary
from . import views


@skipUnless(chrome_binary() and importlib.util.find_spec("websockets"), "Installed Chrome/websockets required")
class LoadingBrowserTests(WorkflowFixtures, StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        for attempt in range(3):
            try:
                self.browser = Chrome()
                break
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.1)
        self.addCleanup(self.browser.close)
        self.browser.call("Page.bringToFront")
        self.browser.call("Emulation.setFocusEmulationEnabled", {"enabled": True})
        self.browser.call("Network.setCookie", {"name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value, "url": self.live_server_url})

    def visit(self, name, job=None):
        self.browser.navigate(self.live_server_url + reverse("translator:" + name, args=[job.pk] if job else []))

    def key(self, key, code, modifiers=0):
        self.browser.call("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": key, "code": key,
            "windowsVirtualKeyCode": code, "nativeVirtualKeyCode": code, "modifiers": modifiers})
        if key == "Enter":
            self.browser.call("Input.dispatchKeyEvent", {"type": "char", "text": "\r", "unmodifiedText": "\r", "modifiers": modifiers})
        self.browser.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "code": key,
            "windowsVirtualKeyCode": code, "nativeVirtualKeyCode": code, "modifiers": modifiers})


    def tearDown(self):
        try:
            self.assertEqual(self.browser.errors, [])
        finally:
            super().tearDown()

    def test_terminal_escape_dismisses_and_restores_focus_without_changing_job(self):
        job = self.job()
        self.complete(job)
        self.visit("job_detail", job)
        self.key("Escape", 27)
        self.browser.wait("!document.body.classList.contains('translation-overlay-active')")
        self.assertFalse(self.browser.evaluate("document.body.classList.contains('translation-overlay-active')"))
        self.assertEqual(self.browser.evaluate("document.activeElement.id"), "translation-status-toggle")
        self.assertTrue(self.browser.evaluate("document.querySelector('#job-preview-action').getBoundingClientRect().width > 0"))
        self.assertTrue(self.browser.evaluate("document.querySelector('#job-download-action').getBoundingClientRect().width > 0"))
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")

    def test_processing_background_is_inert_and_status_controls_are_not_busy(self):
        job = self.job("processing")
        self.visit("job_detail", job)
        self.browser.evaluate("document.querySelector('.site-header a').focus()")
        self.assertTrue(self.browser.evaluate("document.querySelector('#translation-job-processing-overlay').contains(document.activeElement)"))
        self.assertFalse(self.browser.evaluate("document.activeElement.closest('[aria-busy=true]') !== null"))

    def test_processing_can_be_dismissed_and_reopened_with_keyboard(self):
        job = self.job("processing")
        self.visit("job_detail", job)
        self.key("Escape", 27)
        self.browser.wait("!document.body.classList.contains('translation-overlay-active')")
        self.assertFalse(self.browser.evaluate("document.body.classList.contains('translation-overlay-active')"))
        self.key("Enter", 13)
        self.assertTrue(self.browser.evaluate("document.querySelector('#translation-job-processing-overlay').open"))
        self.assertEqual(self.browser.evaluate("document.querySelector('#translation-status-toggle').getAttribute('aria-expanded')"), "true")

    def test_native_dialog_has_accessible_name_and_traps_tab_keys(self):
        job = self.job("processing")
        self.visit("job_detail", job)
        tree = self.browser.call("Accessibility.getFullAXTree")["nodes"]
        dialogs = [node for node in tree if not node.get("ignored") and node.get("role", {}).get("value") == "dialog"]
        self.assertEqual(len(dialogs), 1)
        self.assertTrue(dialogs[0].get("name", {}).get("value"))
        self.browser.evaluate("document.querySelector('[data-close-translation-status]').focus()")
        self.key("Tab", 9)
        self.assertTrue(self.browser.evaluate("document.activeElement.matches('[data-close-translation-status]')"),
                        self.browser.evaluate("document.activeElement.outerHTML.slice(0,300)"))
        self.key("Tab", 9, 8)
        self.assertTrue(self.browser.evaluate("document.activeElement.matches('[data-close-translation-status]')"))

    def hang_upload(self):
        self.browser.evaluate("""window.__uploads = 0;
          window.fetch = (_url, options) => {
            window.__uploads++;
            return new Promise((_resolve, reject) => options.signal.addEventListener('abort',
              () => reject(new DOMException('private upload diagnostics', 'AbortError'))));
          };""")
        self.browser.choose(self.pdf(self.root / "pending.pdf", "alert"))
        self.browser.evaluate("document.querySelector('#translate-flow-form').requestSubmit(); document.querySelector('#translate-flow-form').requestSubmit()")
        self.browser.wait("!document.querySelector('#translate-uploading').hidden")

    def test_upload_loading_focus_busy_state_and_stop_waiting_are_safe(self):
        self.visit("translate")
        self.hang_upload()
        self.assertEqual(self.browser.evaluate("document.querySelector('#translate-flow-form').getAttribute('aria-busy')"), "true")
        self.assertEqual(self.browser.evaluate("document.activeElement.id"), "translate-uploading")
        self.assertTrue(self.browser.evaluate("document.querySelector('#translate-upload-announcement').closest('[aria-busy=true]') === null"))
        self.key("Tab", 9)
        self.assertEqual(self.browser.evaluate("document.activeElement.id"), "translate-stop-waiting")
        self.key("Enter", 13)
        self.browser.wait("!document.querySelector('#translate-error-stage').hidden")
        self.assertEqual(self.browser.evaluate("document.querySelector('#translate-flow-form').getAttribute('aria-busy')"), "false")
        self.assertEqual(self.browser.evaluate("document.activeElement.id"), "translate-review-upload")
        self.assertIn("could not be confirmed", self.browser.evaluate("document.body.innerText"))
        self.assertNotIn("private upload", self.browser.evaluate("document.body.innerText"))
        self.assertEqual(self.browser.evaluate("window.__uploads"), 1)
        self.assertEqual(TranslationJob.objects.count(), 0)

    def test_upload_deadline_retains_uncertainty_and_never_reposts(self):
        self.visit("translate")
        self.browser.evaluate("""const realTimer = window.setTimeout;
          window.setTimeout = (fn, ms, ...args) => {
            if (ms === 120000) { window.__deadline = fn; return realTimer(() => {}, 20000); }
            return realTimer(fn, ms, ...args);
          };""")
        self.hang_upload()
        self.browser.evaluate("window.__deadline()")
        self.browser.wait("!document.querySelector('#translate-error-stage').hidden")
        self.assertTrue(self.browser.evaluate("document.querySelector('#translate-start').disabled"))
        self.assertIn("could not be confirmed", self.browser.evaluate("document.body.innerText"))
        self.assertEqual(self.browser.evaluate("window.__uploads"), 1)

    def test_repeated_polls_do_not_repeat_unchanged_live_text_and_outage_is_safe(self):
        job = self.job("processing")
        self.visit("job_detail", job)
        self.browser.wait("Array.from(window.LingoKatutuboPolling.controllers.values()).every(c => c.lastData && !c.inFlight)")
        self.browser.evaluate("""window.__changes = 0;
          new MutationObserver(records => window.__changes += records.length).observe(
            document.querySelector('#translation-state-description'), {childList:true, subtree:true});
          Array.from(window.LingoKatutuboPolling.controllers.values())[0].poll();""")
        self.browser.wait("Array.from(window.LingoKatutuboPolling.controllers.values()).every(c => !c.inFlight)")
        self.assertEqual(self.browser.evaluate("window.__changes"), 0)
        self.key("Escape", 27)
        self.browser.evaluate("window.fetch = async () => {throw new SyntaxError('private response excerpt')}; Array.from(window.LingoKatutuboPolling.controllers.values())[0].poll()")
        self.browser.wait("document.querySelector('#translation-status-summary').textContent.includes('last confirmed')")
        self.assertNotIn("private response", self.browser.evaluate("document.body.innerText"))
        job.refresh_from_db()
        self.assertEqual(job.status, "processing")

    @contextmanager
    def hold_preview(self):
        entered, release, finished = Event(), Event(), Event()
        original = views._image_preview_context

        def held(job):
            entered.set()
            try:
                if not release.wait(timeout=15):
                    raise TimeoutError("Isolated preview fixture timed out")
                return original(job)
            finally:
                finished.set()
        with patch("translator.views._image_preview_context", side_effect=held):
            try:
                yield entered
            finally:
                release.set()
                if entered.is_set():
                    finished.wait(timeout=5)

    def test_preview_loading_cancel_restores_terminal_actions_and_focus(self):
        job = self.job()
        self.complete(job)
        self.visit("job_detail", job)
        with self.hold_preview() as entered:
            # Capture state in-page: CDP Runtime inspection waits for an active
            # navigation to settle, while real keyboard input remains available.
            self.browser.evaluate("""setTimeout(() => {
              window.__loadingObservation = {open:document.querySelector('#page-transition-overlay').open,
                focus:document.activeElement.id};
            }, 100); setTimeout(() => document.querySelector('#job-terminal-preview-action').click(), 0); true""")
            self.assertTrue(entered.wait(timeout=5), "Preview request must start immediately")
            self.key("Escape", 27)
            state = self.browser.evaluate("window.__loadingObservation")
            self.assertTrue(state["open"])
            self.assertEqual(state["focus"], "cancel-preview-opening")
            self.assertFalse(self.browser.evaluate("document.querySelector('#page-transition-overlay').open"))
            self.assertEqual(self.browser.evaluate("document.activeElement.id"), "job-terminal-preview-action")
            self.assertFalse(self.browser.evaluate("document.querySelector('#job-terminal-preview-action').hasAttribute('aria-disabled')"))
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")

    def test_preview_timeout_remains_active_until_navigation_finishes(self):
        job = self.job()
        self.complete(job)
        self.visit("job_detail", job)
        self.browser.evaluate("""const realTimer = window.setTimeout;
          window.setTimeout = (fn, ms, ...args) => {
            if (ms === 12000) { window.__previewTimeout = fn; return realTimer(() => {}, 20000); }
            return realTimer(fn, ms, ...args);
          };
          window.addEventListener('keydown', event => {
            if (event.key === 'F8') window.__previewTimeout();
          });""")
        with self.hold_preview() as entered:
            self.browser.evaluate("setTimeout(() => document.querySelector('#job-terminal-preview-action').click(), 0); true")
            self.assertTrue(entered.wait(timeout=5))
            self.key("F8", 119)
            self.assertFalse(self.browser.evaluate("document.querySelector('#page-transition-overlay').open"))
            self.assertIn("Your translation is unchanged", self.browser.evaluate("document.querySelector('[data-preview-error]').textContent"))
            self.assertTrue(self.browser.evaluate("document.querySelector('[data-preview-error]').getBoundingClientRect().width > 0"))
            self.assertEqual(self.browser.evaluate("document.activeElement.id"), "job-terminal-preview-action")

    def test_preview_navigation_and_history_return_clear_loading_state(self):
        job = self.job()
        self.complete(job)
        self.visit("job_detail", job)
        self.browser.evaluate("document.querySelector('#job-terminal-preview-action').click()")
        self.browser.wait("!!document.querySelector('#preview-app')")
        self.assertFalse(self.browser.evaluate("document.querySelector('#page-transition-overlay').open"))
        self.visit("job_detail", job)
        self.assertFalse(self.browser.evaluate("document.querySelector('#job-terminal-preview-action').classList.contains('is-loading')"))

    def test_uncertainty_recovery_restores_file_focus_and_known_error_guidance(self):
        self.visit("translate")
        self.hang_upload()
        self.browser.evaluate("document.querySelector('#translate-stop-waiting').click()")
        self.browser.wait("!document.querySelector('#translate-error-stage').hidden")
        self.browser.evaluate("document.querySelector('#translate-file').click = () => {}; document.querySelector('#translate-try-again').click()")
        self.assertEqual(self.browser.evaluate("document.activeElement.id"), "translate-file")
        path = self.root / "invalid.txt"
        path.write_text("test")
        self.browser.choose(path)
        self.assertEqual(self.browser.evaluate("document.querySelector('#translate-error-stage').getAttribute('role')"), "alert")
        self.assertEqual(self.browser.evaluate("document.querySelector('#translate-try-again').textContent"), "Choose a document to try again")

    def test_mobile_and_short_viewports_keep_dialog_controls_reachable(self):
        self.browser.call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
        for status in ("processing", "completed", "failed"):
            job = self.job(status)
            for width, height in ((320, 568), (568, 320), (1280, 800)):
                self.browser.call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 600})
                self.visit("job_detail", job)
                self.assertTrue(self.browser.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
                self.browser.evaluate("document.querySelector('[data-close-translation-status]').scrollIntoView({block:'center'})")
                self.assertTrue(self.browser.evaluate("""(() => {
                  const r = document.querySelector('[data-close-translation-status]').getBoundingClientRect();
                  return r.width >= 44 && r.height >= 44 && r.left >= 0 && r.right <= innerWidth + 1 && r.top >= 0 && r.bottom <= innerHeight;
                })()"""))
                if os.environ.get("LINGOKATUTUBO_T05_SCREENSHOTS") and status == "completed":
                    path = Path(os.environ["LINGOKATUTUBO_T05_SCREENSHOTS"]) / f"completed-{width}x{height}.png"
                    data = self.browser.call("Page.captureScreenshot", {"format": "png"})["data"]
                    path.write_bytes(base64.b64decode(data))

    def test_focused_notification_and_reserved_error_region_do_not_disappear(self):
        job = self.job("completed")
        self.visit("job_detail", job)
        self.key("Escape", 27)
        self.browser.wait("!document.body.classList.contains('translation-overlay-active')")
        self.browser.evaluate("document.querySelector('#messages-region .message-dismiss').focus()")
        self.browser.evaluate("new Promise(resolve => setTimeout(resolve, 3300))")
        self.assertTrue(self.browser.evaluate("!!document.querySelector('#messages-region .message')"))
        self.assertTrue(self.browser.evaluate("!!document.querySelector('#js-error-banner')"))
