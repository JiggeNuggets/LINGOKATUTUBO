import threading
from typing import Any, Callable

from django.conf import settings
from .job_lifecycle import JobPersistenceError


def submit_translation_task(func: Callable[..., None], *args: Any) -> None:
    """Submit a translation task through the configured runner.

    The default development runner is a daemon thread. Production should set
    `LINGOKATUTUBO_TASK_MODE=celery` after a Celery worker is wired.
    """
    mode = getattr(settings, "LINGOKATUTUBO_TASK_MODE", "thread").lower()

    if mode == "inline":
        func(*args)
        return

    if mode == "celery":
        from translator.tasks import process_translation_job
        from celery.exceptions import OperationalError

        try:
            # Lost broker acknowledgements are ambiguous; do not republish.
            process_translation_job.apply_async(args=args, retry=False)
        except (OperationalError, ConnectionError, TimeoutError) as exc:
            raise JobPersistenceError("Worker dispatch could not be confirmed; do not submit a replacement job.") from exc
        return

    if mode != "thread":
        raise ValueError("Unsupported translation task mode; expected thread, inline, or celery.")

    thread = threading.Thread(
        target=func,
        args=args,
        daemon=True,
        name=f"lingokatutubo-translation-{args[0]}",
    )
    thread.start()
