"""Centralized language-resource governance and runtime eligibility rules."""

from __future__ import annotations

from typing import Iterable

from django.utils import timezone

from translator.models import LanguageEntryReview, PhrasebookEntry


GOVERNANCE_POLICY_VERSION = "phase2-draft-1"
RUNTIME_LICENSE_STATUSES = {"permitted", "public_domain", "cc-by", "cc-by-sa"}
RUNTIME_SENSITIVITY_STATUSES = {"approved", "not_sensitive"}


def eligibility_reasons(entry: PhrasebookEntry) -> list[str]:
    reasons: list[str] = []
    if not entry.is_active:
        reasons.append("inactive")
    if entry.validation_status != "verified":
        reasons.append("validation_not_verified")
    if not entry.is_approved_for_runtime:
        reasons.append("runtime_not_approved")
    if entry.license_status not in RUNTIME_LICENSE_STATUSES:
        reasons.append("license_not_eligible")
    if entry.access_restriction != "public":
        reasons.append("access_restricted")
    if entry.cultural_sensitivity_status not in RUNTIME_SENSITIVITY_STATUSES:
        reasons.append("cultural_review_incomplete")
    if entry.has_unresolved_conflict:
        reasons.append("unresolved_conflict")
    if not entry.source_title or not entry.source_owner:
        reasons.append("provenance_incomplete")
    verified_reviews = entry.reviews.filter(decision=LanguageEntryReview.Decision.VERIFY).count()
    if verified_reviews < entry.required_reviews:
        reasons.append("required_reviews_incomplete")
    return reasons


def is_runtime_eligible(entry: PhrasebookEntry) -> bool:
    return not eligibility_reasons(entry)


def runtime_eligible_entries(entries: Iterable[PhrasebookEntry] | None = None) -> list[PhrasebookEntry]:
    queryset = entries if entries is not None else PhrasebookEntry.objects.all()
    return [entry for entry in queryset if is_runtime_eligible(entry)]


def review_entry(*, entry: PhrasebookEntry, reviewer, decision: str, notes: str, related_entry_ids=None) -> LanguageEntryReview:
    """Record a validator decision and preserve previous/new state snapshots."""
    if not reviewer.has_perm("translator.review_language_entry"):
        raise PermissionError("Validator permission is required.")
    previous = entry.governance_snapshot()
    related_entry_ids = related_entry_ids or []
    if decision == LanguageEntryReview.Decision.VERIFY:
        entry.validation_status = "verified"
        entry.needs_review = False
        entry.validator = reviewer
        entry.validation_date = timezone.now().date()
    elif decision == LanguageEntryReview.Decision.REJECT:
        entry.validation_status = "rejected"
        entry.is_approved_for_runtime = False
    elif decision == LanguageEntryReview.Decision.RESTRICT:
        entry.validation_status = "restricted"
        entry.access_restriction = "restricted"
        entry.is_approved_for_runtime = False
    elif decision == LanguageEntryReview.Decision.DUPLICATE:
        entry.validation_status = "deprecated"
        entry.is_active = False
        entry.is_approved_for_runtime = False
    elif decision == LanguageEntryReview.Decision.REQUEST_REVIEW:
        entry.validation_status = "under_review"
        entry.needs_review = True
    entry.save()
    return LanguageEntryReview.objects.create(
        entry=entry,
        reviewer=reviewer,
        decision=decision,
        notes=notes,
        previous_state=previous,
        new_state=entry.governance_snapshot(),
        related_entry_ids=[str(value) for value in related_entry_ids],
    )
