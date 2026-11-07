"""Public, learner-safe translation review status helpers."""

from __future__ import annotations

from typing import Any


REVIEW_LABEL = "Original text retained, translation requires validation."


def public_translation_status(
    method: Any,
    confidence: Any,
    needs_review: bool,
    warning: Any = "",
) -> dict[str, Any]:
    method_value = str(method or "").lower()
    status_map = {
        "exact_phrase": "exact_match",
        "normalized_phrase": "normalized_match",
        "fuzzy_match": "fuzzy_match",
        "segmented_phrase": "segmented_match",
        "byt5_neural": "machine_suggestion",
        "identity": "source_retained",
        "exact": "exact_match", "normalized": "normalized_match",
        "fuzzy": "fuzzy_match", "segmented": "segmented_match",
        "source_retained": "source_retained",
    }
    status = status_map.get(method_value, "unknown")
    review_required = bool(needs_review) or status in {"unknown", "machine_suggestion", "fuzzy_match"}
    if review_required and status not in {"machine_suggestion", "unknown"}:
        status = "validation_required"
    reason = (REVIEW_LABEL if status == "unknown" else
              "Suggested translation requires language-expert validation." if review_required else
              "Translation matched the available language resource.")
    if status == "machine_suggestion":
        reason = "Machine suggestion requires language-expert validation."
    return {
        "translation_status": status,
        "confidence": confidence,
        "review_required": review_required,
        "reason": reason,
    }
