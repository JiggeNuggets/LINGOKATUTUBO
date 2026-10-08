"""Authenticated download of review-required translation segments."""

import csv
from django.http import HttpResponse, JsonResponse
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from .models import TranslationJob
from .services.display_utils import clean_invisible_unicode
from .services.translation_review import public_translation_status
from .services.permissions import can_download_validator_copy


@require_GET
def review_manifest(request, job_id):
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "error": "Please log in again to continue."}, status=401)
    if not can_download_validator_copy(request.user):
        raise PermissionDenied("Review manifests are available to validators only.")
    job = get_object_or_404(
        TranslationJob.objects.filter(is_deleted=False, owner=request.user), id=job_id
    )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="review_manifest_{job.job_id}.csv"'
    writer = csv.DictWriter(
        response,
        fieldnames=[
            "segment_index", "page_number", "source_text", "display_text",
            "translation_status", "confidence", "review_required", "reason",
            "source_language", "target_language", "match_method",
            "validation_status", "runtime_approval_status", "provenance_status",
            "unknown_tokens", "warnings", "segment_identifier",
        ],
    )
    writer.writeheader()
    for segment in job.segments.filter(needs_review=True).select_related("page").order_by("segment_index"):
        status = public_translation_status(
            segment.method, segment.confidence, segment.needs_review,
            (segment.metadata or {}).get("warning", ""),
        )
        metadata = segment.metadata or {}
        writer.writerow({
            "segment_index": segment.segment_index,
            "page_number": segment.page.page_number if segment.page else "",
            "source_text": clean_invisible_unicode(segment.source_text),
            "display_text": clean_invisible_unicode(segment.source_text),
            **status,
            "source_language": segment.source_language,
            "target_language": segment.target_language,
            "match_method": segment.method,
            "validation_status": metadata.get("validation_status", "unverified"),
            "runtime_approval_status": metadata.get("runtime_approval_status", "not_approved"),
            "provenance_status": metadata.get("provenance_status", "unknown"),
            "unknown_tokens": " | ".join(metadata.get("unknown_tokens", []) or []),
            "warnings": " | ".join(metadata.get("warnings", []) or []),
            "segment_identifier": f"p{segment.page.page_number if segment.page else 'x'}-s{segment.segment_index}",
        })
    return response
