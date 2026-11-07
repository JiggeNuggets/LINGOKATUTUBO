"""T03 lifecycle tests: isolated Django test database and temporary media only."""

import io
import json
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock, patch

import fitz
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError, close_old_connections, connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from . import services
from .management.commands.recover_stale_jobs import Command
from .models import GeneratedOutput, SystemEventLog, TranslationJob, UploadedDocument
from .services.detection_service import DetectionService
from .services.extraction_service import ExtractionService
from .services.job_lifecycle import JobPersistenceError, PROCESSING_FAILURE_MESSAGE
from .services.language_detection_service import LanguageDetectionService
from .services.models import FileType
from .services.pipeline_service import JobStatus, PipelineService
from .services.reconstruction_service import ReconstructionService
from .services.task_runner import submit_translation_task
from .services.translation_dataset import TranslationDataset


class JobLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create(username="lifecycle-test-user")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lingokatutubo-t03-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings_context = override_settings(
            MEDIA_ROOT=self.root, LINGOKATUTUBO_TASK_MODE="inline",
            LINGOKATUTUBO_NEURAL_TRANSLATION_ENABLED=False,
        )
        self.settings_context.enable()
        self.addCleanup(self.settings_context.disable)
        self.patch_connections = patch("translator.services.close_old_connections")
        self.patch_connections.start()
        self.addCleanup(self.patch_connections.stop)
        self.patch_files = patch.object(services.file_service_module, "_file_service", None)
        self.patch_files.start()
        self.addCleanup(self.patch_files.stop)
        cache.clear()
        self.client.force_login(self.user)

    @staticmethod
    def uploaded_pdf():
        with fitz.open() as doc:
            doc.new_page().insert_text((72, 100), "alert")
            content = doc.tobytes()
        return SimpleUploadedFile("lifecycle.pdf", content, content_type="application/pdf")

    def new_job(self, status="queued"):
        return TranslationJob.objects.create(
            owner=self.user, original_filename="lifecycle.pdf", file_type="pdf",
            source_language="english", target_language="filipino", status=status,
        )

    def make_pipeline(self):
        pipeline = PipelineService.__new__(PipelineService)
        pipeline.file_service = services._get_file_service()
        pipeline.detection_service = DetectionService()
        pipeline.extraction_service = ExtractionService()
        pipeline.reconstruction_service = ReconstructionService()
        pipeline.translation_dataset = TranslationDataset(
            str(Path(__file__).parent / "services" / "translation_data.json"),
            include_default_corpus=False, include_validated_imports=False,
            data_mode="development_unverified",
        )
        pipeline.language_service = LanguageDetectionService(pipeline.translation_dataset)
        pipeline.ocr_service = Mock()
        pipeline.jobs = {}
        pipeline.job_update_callback = services.sync_pipeline_job
        return pipeline

    def stored_job(self):
        job = self.new_job()
        paths = services.save_uploaded_file(self.uploaded_pdf(), job.job_id)
        job.input_file_path = paths["input_file_path"]
        job.upload_file_path = paths["upload_file_path"]
        job.save()
        return job

    def run_worker(self, job, pipeline):
        with patch("translator.services._get_pipeline_service", return_value=pipeline):
            services._run_translation_job(job.job_id, job.input_file_path, "pdf", "english", "filipino", None)
        job.refresh_from_db()

    def upload(self):
        return self.client.post(reverse("translator:upload"), {
            "file": self.uploaded_pdf(), "source_language": "english", "target_language": "filipino",
        })

    def completed_checkpoint(self, job):
        file_service = services._get_file_service()
        output = Path(file_service.get_output_path(job.job_id, "translated.pdf"))
        output.write_bytes(b"retained test output")
        structure = Path(file_service.get_job_dir(job.job_id)) / "structure.json"
        structure.write_text(json.dumps({"pages": []}), encoding="utf-8")
        checkpoint = JobStatus(job.job_id)
        checkpoint.status = "completed"
        checkpoint.current_phase = "completed"
        checkpoint.metadata["structure_file"] = str(structure)
        return checkpoint, output

    def make_stale(self, job):
        old = timezone.now() - timezone.timedelta(minutes=30)
        TranslationJob.objects.filter(pk=job.pk).update(updated_at=old)
        job.refresh_from_db()

    def test_successful_upload_through_persisted_completion(self):
        pipeline = self.make_pipeline()
        with patch("translator.services._get_pipeline_service", return_value=pipeline):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.upload()
        self.assertEqual(response.status_code, 202)
        job = TranslationJob.objects.get(pk=response.json()["job_id"])
        self.assertEqual(job.status, "completed")
        self.assertTrue(Path(job.upload_file_path).is_file())
        self.assertTrue(Path(job.output_file_path).is_file())
        self.assertEqual(job.segments.count(), 1)
        segment = job.segments.get()
        self.assertEqual(segment.source_text, "alert")
        self.assertEqual(segment.translated_text, "alisto")
        with fitz.open(job.output_file_path) as translated:
            # PDF reconstruction may wrap this word in the source text box.
            self.assertEqual("".join(translated[0].get_text().split()), "alisto")
        self.assertTrue(UploadedDocument.objects.filter(job=job).exists())
        self.assertTrue(GeneratedOutput.objects.filter(job=job).exists())
        self.assertEqual(pipeline.ocr_service.mock_calls, [])

    def test_validation_failure_does_not_create_or_dispatch_job(self):
        with patch("translator.views.start_translation_job") as dispatch:
            response = self.client.post(reverse("translator:upload"), {"source_language": "english"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TranslationJob.objects.count(), 0)
        dispatch.assert_not_called()

    def test_file_storage_exception_marks_created_job_failed(self):
        with patch("translator.views.save_uploaded_file", side_effect=OSError("private storage path")), patch("translator.views.start_translation_job") as dispatch:
            response = self.upload()
        self.assertEqual(response.status_code, 500)
        job = TranslationJob.objects.get()
        self.assertEqual(job.status, "failed")
        self.assertIsNotNone(job.completed_at)
        self.assertNotIn("private storage path", response.content.decode())
        self.assertEqual(UploadedDocument.objects.count(), 0)
        dispatch.assert_not_called()

    def test_partial_initialization_rolls_back_related_rows_and_retains_original(self):
        with patch("translator.views.UserActivityLog.objects.create", side_effect=RuntimeError("audit failure")):
            response = self.upload()
        job = TranslationJob.objects.get()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(job.status, "failed")
        self.assertEqual(UploadedDocument.objects.count(), 0)
        self.assertTrue(Path(job.upload_file_path).is_file())
        self.assertTrue(Path(job.input_file_path).is_file())

    def test_upload_database_unavailable_reports_uncertainty_without_false_failure(self):
        with patch("translator.views.TranslationJob.objects.filter", side_effect=OperationalError("private database endpoint")):
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.json()["status_uncertain"])
        self.assertEqual(response.json()["error_code"], "database_unavailable")
        self.assertNotIn("private database endpoint", response.content.decode())

    def test_database_failure_after_job_creation_does_not_claim_failed_state(self):
        with patch("translator.views._initialize_uploaded_document", side_effect=OperationalError("offline")):
            response = self.upload()
        job = TranslationJob.objects.get()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(job.status, "queued")
        self.assertTrue(response.json()["status_uncertain"])
        self.assertEqual(response.json()["job_id"], job.job_id)

    def test_dispatch_startup_failure_marks_job_failed(self):
        job = self.stored_job()
        with patch("translator.services.submit_translation_task", side_effect=RuntimeError("thread startup failed")):
            with self.captureOnCommitCallbacks(execute=True):
                outcome = services.start_translation_job(job)
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertEqual(outcome["status"], "failed")
        self.assertTrue(Path(job.upload_file_path).exists())

    def test_accepted_dispatch_log_failure_does_not_fail_or_repeat_job(self):
        job = self.new_job()
        with patch("translator.services.submit_translation_task") as submit, patch("translator.services.SystemEventLog.objects.create", side_effect=OperationalError("audit unavailable")):
            with self.captureOnCommitCallbacks(execute=True):
                outcome = services.start_translation_job(job)
        job.refresh_from_db()
        submit.assert_called_once()
        self.assertEqual(outcome["status"], "accepted")
        self.assertEqual(job.status, "queued")

    def test_uncertain_dispatch_does_not_fail_or_retry_job(self):
        job = self.new_job()
        with patch("translator.services.submit_translation_task", side_effect=JobPersistenceError("broker acknowledgement lost")) as submit:
            with self.captureOnCommitCallbacks(execute=True):
                outcome = services.start_translation_job(job)
        job.refresh_from_db()
        self.assertEqual(outcome["status"], "uncertain")
        self.assertEqual(job.status, "queued")
        self.assertTrue(job.metadata["dispatch_uncertain"])
        submit.assert_called_once()

    def test_upload_reports_uncertain_dispatch_without_creating_replacement(self):
        with patch("translator.views.start_translation_job", return_value={"status": "uncertain"}) as dispatch:
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error_code"], "dispatch_uncertain")
        self.assertTrue(response.json()["status_uncertain"])
        self.assertEqual(TranslationJob.objects.count(), 1)
        self.assertEqual(TranslationJob.objects.get().status, "queued")
        dispatch.assert_called_once()

    def test_processing_exception_is_failed_with_safe_public_message(self):
        job = self.stored_job()
        pipeline = self.make_pipeline()
        pipeline.extraction_service = Mock()
        with patch.object(ExtractionService, "_extract_page_digital", side_effect=RuntimeError("private extraction exception")):
            self.run_worker(job, pipeline)
        self.assertEqual(job.status, "failed")
        self.assertIn("private extraction exception", job.error)
        self.assertEqual(job.phase_message, PROCESSING_FAILURE_MESSAGE)
        response = self.client.get(reverse("translator:status", args=[job.id]))
        self.assertNotIn("private extraction exception", response.content.decode())
        self.assertTrue(Path(job.upload_file_path).exists())

    def test_database_sync_failure_rolls_back_completion_and_output_records(self):
        job = self.new_job("processing")
        checkpoint, output = self.completed_checkpoint(job)
        with patch("translator.services._sync_structure_models", side_effect=OperationalError("sync offline")):
            with self.assertRaises(OperationalError):
                services.sync_pipeline_job(checkpoint)
        job.refresh_from_db()
        self.assertEqual(job.status, "processing")
        self.assertEqual(job.generated_outputs.count(), 0)
        self.assertTrue(output.exists())

    def test_worker_completion_sync_failure_is_uncertain_not_processing_failure(self):
        job = self.stored_job()
        pipeline = self.make_pipeline()
        with patch("translator.services._sync_structure_models", side_effect=OperationalError("sync offline")):
            self.run_worker(job, pipeline)
        self.assertEqual(job.status, "processing")
        self.assertEqual(job.error, "")
        self.assertTrue(Path(pipeline.file_service.get_output_path(job.job_id, "translated.pdf")).exists())
        self.assertTrue(pipeline.jobs[job.job_id].metadata["persistence_uncertain"])

    def test_initial_checkpoint_database_failure_does_not_run_extraction(self):
        job = self.stored_job()
        pipeline = self.make_pipeline()
        with patch.object(pipeline, "_extract_hybrid_pdf") as extract, patch("translator.services.sync_pipeline_job", side_effect=OperationalError("sync offline")):
            self.run_worker(job, pipeline)
        self.assertEqual(job.status, "processing")
        extract.assert_not_called()

    def test_worker_interruption_marks_claimed_job_failed(self):
        job = self.stored_job()
        pipeline = self.make_pipeline()
        with patch.object(pipeline, "process_translation", side_effect=SystemExit("worker stopped")):
            self.run_worker(job, pipeline)
        self.assertEqual(job.status, "failed")
        self.assertIn("worker stopped", job.error)

    def test_duplicate_worker_attempt_does_not_execute_or_change_active_job(self):
        job = self.new_job("processing")
        pipeline = Mock()
        with patch("translator.services.SystemEventLog.objects.create", side_effect=OperationalError("audit unavailable")):
            self.run_worker(job, pipeline)
        pipeline.process_translation.assert_not_called()
        self.assertEqual(job.status, "processing")

    def test_only_one_claim_succeeds(self):
        job = self.new_job()
        self.assertTrue(services._claim_translation_job(job.job_id))
        self.assertFalse(services._claim_translation_job(job.job_id))

    def test_late_checkpoints_cannot_overwrite_terminal_job(self):
        for status in ("completed", "failed"):
            job = self.new_job(status)
            checkpoint = JobStatus(job.job_id)
            checkpoint.status = "processing"
            self.assertFalse(services.sync_pipeline_job(checkpoint))
            job.refresh_from_db()
            self.assertEqual(job.status, status)

    def test_checkpoint_cannot_requeue_an_active_job_or_bypass_claim(self):
        job = self.new_job("processing")
        checkpoint = JobStatus(job.job_id)
        self.assertFalse(services.sync_pipeline_job(checkpoint))
        job.refresh_from_db()
        self.assertEqual(job.status, "processing")
        queued = self.new_job()
        checkpoint = JobStatus(queued.job_id)
        checkpoint.status = "processing"
        self.assertFalse(services.sync_pipeline_job(checkpoint))
        queued.refresh_from_db()
        self.assertEqual(queued.status, "queued")

    def test_completed_job_is_not_changed_by_failure_helper(self):
        job = self.new_job("completed")
        self.assertFalse(services._fail_translation_job(job.job_id, "late failure"))
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")

    def test_failure_write_unavailable_returns_false_and_logs_uncertainty(self):
        job = self.new_job()
        with patch.object(TranslationJob.objects, "filter", side_effect=OperationalError("offline")), self.assertLogs("translator.services", level="ERROR") as logs:
            self.assertFalse(services._fail_translation_job(job.job_id, "processing error"))
        self.assertIn("uncertain", " ".join(logs.output))

    def test_failure_state_survives_secondary_diagnostic_failure(self):
        job = self.new_job("processing")
        checkpoint = JobStatus(job.job_id)
        checkpoint.status = "failed"
        checkpoint.error = "processing error"
        with patch("translator.services._sync_generated_outputs", side_effect=RuntimeError("diagnostic failure")):
            self.assertTrue(services.sync_pipeline_job(checkpoint))
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertIsNotNone(job.completed_at)

    def test_failure_state_persists_when_filesystem_diagnostics_are_unavailable(self):
        job = self.new_job("processing")
        checkpoint = JobStatus(job.job_id)
        checkpoint.status = "failed"
        checkpoint.error = "processing error"
        with patch("translator.services._job_paths", side_effect=OSError("filesystem unavailable")):
            self.assertTrue(services.sync_pipeline_job(checkpoint))
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")

    def test_status_database_outage_is_json_503_without_failed_status(self):
        job = self.new_job()
        with patch("translator.views._get_owned_job", side_effect=OperationalError("private endpoint")):
            response = self.client.get(reverse("translator:status", args=[job.pk]))
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.json()["status_uncertain"])
        self.assertNotIn("status", response.json())
        self.assertNotIn("private endpoint", response.content.decode())

    def test_stale_default_inspect_and_dry_run_are_read_only(self):
        job = self.new_job("processing")
        self.make_stale(job)
        before = TranslationJob.objects.values().get(pk=job.pk)
        logs = SystemEventLog.objects.count()
        for flags in ({}, {"inspect": True}, {"dry_run": True}):
            output = io.StringIO()
            with patch("translator.management.commands.recover_stale_jobs.start_translation_job") as dispatch:
                with CaptureQueriesContext(connection) as queries:
                    call_command("recover_stale_jobs", stdout=output, **flags)
                self.assertTrue(queries.captured_queries)
                self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries.captured_queries))
            self.assertIn(job.job_id, output.getvalue())
            self.assertIn("no records, logs, tasks, or files changed", output.getvalue())
            dispatch.assert_not_called()
            self.assertEqual(TranslationJob.objects.values().get(pk=job.pk), before)
            self.assertEqual(SystemEventLog.objects.count(), logs)
        self.assertFalse((self.root / "jobs").exists())

    def test_stale_inspection_skips_recent_completed_and_deleted_jobs(self):
        stale = self.new_job("queued")
        self.make_stale(stale)
        completed = self.new_job("completed")
        deleted = self.new_job("processing")
        deleted.is_deleted = True
        deleted.save()
        recent = self.new_job()
        output = io.StringIO()
        call_command("recover_stale_jobs", stdout=output)
        self.assertIn(stale.job_id, output.getvalue())
        for job in (completed, deleted, recent):
            self.assertNotIn(job.job_id, output.getvalue())

    def test_explicit_recovery_preserves_jobs_with_uncertain_completed_outputs(self):
        job = self.new_job("processing")
        self.make_stale(job)
        _, output = self.completed_checkpoint(job)
        call_command("recover_stale_jobs", apply=True, stdout=io.StringIO())
        job.refresh_from_db()
        self.assertEqual(job.status, "processing")
        self.assertTrue(output.exists())
        self.assertEqual(SystemEventLog.objects.count(), 0)

    def test_explicit_recovery_guard_does_not_overwrite_racing_completion(self):
        stale = self.new_job("processing")
        self.make_stale(stale)
        TranslationJob.objects.filter(pk=stale.pk).update(status="completed")
        self.assertFalse(Command._mark_failed(stale, 15))
        self.assertEqual(TranslationJob.objects.get(pk=stale.pk).status, "completed")

    def test_explicit_recovery_does_not_retry_uncertain_broker_submission(self):
        job = self.new_job()
        job.metadata = {"dispatch_uncertain": True}
        job.save()
        self.make_stale(job)
        with patch("translator.management.commands.recover_stale_jobs.start_translation_job") as dispatch:
            call_command("recover_stale_jobs", apply=True, retry_queued=True, stdout=io.StringIO())
        job.refresh_from_db()
        self.assertEqual(job.status, "queued")
        dispatch.assert_not_called()

    def test_explicit_recovery_only_changes_reviewed_stale_active_job(self):
        stale = self.new_job("processing")
        self.make_stale(stale)
        completed = self.new_job("completed")
        call_command("recover_stale_jobs", apply=True, stdout=io.StringIO())
        stale.refresh_from_db()
        completed.refresh_from_db()
        self.assertEqual(stale.status, "failed")
        self.assertEqual(completed.status, "completed")

    def test_recovery_retry_requires_separate_explicit_apply(self):
        with self.assertRaises(CommandError):
            call_command("recover_stale_jobs", retry_queued=True, stdout=io.StringIO())

    def test_cooperative_deadline_fails_at_checkpoint_without_processing(self):
        job = self.stored_job()
        pipeline = self.make_pipeline()
        with override_settings(LINGOKATUTUBO_TASK_TIMEOUT_SECONDS=0), patch.object(pipeline, "_extract_hybrid_pdf") as extract:
            self.run_worker(job, pipeline)
        self.assertEqual(job.status, "failed")
        self.assertIn("deadline", job.error)
        extract.assert_not_called()


class TaskRunnerLifecycleTests(SimpleTestCase):
    def test_thread_startup_exception_is_propagated(self):
        with override_settings(LINGOKATUTUBO_TASK_MODE="thread"), patch("translator.services.task_runner.threading.Thread") as thread:
            thread.return_value.start.side_effect = RuntimeError("thread startup failed")
            with self.assertRaises(RuntimeError):
                submit_translation_task(Mock(), "isolated-id")

    def test_invalid_task_mode_is_rejected(self):
        with override_settings(LINGOKATUTUBO_TASK_MODE="typo"):
            with self.assertRaises(ValueError):
                submit_translation_task(Mock(), "isolated-id")

    def test_celery_publish_failure_is_uncertain_without_publish_retry(self):
        from celery.exceptions import OperationalError as BrokerError
        with override_settings(LINGOKATUTUBO_TASK_MODE="celery"), patch("translator.tasks.process_translation_job") as task:
            task.apply_async.side_effect = BrokerError("acknowledgement unavailable")
            with self.assertRaises(JobPersistenceError):
                submit_translation_task(Mock(), "isolated-id")
            task.apply_async.assert_called_once_with(args=("isolated-id",), retry=False)


class ConcurrentClaimTests(TransactionTestCase):
    def test_simultaneous_postgresql_claims_allow_only_one_worker(self):
        owner = get_user_model().objects.create(username="concurrent-claim-user")
        job = TranslationJob.objects.create(owner=owner, original_filename="claim.pdf", file_type="pdf")
        barrier = Barrier(2)

        def claim():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return services._claim_translation_job(job.job_id)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: claim(), range(2)))
        self.assertEqual(sorted(results), [False, True])
        job.refresh_from_db()
        self.assertEqual(job.status, "processing")
