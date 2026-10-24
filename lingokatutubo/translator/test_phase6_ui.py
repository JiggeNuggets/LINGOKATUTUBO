from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse
from pathlib import Path
from django.conf import settings

from .models import PhrasebookEntry, TranslationJob


class Phase6InterfaceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user("phase6-learner", password="safe-password")
        self.other_user = user_model.objects.create_user("phase6-other", password="safe-password")
        self.job = TranslationJob.objects.create(
            owner=self.user,
            original_filename="lesson.txt",
            file_type=TranslationJob.FileType.TXT,
            source_language="english",
            target_language="tagabawa",
            status=TranslationJob.Status.QUEUED,
        )

    def test_upload_has_accessible_progress_and_error_states(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("translator:translate"))
        self.assertContains(response, 'id="translate-flow-form"')
        self.assertContains(response, 'aria-describedby="translate-file-help translate-file-feedback"')
        self.assertContains(response, 'id="translate-uploading" hidden role="status"')
        self.assertContains(response, 'id="translate-error-stage" hidden role="alert"')
        self.assertContains(response, 'data-max-file-bytes="52428800"')

    def test_dashboard_and_result_include_actionable_phase6_components(self):
        self.client.force_login(self.user)
        dashboard = self.client.get(reverse("translator:dashboard"))
        self.assertContains(dashboard, "Welcome, phase6-learner")
        detail = self.client.get(reverse("translator:job_detail", args=[self.job.id]))
        self.assertContains(detail, 'id="translation-job-processing-overlay"')
        self.assertContains(detail, 'class="translation-processing-overlay job-processing-overlay"')
        self.assertContains(detail, "Translating")
        self.assertContains(detail, 'id="translation-progress" class="translation-loading-progress"', html=False)
        self.assertNotContains(detail, ">CHECK</a>")

    def test_upload_script_validates_before_post_and_recovers_from_failure(self):
        script = (Path(settings.BASE_DIR) / "static" / "js" / "translate-flow.js").read_text(encoding="utf-8")
        self.assertIn('if (busy || !validateFile(fileInput.files[0])) return;', script)
        self.assertIn('if (file.size > maxBytes)', script)
        self.assertIn('if (!contentType.includes("application/json"))', script)
        self.assertIn('showError(error.message', script)
        self.assertIn("window.location.assign", script)

    def test_processing_card_hides_raw_step_and_uses_indeterminate_progress(self):
        self.job.current_step = "Worker accepted the job"
        self.job.current_phase = "extracting"
        self.job.save(update_fields=["current_step", "current_phase"])
        self.client.force_login(self.user)
        response = self.client.get(reverse("translator:job_detail", args=[self.job.id]))
        body = response.content.decode("utf-8")
        self.assertNotIn("Worker accepted the job", body)
        self.assertIn('aria-busy="true"', body)
        self.assertIn('id="translation-progress" class="translation-loading-progress"', body)
        self.assertIn("Translation is continuing in the background", body)
        self.assertNotIn('class="translation-result-banner', body)

    def test_terminal_job_replaces_processing_overlay_with_server_rendered_actions(self):
        self.client.force_login(self.user)
        self.job.status = TranslationJob.Status.COMPLETED
        self.job.save(update_fields=["status"])

        response = self.client.get(reverse("translator:job_detail", args=[self.job.id]))
        body = response.content.decode("utf-8")
        self.assertNotIn('id="translation-job-processing-overlay"', body)
        self.assertIn('id="translation-terminal-overlay"', body)
        self.assertIn("Translation Complete", body)
        self.assertIn(">CHECK</a>", body)
        self.assertIn(reverse("translator:job_preview", args=[self.job.id]), body)

    def test_translate_page_keeps_labels_and_a_safe_language_swap_control(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("translator:translate"))
        body = response.content.decode("utf-8")
        self.assertIn('for="translate-source">From</label>', body)
        self.assertIn('for="translate-target">To</label>', body)
        self.assertIn('id="translate-swap"', body)
        script = (Path(settings.BASE_DIR) / "static" / "js" / "translate-flow.js").read_text(encoding="utf-8")
        self.assertIn('swap.disabled = busy || source.value === "auto"', script)
        self.assertIn('source.value = target.value', script)
        self.assertIn('target.value = oldSource', script)

    def test_completed_failed_and_partial_states_have_safe_actions(self):
        self.client.force_login(self.user)
        self.job.status = TranslationJob.Status.COMPLETED
        self.job.save(update_fields=["status"])
        completed = self.client.get(reverse("translator:job_detail", args=[self.job.id]))
        self.assertContains(completed, "Translation Complete")
        self.assertContains(completed, "Translation Complete")
        self.assertContains(completed, ">CHECK</a>", html=False)
        self.assertNotContains(completed, "Download choices")

        self.job.status = TranslationJob.Status.FAILED
        self.job.error = "private/server/path traceback"
        self.job.save(update_fields=["status", "error"])
        failed = self.client.get(reverse("translator:job_detail", args=[self.job.id]))
        self.assertContains(failed, "Failed")
        self.assertContains(failed, "Try Again")
        self.assertContains(failed, "Translation Failed")
        self.assertNotContains(failed, ">CHECK</a>", html=False)
        self.assertNotContains(failed, "private/server/path traceback")

        self.job.status = TranslationJob.Status.COMPLETED
        self.job.metadata = {"partial_processing": True}
        self.job.save(update_fields=["status", "metadata"])
        partial = self.client.get(reverse("translator:job_detail", args=[self.job.id]))
        self.assertContains(partial, "Translation Complete")
        self.assertNotContains(partial, "Only part of this document was processed")

    def test_reduced_motion_rules_and_real_progress_flag_exist(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn(".translation-language-line", css)
        self.assertIn(".translation-loading-progress", css)
        self.assertIn("translation-progress-slide", css)
        self.assertIn("position: fixed", css)
        self.client.force_login(self.user)
        payload = self.client.get(reverse("translator:status", args=[self.job.id])).json()
        self.assertIs(payload["progress_available"], False)
        self.assertIsNone(payload["progress_percent"])

    def test_downloads_remain_owner_scoped(self):
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("translator:job_download_original", args=[self.job.id]))
        self.assertEqual(response.status_code, 404)

    def test_validator_queue_uses_permission_and_status_text(self):
        PhrasebookEntry.objects.create(english="water", tagabawa="tubig", validation_status="pending")
        self.client.force_login(self.user)
        forbidden = self.client.get(reverse("translator:validator_queue"))
        self.assertEqual(forbidden.status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(codename="review_language_entry"))
        response = self.client.get(reverse("translator:validator_queue"))
        self.assertContains(response, "Language resource review queue")
        self.assertContains(response, "Needs validation")


class TranslationRoleVisibilityTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.learner = user_model.objects.create_user("role-learner", password="safe-password")
        self.teacher = user_model.objects.create_user("role-teacher", password="safe-password")
        self.validator = user_model.objects.create_user("role-validator", password="safe-password")
        self.administrator = user_model.objects.create_user(
            "role-administrator", password="safe-password", is_staff=True
        )
        self.superuser = user_model.objects.create_superuser(
            "role-superuser", "superuser@example.test", "safe-password"
        )
        teacher_group, _ = Group.objects.get_or_create(name="Teacher")
        self.teacher.groups.add(teacher_group)
        self.validator.user_permissions.add(
            Permission.objects.get(codename="review_language_entry")
        )
        self.job = TranslationJob.objects.create(
            owner=self.learner,
            original_filename="community-story.txt",
            file_type=TranslationJob.FileType.TXT,
            source_language="english",
            target_language="tagabawa",
            status=TranslationJob.Status.COMPLETED,
            metadata={"partial_processing": True, "extraction_method": "ocr_image"},
        )
        TranslationSegment = self.job.segments.model
        TranslationSegment.objects.create(
            job=self.job,
            segment_index=1,
            source_text="Untranslated community term",
            translated_text="Untranslated community term",
            source_language="english",
            target_language="tagabawa",
            method="no_match",
            confidence=0,
            needs_review=True,
            metadata={"provenance_status": "unverified"},
        )

    def test_learner_hides_review_and_technical_surfaces(self):
        self.client.force_login(self.learner)
        detail = self.client.get(reverse("translator:job_detail", args=[self.job.id]))
        preview = self.client.get(reverse("translator:job_preview", args=[self.job.id]))
        payload = self.client.get(reverse("translator:preview_data", args=[self.job.id])).json()
        self.assertContains(detail, "Translation Complete")
        self.assertContains(detail, "Some text may remain unchanged when a suitable translation is unavailable.")
        self.assertNotContains(detail, "Details")
        self.assertNotContains(detail, "Translation Confidence")
        self.assertNotContains(preview, "Text and validation markers")
        self.assertNotContains(preview, "Needs validation")
        self.assertNotContains(preview, "Suggest a correction")
        self.assertContains(preview, "preview-back-link")
        self.assertContains(preview, "data-back-action")
        self.assertNotIn("method", payload["segments"][0])
        self.assertNotIn("confidence", payload["segments"][0])
        self.assertNotIn("metadata", payload["segments"][0])

    def test_learner_cannot_access_validator_artifacts(self):
        self.client.force_login(self.learner)
        manifest = self.client.get(reverse("translator:review_manifest", args=[self.job.id]))
        structure = self.client.get(reverse("translator:structure", args=[self.job.id]))
        bilingual = self.client.get(
            reverse("translator:job_download", args=[self.job.id]) + "?format=bilingual"
        )

        self.assertEqual(manifest.status_code, 403)
        self.assertEqual(structure.status_code, 403)
        self.assertEqual(bilingual.status_code, 403)

    def test_teacher_gets_review_copy_without_validator_markers(self):
        self.job.owner = self.teacher
        self.job.save(update_fields=["owner"])
        self.client.force_login(self.teacher)

        detail = self.client.get(reverse("translator:job_detail", args=[self.job.id]))
        preview = self.client.get(reverse("translator:job_preview", args=[self.job.id]))

        self.assertContains(detail, "Teacher review copy")
        self.assertNotContains(detail, "Translation Confidence")
        self.assertNotContains(preview, "Text and validation markers")

    def test_validator_gets_detailed_markers_and_manifest(self):
        self.job.owner = self.validator
        self.job.save(update_fields=["owner"])
        self.client.force_login(self.validator)

        preview = self.client.get(reverse("translator:job_preview", args=[self.job.id]))
        payload = self.client.get(reverse("translator:preview_data", args=[self.job.id])).json()
        manifest = self.client.get(reverse("translator:review_manifest", args=[self.job.id]))

        self.assertContains(preview, "Text and validation markers")
        self.assertContains(preview, "Needs validation")
        self.assertIn("method", payload["segments"][0])
        self.assertEqual(manifest.status_code, 200)

    def test_administrator_is_not_implicitly_a_validator(self):
        self.client.force_login(self.administrator)
        dashboard = self.client.get(reverse("translator:dashboard"))
        queue = self.client.get(reverse("translator:validator_queue"))
        health = self.client.get(reverse("translator:health"))

        self.assertContains(dashboard, "Administration")
        self.assertEqual(queue.status_code, 403)
        self.assertEqual(health.status_code, 403)

    def test_superuser_can_see_diagnostics(self):
        self.job.owner = self.superuser
        self.job.status = TranslationJob.Status.FAILED
        self.job.error = "internal OCR trace"
        self.job.save(update_fields=["owner", "status", "error"])
        self.client.force_login(self.superuser)

        detail = self.client.get(reverse("translator:job_detail", args=[self.job.id]))
        health = self.client.get(reverse("translator:health"))

        self.assertContains(detail, "Technical Details")
        self.assertContains(detail, "internal OCR trace")
        self.assertEqual(health.status_code, 200)
