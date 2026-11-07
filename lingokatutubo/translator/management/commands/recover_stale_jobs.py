from __future__ import annotations

from pathlib import Path
import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from translator.models import SystemEventLog, TranslationJob
from translator.services import start_translation_job

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Inspect stale jobs without writes by default. Recovery requires explicit --apply after operator review."

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes",
            type=int,
            default=15,
            help="Minimum age in minutes since the last job update.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Inspect stale jobs without database, log, task, or file writes.",
        )
        parser.add_argument("--inspect", action="store_true", help="Read-only inspection (the default).")
        parser.add_argument("--apply", action="store_true", help="Explicitly authorize recovery writes for the selected stale jobs.")
        parser.add_argument(
            "--retry-queued",
            action="store_true",
            help="Mark stale queued/retrying jobs as retrying and dispatch them again.",
        )

    def handle(self, *args, **options):
        minutes = max(1, int(options["minutes"]))
        dry_run = bool(options["dry_run"])
        retry_queued = bool(options["retry_queued"])
        apply = bool(options["apply"])
        if apply and (dry_run or options["inspect"]):
            raise CommandError("--apply cannot be combined with --inspect or --dry-run.")
        if retry_queued and not apply:
            raise CommandError("Retry requires explicit --apply after reviewing the inspection output.")
        cutoff = timezone.now() - timezone.timedelta(minutes=minutes)

        stale_jobs = TranslationJob.objects.filter(
            is_deleted=False,
            status__in=[
                TranslationJob.Status.QUEUED,
                TranslationJob.Status.RETRYING,
                TranslationJob.Status.PROCESSING,
            ],
            updated_at__lte=cutoff,
        ).select_related("owner").order_by("updated_at")

        count = 0
        recovered = 0
        for job in stale_jobs:
            count += 1
            uncertain = self._has_output_or_uncertain_status(job)
            action = "inspect-only" if uncertain else self._action_for(job, retry_queued)
            message = (
                f"{action}: job={job.job_id} status={job.status} "
                f"updated_at={job.updated_at.isoformat()}"
            )
            self.stdout.write(message)

            if not apply or uncertain:
                continue

            if action == "retry":
                changed = self._mark_retrying(job, minutes)
                if changed:
                    start_translation_job(job)
            else:
                changed = self._mark_failed(job, minutes)
            if changed:
                recovered += 1
                self._log_recovery_event(job, action, False, minutes)

        if count == 0:
            self.stdout.write("No stale translation jobs found.")
        else:
            if apply:
                self.stdout.write(f"Recovered {recovered} stale job(s); preserved uncertain outputs and changed jobs.")
            else:
                self.stdout.write(f"Inspected {count} stale job(s); no records, logs, tasks, or files changed. Age alone does not prove worker interruption.")

    @staticmethod
    def _has_output_or_uncertain_status(job):
        if any((job.metadata or {}).get(key) for key in ("persistence_uncertain", "dispatch_uncertain")):
            return True
        candidates = [job.output_file_path, job.bilingual_file_path]
        root = Path(settings.MEDIA_ROOT) / "jobs" / job.job_id
        candidates.extend([root / "translated" / "translated.pdf", root / "translated.pdf"])
        return any(path and Path(path).is_file() for path in candidates)

    @staticmethod
    def _action_for(job: TranslationJob, retry_queued: bool) -> str:
        if retry_queued and job.status in {
            TranslationJob.Status.QUEUED,
            TranslationJob.Status.RETRYING,
        }:
            return "retry"
        return "fail"

    @staticmethod
    def _log_recovery_event(
        job: TranslationJob,
        action: str,
        dry_run: bool,
        minutes: int,
    ) -> None:
        try:
            SystemEventLog.objects.create(
                actor=job.owner, job=job, level=SystemEventLog.Level.WARNING,
                event_type="translation_job_stale_recovery",
                message=f"{action} stale translation job after {minutes} minute(s).",
                metadata={"action": action, "dry_run": dry_run, "previous_status": job.status,
                          "minutes": minutes, "updated_at": job.updated_at.isoformat()},
            )
        except Exception:
            logger.exception("Recovery state was updated but its audit event could not be recorded for job %s", job.job_id)

    @staticmethod
    def _mark_retrying(job: TranslationJob, minutes: int) -> bool:
        metadata = dict(job.metadata or {})
        metadata["stale_recovery"] = {
            "action": "retry",
            "minutes": minutes,
            "recovered_at": timezone.now().isoformat(),
            "previous_status": job.status,
        }
        changed = TranslationJob.objects.filter(
            id=job.id, status=job.status, updated_at=job.updated_at, is_deleted=False,
        ).update(
            status=TranslationJob.Status.RETRYING,
            current_phase="retrying",
            current_step="Retrying abandoned translation job",
            phase_message="This job was abandoned and has been queued for retry.",
            error="",
            progress=0,
            metadata=metadata,
            updated_at=timezone.now(),
        )
        if changed:
            job.status = TranslationJob.Status.RETRYING
        return bool(changed)

    @staticmethod
    def _mark_failed(job: TranslationJob, minutes: int) -> bool:
        now = timezone.now()
        metadata = dict(job.metadata or {})
        metadata["stale_recovery"] = {
            "action": "fail",
            "minutes": minutes,
            "recovered_at": now.isoformat(),
            "previous_status": job.status,
        }
        message = (
            "Translation job was abandoned before completion and was marked "
            "failed by stale-job recovery."
        )
        return bool(TranslationJob.objects.filter(
            id=job.id, status=job.status, updated_at=job.updated_at, is_deleted=False,
        ).update(
            status=TranslationJob.Status.FAILED,
            current_phase="failed",
            current_step="Translation failed",
            phase_message=message,
            error=message,
            metadata=metadata,
            updated_at=now,
            completed_at=now,
        ))
