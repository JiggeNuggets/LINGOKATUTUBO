"""Shared lifecycle signals; no database or filesystem side effects."""

PROCESSING_FAILURE_MESSAGE = "Translation could not be completed. Please try another file or contact the administrator."
PERSISTENCE_UNCERTAIN_MESSAGE = "Translation status could not be confirmed. Check this job again before submitting another document."


class JobPersistenceError(RuntimeError):
    """A state write failed; the caller must not infer failure or retry work."""


class JobDeadlineExceeded(RuntimeError):
    """The cooperative processing deadline was reached at a checkpoint."""
