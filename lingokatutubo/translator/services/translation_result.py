"""Canonical, transport-safe translation result used by every pipeline stage.

The legacy keys (``translated``, ``method`` and ``needs_review``) are kept in
the dictionary representation so existing clients and stored structures remain
compatible.  Callers must use ``match_method``/``review_required`` to decide
whether a translation can be treated as complete.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TranslationResult:
    source_text: str
    displayed_text: str
    source_language: str
    target_language: str
    match_method: str
    confidence: float | None
    review_required: bool = False
    validation_status: str = "unverified"
    runtime_approval_status: str = "not_approved"
    matched_entry_id: str | None = None
    matched_entry_revision: int | None = None
    unknown_tokens: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provenance_status: str = "unknown"
    restriction_status: str = "unrestricted"
    matched_term: str | None = None
    match_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        normalized_method = {
            "exact_phrase": "exact",
            "normalized_phrase": "normalized",
            "segmented_phrase": "segmented",
            "fuzzy_match": "fuzzy",
            "unknown_for_review": "unknown",
            "identity": "source_retained",
        }.get(self.match_method, self.match_method)
        result["match_method"] = normalized_method
        # Compatibility aliases.  Do not infer success from displayed_text:
        # unknown/source_retained intentionally display the source verbatim.
        result.update({
            "translated": self.displayed_text,
            "method": self.match_method,
            "cascade_stage": self.match_method,
            "needs_review": self.review_required,
        })
        return result


def make_result(*, source_text: str, displayed_text: str, source_language: str,
                target_language: str, match_method: str, confidence: float | None,
                review_required: bool = False, validation_status: str = "unverified",
                runtime_approval_status: str = "not_approved",
                matched_entry_id: str | None = None,
                matched_entry_revision: int | None = None,
                unknown_tokens: list[str] | None = None,
                warnings: list[str] | None = None,
                provenance_status: str = "unknown",
                restriction_status: str = "unrestricted",
                matched_term: str | None = None,
                match_score: float | None = None) -> dict[str, Any]:
    """Build a normalized result with a bounded confidence value."""
    if confidence is not None:
        confidence = round(max(0.0, min(1.0, float(confidence))), 4)
    return TranslationResult(
        source_text=source_text,
        displayed_text=displayed_text,
        source_language=source_language,
        target_language=target_language,
        match_method=match_method,
        confidence=confidence,
        review_required=review_required,
        validation_status=validation_status,
        runtime_approval_status=runtime_approval_status,
        matched_entry_id=matched_entry_id,
        matched_entry_revision=matched_entry_revision,
        unknown_tokens=unknown_tokens or [],
        warnings=warnings or [],
        provenance_status=provenance_status,
        restriction_status=restriction_status,
        matched_term=matched_term,
        match_score=match_score,
    ).to_dict()
