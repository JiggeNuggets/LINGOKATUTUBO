"""Private, short-text translation endpoint for the Django runtime."""

from __future__ import annotations

import json

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse

from .models import UserActivityLog
from .services import quick_translate_text
from .services.translation_review import public_translation_status

def quick_translate(request):
    """Handle an authenticated, CSRF-protected JSON translation request."""
    if not request.user.is_authenticated:
        return JsonResponse(
            {
                "ok": False,
                "error": "Please log in again to continue.",
            },
            status=401,
        )
    if request.method != "POST":
        return JsonResponse(
            {"ok": False, "error": "Use POST with an application/json body."},
            status=405,
        )
    if (request.content_type or "").lower() != "application/json":
        return JsonResponse(
            {"ok": False, "error": "Content-Type must be application/json."},
            status=415,
        )

    max_request_bytes = int(
        getattr(settings, "LINGOKATUTUBO_QUICK_TRANSLATE_MAX_REQUEST_BYTES", 12000)
    )
    try:
        if int(request.META.get("CONTENT_LENGTH") or 0) > max_request_bytes:
            return _too_large()
    except (TypeError, ValueError):
        pass
    try:
        body = request.body
    except Exception:
        return JsonResponse(
            {"ok": False, "error": "Translation request could not be read."},
            status=400,
        )
    if len(body) > max_request_bytes:
        return _too_large()

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse(
            {"ok": False, "error": "Request body must be valid UTF-8 JSON."},
            status=400,
        )
    if not isinstance(payload, dict):
        return JsonResponse(
            {"ok": False, "error": "Request body must be a JSON object."},
            status=400,
        )

    text = payload.get("text", "")
    if not isinstance(text, str) or not text.strip():
        return JsonResponse({"ok": False, "error": "Text is required."}, status=400)
    max_text_length = int(
        getattr(settings, "LINGOKATUTUBO_QUICK_TRANSLATE_MAX_TEXT_LENGTH", 5000)
    )
    if len(text) > max_text_length:
        return JsonResponse(
            {"ok": False, "error": f"Text must be {max_text_length} characters or fewer."},
            status=413,
        )

    source_language = payload.get("source_language", "auto")
    target_language = payload.get("target_language", "tagabawa")
    if not all(
        isinstance(value, str) and len(value) <= 32
        for value in (source_language, target_language)
    ):
        return JsonResponse(
            {"ok": False, "error": "Language labels must be short text values."},
            status=400,
        )
    if not _allow_request(request.user.id):
        return JsonResponse(
            {"ok": False, "error": "Translation limit reached. Please try again later."},
            status=429,
        )

    try:
        result = quick_translate_text(text, source_language, target_language)
        public_status = public_translation_status(
            result.get("method"), result.get("confidence"), result.get("needs_review", False)
        )
        UserActivityLog.objects.create(
            user=request.user,
            action="quick_translate",
            object_type="quick_translation",
            metadata={
                "text_length": len(text),
                "source_language": source_language,
                "target_language": target_language,
            },
        )
        # This endpoint is used by normal authenticated users.  Matching
        # mechanics, scores, dataset/cache state, and resource provenance are
        # deliberately kept out of its public response.
        return JsonResponse({
            "ok": True,
            "original": result.get("original", text),
            "translated": result.get("translated", text),
            "source_language": result.get("source_language", source_language),
            "target_language": result.get("target_language", target_language),
            "review_required": public_status["review_required"],
            "reason": public_status["reason"],
        })
    except Exception:
        return JsonResponse(
            {
                "ok": False,
                "error": "Translation is temporarily unavailable. Please try again later.",
            },
            status=500,
        )


def _allow_request(user_id) -> bool:
    """Rate-limit by authenticated account; no text is retained in the cache."""
    limit = max(1, int(getattr(settings, "LINGOKATUTUBO_QUICK_TRANSLATE_RATE_LIMIT", 30)))
    window = max(
        1,
        int(getattr(settings, "LINGOKATUTUBO_QUICK_TRANSLATE_RATE_WINDOW_SECONDS", 3600)),
    )
    key = f"quick_translation_rate:{user_id}"
    if cache.add(key, 1, timeout=window):
        return True
    try:
        return int(cache.incr(key)) <= limit
    except (ValueError, NotImplementedError):
        return False


def _too_large() -> JsonResponse:
    return JsonResponse(
        {"ok": False, "error": "Translation request is too large."},
        status=413,
    )
