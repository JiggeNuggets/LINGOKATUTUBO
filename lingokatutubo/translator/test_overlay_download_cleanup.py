"""Focused UI/download tests; controlled jobs, isolated DB/media, real Chrome."""
import base64
from email.message import Message
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
import time
from types import SimpleNamespace
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import SimpleTestCase, TransactionTestCase
from django.urls import reverse

from .download_filenames import translated_download_filename
from .models import TranslationJob, UploadedDocument
from .test_translation_workflow import Chrome, WorkflowFixtures, chrome_binary


def filename(response):
    message = Message()
    message['Content-Disposition'] = response['Content-Disposition']
    return message.get_filename()


class DownloadNameTests(SimpleTestCase):
    def job(self, name='lesson.pdf', source='english', target='tagabawa', **metadata):
        return SimpleNamespace(original_filename=name, source_language=source,
                               target_language=target, metadata=metadata)

    def test_requested_examples(self):
        for name, source, target, expected in [
            ('lesson.pdf', 'english', 'tagabawa', 'lesson_EN_to_TBW.pdf'),
            ('story.pdf', 'tagabawa', 'filipino', 'story_TBW_to_FIL.pdf'),
            ('module.docx', 'cebuano', 'english', 'module_CEB_to_EN.pdf'),
            ('learning.docx', 'filipino', 'cebuano', 'learning_FIL_to_CEB.pdf'),
        ]:
            with self.subTest(name=name):
                self.assertEqual(translated_download_filename(self.job(name, source, target)), expected)

    def test_aliases_are_names_only_and_explicit_source_overrides_detection(self):
        for source, code in [('EN', 'EN'), ('Bagobo-Tagabawa', 'TBW'), ('tagalog', 'FIL'), ('bisaya', 'CEB')]:
            with self.subTest(source=source):
                self.assertEqual(translated_download_filename(self.job(source=source,
                    detected_language='cebuano', detection_confidence=1)), f'lesson_{code}_to_TBW.pdf')

    def test_confirmed_auto_source(self):
        self.assertEqual(translated_download_filename(self.job(source='auto',
            detected_language='english', detection_confidence=1.0, is_mixed_language=False)), 'lesson_EN_to_TBW.pdf')

    def test_uncertain_auto_is_neutral(self):
        for metadata in [{}, {'detected_language': 'english', 'detection_confidence': 0},
            {'detected_language': 'english', 'detection_confidence': 0.49},
            {'detected_language': 'english', 'detection_confidence': 1, 'is_mixed_language': True},
            {'detected_language': 'unknown', 'detection_confidence': 1}]:
            with self.subTest(metadata=metadata):
                self.assertEqual(translated_download_filename(self.job(source='auto', **metadata)), 'lesson_AUTO_to_TBW.pdf')

    def test_invalid_confidence_never_asserts_language(self):
        for confidence in [None, 'invalid', float('nan'), float('inf'), True, -1, 2]:
            with self.subTest(confidence=confidence):
                self.assertEqual(translated_download_filename(self.job(source='auto',
                    detected_language='english', detection_confidence=confidence)), 'lesson_AUTO_to_TBW.pdf')

    def test_unsafe_paths_symbols_controls_and_repeated_extensions(self):
        for name, expected in [('../lesson.pdf', 'lesson_EN_to_TBW.pdf'),
            (r'C:\fakepath\lesson.PDF.docx.pdf', 'lesson_EN_to_TBW.pdf'),
            ('bad<>:"|?*\r\n\x00name.pdf', 'bad----------name_EN_to_TBW.pdf'),
            ('...pdf', 'document_EN_to_TBW.pdf'), ('CON.pdf', '_CON_EN_to_TBW.pdf'),
            ('CON.notes.pdf', '_CON.notes_EN_to_TBW.pdf'),
            ('COM1.notes.docx', '_COM1.notes_EN_to_TBW.pdf')]:
            with self.subTest(name=name):
                actual = translated_download_filename(self.job(name))
                self.assertEqual(actual, expected)
                self.assertFalse(any(c in actual for c in '<>:"/\\|?*\r\n\x00'))

    def test_unicode_preserved_and_length_bounded(self):
        self.assertEqual(translated_download_filename(self.job('Ágpanumbalé.docx')), 'Ágpanumbalé_EN_to_TBW.pdf')
        result = translated_download_filename(self.job('á' * 250 + '.pdf'))
        self.assertLess(len(result.encode('utf-8')), 255)
        self.assertTrue(result.endswith('_EN_to_TBW.pdf'))

    def test_unknown_codes_and_bilingual_variant(self):
        self.assertEqual(translated_download_filename(self.job(source='unknown', target='invalid')), 'lesson_UNKNOWN_to_UNKNOWN.pdf')
        self.assertEqual(translated_download_filename(self.job(), bilingual=True), 'lesson_EN_to_TBW_bilingual.pdf')


class DownloadResponseTests(WorkflowFixtures, TransactionTestCase):
    def test_all_twelve_directions_serve_persisted_bytes_without_renaming_files(self):
        codes = {'english': 'EN', 'tagabawa': 'TBW', 'filipino': 'FIL', 'cebuano': 'CEB'}
        for source in codes:
            for target in codes:
                if source == target:
                    continue
                with self.subTest(source=source, target=target):
                    job = self.job('completed')
                    job.original_filename = 'lesson.pdf'
                    job.source_language, job.target_language = source, target
                    job.save()
                    output = self.output(job)
                    before = output.read_bytes()
                    response = self.client.get(reverse('translator:job_download', args=[job.id]))
                    try:
                        self.assertEqual(filename(response), f'lesson_{codes[source]}_to_{codes[target]}.pdf')
                        self.assertEqual(b''.join(response.streaming_content), before)
                        self.assertEqual(response['Content-Type'], 'application/pdf')
                    finally:
                        response.close()
                    self.assertEqual(output.read_bytes(), before)
                    self.assertEqual(job.generated_outputs.get().file_path, str(output))

    def test_auto_fallback_and_docx_source_headers(self):
        for confidence, expected in [(1.0, 'story_TBW_to_FIL.pdf'), (0.0, 'story_AUTO_to_FIL.pdf')]:
            with self.subTest(confidence=confidence):
                job = self.job('completed')
                job.original_filename, job.file_type, job.source_language = 'story.docx', 'docx', 'auto'
                job.metadata = {'detected_language': 'tagabawa', 'detection_confidence': confidence}
                job.save()
                self.output(job)
                response = self.client.get(reverse('translator:job_download', args=[job.id]))
                try:
                    self.assertEqual(filename(response), expected)
                finally:
                    response.close()

    def test_unicode_header_uses_rfc5987_and_safe_name(self):
        job = self.job('completed')
        job.original_filename = '../Ágpanumbalé\r\n.pdf'
        job.save()
        self.output(job)
        response = self.client.get(reverse('translator:job_download', args=[job.id]))
        try:
            self.assertIn("filename*=utf-8''", response['Content-Disposition'])
            self.assertEqual(filename(response), 'Ágpanumbalé_EN_to_FIL.pdf')
            self.assertNotIn('\r', response['Content-Disposition'])
            self.assertNotIn('\n', response['Content-Disposition'])
        finally:
            response.close()

    def test_bilingual_variant_and_original_download_remain_distinct(self):
        self.user.is_superuser = True
        self.user.save()
        job = self.job('completed')
        self.output(job, 'bilingual_alternating')
        response = self.client.get(reverse('translator:job_download', args=[job.id]) + '?format=bilingual')
        try:
            self.assertEqual(filename(response), 'workflow_EN_to_FIL_bilingual.pdf')
        finally:
            response.close()

    def test_pdf_and_docx_originals_keep_their_names_and_bytes(self):
        from docx import Document
        for kind in ['pdf', 'docx']:
            with self.subTest(kind=kind):
                job = self.job('completed')
                job.original_filename, job.file_type = 'source.' + kind, kind
                job.save()
                original = self.root / 'uploads' / job.job_id / job.original_filename
                original.parent.mkdir(parents=True)
                if kind == 'pdf':
                    self.pdf(original, 'alert')
                else:
                    doc = Document()
                    doc.add_paragraph('alert')
                    doc.save(original)
                UploadedDocument.objects.create(owner=self.user, job=job,
                    original_filename=job.original_filename, file_type=kind,
                    file_path=str(original), file_size_bytes=original.stat().st_size)
                response = self.client.get(reverse('translator:job_download_original', args=[job.id]))
                try:
                    self.assertEqual(filename(response), 'source.' + kind)
                    self.assertEqual(b''.join(response.streaming_content), original.read_bytes())
                finally:
                    response.close()

    def test_processing_modal_minimal_and_recovery_controls_outside(self):
        job = self.job('processing')
        response = self.client.get(reverse('translator:job_detail', args=[job.id]))
        body = response.content.decode()
        modal = re.search(r'<dialog id="translation-job-processing-overlay".*?</dialog>', body, re.S).group()
        self.assertIn('Translating...</h2>', modal)
        self.assertIn('Please wait while your document is processed.', modal)
        self.assertEqual(modal.count('<button'), 1)
        self.assertNotIn('reload-status-button', modal)
        self.assertNotIn('View document history', modal)
        self.assertNotIn('aria-valuenow', modal)
        self.assertContains(response, 'id="reload-status-button"')
        self.assertContains(response, 'id="status-monitor-network"')
        self.assertContains(response, 'role="group" aria-label="Translation status actions"')


@skipUnless(chrome_binary() and importlib.util.find_spec('websockets'), 'Installed Chrome required')
class MinimalOverlayBrowserTests(WorkflowFixtures, StaticLiveServerTestCase):
    """Actual browser/HTTP presentation tests; processing/completion use fixtures."""
    def setUp(self):
        super().setUp()
        self.browser = Chrome()
        self.addCleanup(self.browser.close)
        self.browser.call('Page.bringToFront')
        self.browser.call('Emulation.setFocusEmulationEnabled', {'enabled': True})
        self.browser.call('Network.setCookie', {'name': settings.SESSION_COOKIE_NAME,
            'value': self.client.cookies[settings.SESSION_COOKIE_NAME].value, 'url': self.live_server_url})

    def visit(self, job):
        self.browser.navigate(self.live_server_url + reverse('translator:job_detail', args=[job.id]))

    def key(self, key, code, modifiers=0):
        self.browser.call('Input.dispatchKeyEvent', {'type': 'rawKeyDown', 'key': key,
            'code': key, 'windowsVirtualKeyCode': code, 'modifiers': modifiers})
        self.browser.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': key,
            'code': key, 'windowsVirtualKeyCode': code, 'modifiers': modifiers})

    def tearDown(self):
        try:
            self.assertEqual(self.browser.errors, [])
        finally:
            super().tearDown()

    def test_desktop_tablet_mobile_and_short_landscape_geometry(self):
        job = self.job('processing')
        artifact = os.environ.get('LINGOKATUTUBO_UI_ARTIFACT_DIR')
        for width, height in [(1440, 900), (768, 1024), (390, 844), (320, 568), (812, 375), (568, 256)]:
            with self.subTest(width=width, height=height):
                self.browser.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height,
                    'deviceScaleFactor': 1, 'mobile': width < 600})
                self.visit(job)
                self.browser.wait("document.querySelector('#translation-job-processing-overlay').open")
                self.browser.wait("document.querySelector('.translating-state').getAnimations().every(a => a.playState === 'finished')")
                geometry = self.browser.evaluate("""(() => {
                  const card=document.querySelector('.translating-state'), dialog=card.closest('dialog');
                  const rect=card.getBoundingClientRect(), close=card.querySelector('button');
                  return {x:rect.x,right:rect.right,top:rect.top,bottom:rect.bottom,
                    innerWidth,innerHeight,scroll:dialog.scrollWidth,client:dialog.clientWidth,
                    buttons:card.querySelectorAll('button').length,links:card.querySelectorAll('a').length,
                    heading:card.querySelector('h2').textContent,iconWidth:card.querySelector('svg').getBoundingClientRect().width,
                    closeBottom:close.getBoundingClientRect().bottom,description:card.querySelector('p').textContent,
                    percent:card.querySelector('[aria-valuenow]') !== null}; })()""")
                self.assertGreaterEqual(geometry['x'], 0)
                self.assertLessEqual(geometry['right'], width)
                self.assertGreaterEqual(geometry['top'], 0)
                self.assertLessEqual(geometry['scroll'], geometry['client'] + 1)
                self.assertLessEqual(geometry['closeBottom'], geometry['bottom'])
                self.assertEqual((geometry['buttons'], geometry['links']), (1, 0))
                self.assertEqual(geometry['heading'], 'Translating...')
                self.assertEqual(geometry['description'], 'Please wait while your document is processed.')
                self.assertEqual(geometry['iconWidth'], 32)
                self.assertFalse(geometry['percent'])
                if artifact:
                    path = Path(artifact)
                    path.mkdir(parents=True, exist_ok=True)
                    (path / f'overlay-{width}x{height}.png').write_bytes(base64.b64decode(self.browser.call('Page.captureScreenshot')['data']))
                    (path / f'overlay-{width}x{height}.json').write_text(json.dumps(geometry, indent=2))

    def test_close_escape_focus_trap_and_visible_keyboard_ring(self):
        job = self.job('processing')
        self.visit(job)
        self.assertTrue(self.browser.evaluate("document.activeElement.matches('[data-close-translation-status]')"))
        self.key('Tab', 9)
        self.assertTrue(self.browser.evaluate("document.activeElement.matches('[data-close-translation-status]')"))
        self.key('Tab', 9, 8)
        self.assertTrue(self.browser.evaluate("document.activeElement.matches('[data-close-translation-status]')"))
        self.assertTrue(self.browser.evaluate("getComputedStyle(document.activeElement).outlineStyle !== 'none' && parseFloat(getComputedStyle(document.activeElement).outlineWidth) >= 2"))
        self.browser.evaluate("document.activeElement.click()")
        self.browser.wait("!document.body.classList.contains('translation-overlay-active')")
        self.assertEqual(self.browser.evaluate('document.activeElement.id'), 'translation-status-toggle')
        self.browser.evaluate("document.activeElement.click()")
        self.key('Escape', 27)
        self.browser.wait("!document.body.classList.contains('translation-overlay-active')")
        self.assertEqual(self.browser.evaluate('document.activeElement.id'), 'translation-status-toggle')
        self.assertTrue(self.browser.evaluate("document.querySelector('#reload-status-button').getBoundingClientRect().width > 0"))
        self.assertGreater(self.browser.evaluate("parseFloat(getComputedStyle(document.querySelector('#reload-status-button')).borderRadius)"), 0)
        tree = self.browser.call('Accessibility.getFullAXTree')['nodes']
        self.assertTrue(any(not n.get('ignored') and n.get('role', {}).get('value') == 'group'
            and n.get('name', {}).get('value') == 'Translation status actions' for n in tree))
        job.refresh_from_db()
        self.assertEqual(job.status, 'processing')

    def test_real_status_outage_retains_job_and_accessible_recovery(self):
        job = self.job('processing')
        self.visit(job)
        self.browser.call('Network.enable')
        self.browser.call('Network.setBlockedURLs', {'urls': ['*' + reverse('translator:status', args=[job.id]) + '*']})
        self.browser.evaluate('Array.from(window.LingoKatutuboPolling.controllers.values())[0].poll()')
        self.browser.wait("document.querySelector('#translation-state-description').textContent.includes('temporarily unavailable')")
        self.key('Escape', 27)
        self.assertIn('last confirmed', self.browser.evaluate("document.querySelector('#translation-status-summary').textContent"))
        self.browser.call('Network.setBlockedURLs', {'urls': []})
        self.browser.evaluate("document.querySelector('#reload-status-button').click()")
        self.browser.wait("document.querySelector('#status-monitor-network').hidden")
        self.browser.evaluate("document.querySelector('#translation-status-toggle').click()")
        self.assertEqual(self.browser.evaluate("document.querySelector('#translation-state-description').textContent"), 'Please wait while your document is processed.')
        job.refresh_from_db()
        self.assertEqual(job.status, 'processing')

    def test_completed_failed_and_preview_actions_remain_available(self):
        completed = self.job()
        self.complete(completed)
        self.visit(completed)
        self.assertFalse(self.browser.evaluate("document.querySelector('#translation-job-processing-overlay') !== null"))
        self.key('Escape', 27)
        self.assertTrue(self.browser.evaluate("document.querySelector('#job-download-action').getBoundingClientRect().width > 0"))
        self.browser.evaluate("document.querySelector('#job-preview-action').click()")
        self.browser.wait("location.pathname.includes('/preview/') && document.readyState === 'complete'")
        self.assertIn('Original Document', self.browser.evaluate('document.body.innerText'))
        self.assertIn('Translated Document', self.browser.evaluate('document.body.innerText'))
        failed = self.job('failed')
        self.visit(failed)
        self.assertIn('could not be completed', self.browser.evaluate('document.body.innerText'))
        self.assertTrue(self.browser.evaluate("document.querySelector('#translation-terminal-overlay a[href]') !== null"))

    def test_actual_browser_pdf_download_names_for_pdf_docx_and_uncertain_auto(self):
        downloads = self.root / 'browser-downloads'
        downloads.mkdir()
        self.browser.call('Browser.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': str(downloads)})
        for original, kind, source, target, metadata, expected in [
            ('lesson á.pdf', 'pdf', 'english', 'tagabawa', {}, 'lesson á_EN_to_TBW.pdf'),
            ('learning.docx', 'docx', 'filipino', 'cebuano', {}, 'learning_FIL_to_CEB.pdf'),
            ('auto.pdf', 'pdf', 'auto', 'tagabawa', {'detected_language': 'english', 'detection_confidence': 0}, 'auto_AUTO_to_TBW.pdf'),
            ('detected.pdf', 'pdf', 'auto', 'filipino', {'detected_language': 'english', 'detection_confidence': 1}, 'detected_EN_to_FIL.pdf'),
        ]:
            with self.subTest(original=original):
                job = self.job('completed')
                job.original_filename, job.file_type = original, kind
                job.source_language, job.target_language, job.metadata = source, target, metadata
                job.save()
                path = self.output(job)
                self.visit(job)
                self.key('Escape', 27)
                self.browser.evaluate("document.querySelector('#job-download-action').click()")
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline and not (downloads / expected).exists():
                    time.sleep(.1)
                self.assertTrue((downloads / expected).exists(), list(downloads.iterdir()))
                self.assertEqual((downloads / expected).read_bytes(), path.read_bytes())
