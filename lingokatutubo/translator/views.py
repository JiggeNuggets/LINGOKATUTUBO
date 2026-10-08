import hashlib
import json
import os
import re
import copy
import csv
import io
import uuid
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import Avg, Count, Prefetch, Q
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.csrf import csrf_failure as _django_csrf_failure
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods, require_POST

from .forms import (
    DocumentUploadForm,
    LANGUAGE_CHOICES,
    ResourceMatchTesterForm,
    SignUpForm,
    TranslationResourceForm,
    TranslationResourceImportForm,
)
from .editorial_media import PUBLIC_EDITORIAL_MEDIA
from .editorial_content import get_public_content
from .models import (
    GeneratedOutput,
    OCRResult,
    SystemEventLog,
    TranslationJob,
    TranslationSegment,
    UploadedDocument,
    UserActivityLog,
    CorrectionSuggestion,
    OCRCorrection,
    PhrasebookEntry,
    LanguageResourceImportBatch,
    LanguageResourceIssue,
    UnknownTranslationRecord,
)
from .services import (
    detect_upload_file_type,
    job_directory_path,
    job_structure_path,
    quick_translate_text,
    save_uploaded_file,
    start_translation_job,
    translation_dataset_loaded,
)
from .services.display_utils import clean_invisible_unicode
from .services.translation_display import get_display_translation, get_display_translation_text
from .services.governance import review_entry
from .services.permissions import (
    can_download_teacher_copy,
    can_download_validator_copy,
    can_view_translation_details,
    can_view_validation_markers,
    can_view_system_diagnostics,
    translation_permissions,
)
from .services.resource_management import (
    RESOURCE_FIELDS,
    build_import_preview,
    duplicate_report,
    resource_values,
)
from .services.resource_parity import analyze_resource_inventory, staging_summary
from .services.translation_dataset import TranslationDataset, reset_translation_dataset


PREVIEW_IMAGE_NAME_RE = re.compile(r"^(?:original|translated)_page_\d+\.png$")
LANGUAGE_DISPLAY_LABELS = dict(LANGUAGE_CHOICES)
TRANSLATE_PAGE_RECENT_JOB_LIMIT = 2

# Shown to every user (staff included) in the prominent failure banner and the
# JSON status API. Raw backend exception text (codec errors, tracebacks, file
# paths, model paths) must never reach this surface — it only ever appears
# inside the staff-only technical details panel on the job detail page.
GENERIC_TRANSLATION_FAILURE_MESSAGE = (
    "Translation could not be completed. Please try another file or contact the administrator."
)

# Path prefixes the frontend only ever talks to via fetch() + response.json().
# Auth/CSRF/permission failures on these must stay JSON — a redirect or an
# HTML error page here breaks response.json() with "Unexpected token '<'".
JSON_API_PATH_PREFIXES = (
    "/translate/upload/",
    "/translate/status/",
    "/translate/structure/",
    "/translate/preview-data/",
    "/api/",
)


def csrf_failure(request, reason=""):
    """CSRF failure handler (see CSRF_FAILURE_VIEW in settings.py).

    JSON API routes get a JSON body so fetch() callers can show a clean
    message instead of failing to parse Django's HTML CSRF error page.
    Normal HTML form posts (login, signup, delete fallback) keep Django's
    default CSRF error page unchanged.
    """
    wants_json = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("accept") or "").lower()
    )
    if wants_json or request.path.startswith(JSON_API_PATH_PREFIXES):
        return JsonResponse(
            {
                "ok": False,
                "error": "Your session expired. Please refresh the page and try again.",
            },
            status=403,
        )
    return _django_csrf_failure(request, reason=reason)


def api_login_required(view_func):
    """Like @login_required, but for JSON API endpoints.

    @login_required redirects to the HTML login page; fetch() follows that
    redirect automatically and ends up handing response.json() an HTML
    document, which throws "Unexpected token '<'". API routes need a JSON
    body instead so the frontend can show a clean message.
    """

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Please log in again to continue.",
                    "redirect_url": reverse("translator:login"),
                },
                status=401,
            )
        return view_func(request, *args, **kwargs)

    return wrapped


def home(request):
    return render(request, "translator/home.html", PUBLIC_EDITORIAL_MEDIA["home"])


def bagobo_tagabawa(request):
    content = get_public_content("bagobo_tagabawa")
    return render(
        request,
        "translator/editorial_page.html",
        {
            **PUBLIC_EDITORIAL_MEDIA["bagobo_tagabawa"],
            "page_key": "bagobo_tagabawa",
            "eyebrow": content["hero"]["eyebrow"],
            "title": content["hero"]["title"],
            "intro": content["hero"]["description"],
            "action_label": content["hero"].get("action_label", "Explore"),
            "story_navigation": content.get("story_navigation", []),
            "sections": content["sections"],
            "sources": content.get("sources", []),
            "continue_exploring": content.get("continue_exploring", []),
        },
    )


def culture(request):
    content = get_public_content("culture")
    return render(
        request,
        "translator/editorial_page.html",
        {
            **PUBLIC_EDITORIAL_MEDIA["culture"],
            "page_key": "culture",
            "eyebrow": content["hero"]["eyebrow"],
            "title": content["hero"]["title"],
            "intro": content["hero"]["description"],
            "action_label": content["hero"].get("action_label", "Explore"),
            "story_navigation": content.get("story_navigation", []),
            "sections": content["sections"],
            "sources": content.get("sources", []),
            "continue_exploring": content.get("continue_exploring", []),
        },
    )


def nature(request):
    content = get_public_content("nature")
    return render(
        request,
        "translator/editorial_page.html",
        {
            **PUBLIC_EDITORIAL_MEDIA["nature"],
            "page_key": "nature",
            "eyebrow": content["hero"]["eyebrow"],
            "title": content["hero"]["title"],
            "intro": content["hero"]["description"],
            "action_label": content["hero"].get("action_label", "Explore"),
            "story_navigation": content.get("story_navigation", []),
            "sections": content["sections"],
            "video_feature": content.get("video_feature"),
            "sources": content.get("sources", []),
            "continue_exploring": content.get("continue_exploring", []),
        },
    )


def community(request):
    content = get_public_content("community")
    return render(
        request,
        "translator/editorial_page.html",
        {
            **PUBLIC_EDITORIAL_MEDIA["community"],
            "page_key": "community",
            "eyebrow": content["hero"]["eyebrow"],
            "title": content["hero"]["title"],
            "intro": content["hero"]["description"],
            "action_label": content["hero"].get("action_label", "Explore"),
            "story_navigation": content.get("story_navigation", []),
            "sections": content["sections"],
            "sources": content.get("sources", []),
            "continue_exploring": content.get("continue_exploring", []),
        },
    )


@login_required
def dashboard(request):
    """Decision-oriented, owner-scoped dashboard for the active role."""
    from datetime import timedelta
    from django.utils import timezone

    user = request.user
    permissions = translation_permissions(user)
    is_validator = permissions["is_validator"]
    is_admin = permissions["is_administrator"]
    is_teacher = permissions["is_teacher"]

    owned_jobs = _owned_jobs_queryset(request)
    total_jobs_count = owned_jobs.count()
    completed_jobs_count = owned_jobs.filter(status=TranslationJob.Status.COMPLETED).count()
    processing_jobs_count = owned_jobs.filter(status__in=[
        TranslationJob.Status.QUEUED,
        TranslationJob.Status.RETRYING,
        TranslationJob.Status.PROCESSING,
    ]).count()

    recent_jobs_qs = owned_jobs.order_by("-created_at")[:12]
    all_recent_states = [_job_card_context(job, user) for job in recent_jobs_qs]

    now = timezone.now()
    today_date = now.date()
    yesterday_date = today_date - timedelta(days=1)
    week_ago_date = today_date - timedelta(days=7)

    today_group = {"label": "Today", "jobs": []}
    yesterday_group = {"label": "Yesterday", "jobs": []}
    this_week_group = {"label": "Earlier this Week", "jobs": []}
    older_group = {"label": "Older", "jobs": []}

    for state in all_recent_states:
        title_lower = (state.get("document_title") or "").lower()
        if title_lower.endswith(".pdf"):
            state["format"] = "pdf"
        elif title_lower.endswith(".docx"):
            state["format"] = "docx"
        else:
            state["format"] = "doc"

        uploaded_at = state.get("uploaded_at")
        job_date = uploaded_at.date() if hasattr(uploaded_at, "date") else None

        if job_date == today_date:
            today_group["jobs"].append(state)
        elif job_date == yesterday_date:
            yesterday_group["jobs"].append(state)
        elif job_date and job_date >= week_ago_date:
            this_week_group["jobs"].append(state)
        else:
            older_group["jobs"].append(state)

    date_groups = [g for g in [today_group, yesterday_group, this_week_group, older_group] if g["jobs"]]

    context = {
        "recent_jobs": all_recent_states[:5],
        "all_recent_jobs": all_recent_states,
        "date_groups": date_groups,
        "total_jobs_count": total_jobs_count,
        "completed_jobs_count": completed_jobs_count,
        "processing_jobs_count": processing_jobs_count,
        "is_validator": is_validator,
        "is_administrator": is_admin,
        "is_teacher": is_teacher,
        "review_required_jobs": owned_jobs.filter(segments__needs_review=True).distinct().count(),
        "correction_count": CorrectionSuggestion.objects.filter(submitted_by=user).count(),
        **permissions,
    }
    if is_validator:
        context["validator_counts"] = {
            "pending_entries": PhrasebookEntry.objects.filter(validation_status__in=["pending", "under_review"]).count(),
            "unknown_terms": UnknownTranslationRecord.objects.filter(review_status="pending").count(),
            "conflicts": PhrasebookEntry.objects.filter(has_unresolved_conflict=True).count(),
            "missing_provenance": PhrasebookEntry.objects.filter(Q(source_title="") | Q(source_owner="")).count(),
        }
    return render(request, "translator/dashboard.html", context)


@permission_required("translator.manage_language_resources", raise_exception=True)
def translation_resources(request):
    """Admin resource catalogue; it deliberately excludes governance controls."""
    entries = PhrasebookEntry.objects.all().order_by("-updated_at", "-id")
    query = request.GET.get("q", "").strip()
    active = request.GET.get("active", "active")
    category = request.GET.get("category", "").strip()
    completeness = request.GET.get("completeness", "")
    warning = request.GET.get("warning", "")
    if query:
        entries = entries.filter(
            Q(tagabawa__icontains=query) | Q(english__icontains=query)
            | Q(filipino__icontains=query) | Q(cebuano__icontains=query)
            | Q(topic__icontains=query) | Q(part_of_speech__icontains=query)
        )
    if active == "active":
        entries = entries.filter(is_active=True)
    elif active == "inactive":
        entries = entries.filter(is_active=False)
    if category:
        entries = entries.filter(topic=category)
    language_fields = ["tagabawa", "english", "filipino", "cebuano"]
    if completeness == "complete":
        for field in language_fields:
            entries = entries.exclude(**{field: ""})
    elif completeness == "incomplete":
        entries = entries.filter(Q(tagabawa="") | Q(english="") | Q(filipino="") | Q(cebuano=""))
    if warning == "conflict":
        entries = entries.filter(has_unresolved_conflict=True)
    elif warning == "duplicate":
        entries = entries.filter(
            governance_issues__is_resolved=False,
            governance_issues__category__in=[
                LanguageResourceIssue.Category.EXACT_DUPLICATE,
                LanguageResourceIssue.Category.NORMALIZED_DUPLICATE,
                LanguageResourceIssue.Category.POSSIBLE_DUPLICATE,
            ],
        ).distinct()
    paginator = Paginator(entries, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    categories = (
        PhrasebookEntry.objects.exclude(topic="").values_list("topic", flat=True).distinct().order_by("topic")
    )
    return render(request, "translator/translation_resources/list.html", {
        "page_obj": page_obj, "categories": categories,
        "filters": {"q": query, "active": active, "category": category,
                    "completeness": completeness, "warning": warning},
    })


def _resource_form_response(request, entry=None):
    form = TranslationResourceForm(request.POST or None, instance=entry)
    if request.method == "POST" and form.is_valid():
        report = duplicate_report(
            form.cleaned_data,
            PhrasebookEntry.objects.all(),
            exclude_id=entry.pk if entry else None,
        )
        if report["exact"]:
            form.add_error(None, "An exact duplicate resource already exists. No changes were saved.")
        else:
            saved = form.save(commit=False)
            # Conflict warning is preserved for validator workflows; nothing is
            # overwritten and routine edits never approve an entry.
            if report["conflicts"]:
                saved.has_unresolved_conflict = True
                messages.warning(request, "Saved with a conflict warning for validator review.")
            if report["normalized"]:
                messages.warning(request, "Saved with a normalized-duplicate warning; review the similar entry.")
            saved.save()  # PhrasebookEntry.save records an ordinary revision.
            reset_translation_dataset()
            messages.success(request, "Translation resource saved.")
            return redirect("translator:translation_resources")
    return render(request, "translator/translation_resources/form.html", {
        "form": form, "entry": entry,
    })


@permission_required("translator.manage_language_resources", raise_exception=True)
@require_http_methods(["GET", "POST"])
def translation_resource_add(request):
    return _resource_form_response(request)


@permission_required("translator.manage_language_resources", raise_exception=True)
@require_http_methods(["GET", "POST"])
def translation_resource_edit(request, entry_id):
    return _resource_form_response(request, get_object_or_404(PhrasebookEntry, pk=entry_id))


@permission_required("translator.manage_language_resources", raise_exception=True)
@require_POST
def translation_resource_toggle(request, entry_id):
    entry = get_object_or_404(PhrasebookEntry, pk=entry_id)
    entry.is_active = not entry.is_active
    entry.save()
    reset_translation_dataset()
    messages.success(request, "Resource reactivated." if entry.is_active else "Resource deactivated.")
    return redirect("translator:translation_resources")


@permission_required("translator.manage_language_resources", raise_exception=True)
@require_http_methods(["GET", "POST"])
def translation_resources_import(request):
    form = TranslationResourceImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        uploaded = form.cleaned_data["file"]
        try:
            preview = build_import_preview(uploaded.name, uploaded.read(), PhrasebookEntry.objects.all())
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError, csv.Error) as exc:
            form.add_error("file", f"Could not read resource file: {exc}")
        else:
            request.session["translation_resource_import_preview"] = preview
            request.session.modified = True
            return render(request, "translator/translation_resources/import.html", {"form": form, "preview": preview})
    return render(request, "translator/translation_resources/import.html", {"form": form})


@permission_required("translator.manage_language_resources", raise_exception=True)
@require_POST
def translation_resources_import_confirm(request):
    preview = request.session.get("translation_resource_import_preview")
    if not preview:
        messages.error(request, "No import preview is awaiting confirmation.")
        return redirect("translator:translation_resources_import")
    created = 0
    issue_categories = {
        "duplicate": LanguageResourceIssue.Category.EXACT_DUPLICATE,
        "normalized_duplicate": LanguageResourceIssue.Category.NORMALIZED_DUPLICATE,
        "conflict": LanguageResourceIssue.Category.CONFLICTING_TRANSLATION,
        "invalid": LanguageResourceIssue.Category.INCOMPLETE_RECORD,
    }
    with transaction.atomic():
        batch = LanguageResourceImportBatch.objects.create(
            identifier=f"translation-resources-{uuid.uuid4().hex[:12]}",
            source_filename=preview["source_name"], source_checksum_sha256=preview["checksum"],
            imported_by=request.user, rows_processed=preview["summary"]["processed"],
            rows_duplicated=preview["summary"]["duplicates"], rows_conflicting=preview["summary"]["conflicts"],
            rows_incomplete=preview["summary"]["invalid"],
            rows_skipped=preview["summary"]["duplicates"] + preview["summary"]["conflicts"] + preview["summary"]["invalid"],
            rows_requiring_review=preview["summary"]["conflicts"] + preview["summary"]["invalid"],
            is_dry_run=False,
            notes="Confirmed from Translation Resources dry-run preview; existing records were not overwritten.",
        )
        for item in preview["rows"]:
            if item["status"] == "ready":
                # Recheck before the write so a concurrent resource save cannot
                # make this confirmation overwrite or duplicate an entry.
                if duplicate_report(item["values"], PhrasebookEntry.objects.all())["exact"]:
                    item["status"] = "duplicate"
                else:
                    PhrasebookEntry.objects.create(import_batch=batch, **item["values"])
                    created += 1
                    continue
            LanguageResourceIssue.objects.create(
                batch=batch, category=issue_categories[item["status"]],
                source_row_number=item["row_number"], detail={"reason": item["reason"]},
            )
        batch.rows_created = created
        batch.save(update_fields=["rows_created", "updated_at"])
    request.session.pop("translation_resource_import_preview", None)
    if created:
        reset_translation_dataset()
    messages.success(request, f"Import confirmed: {created} resources created; existing records were not changed.")
    return redirect("translator:translation_resources")


@permission_required("translator.manage_language_resources", raise_exception=True)
def translation_resources_export(request):
    scope = request.GET.get("scope", "active")
    output_format = request.GET.get("format", "csv").lower()
    entries = PhrasebookEntry.objects.all().order_by("id")
    if scope != "all":
        entries = entries.filter(is_active=True)
        scope = "active"
    rows = [resource_values(entry) for entry in entries]
    if output_format == "json":
        response = HttpResponse(json.dumps(rows, ensure_ascii=False, indent=2), content_type="application/json")
        response["Content-Disposition"] = f'attachment; filename="translation-resources-{scope}.json"'
        return response
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=RESOURCE_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="translation-resources-{scope}.csv"'
    return response


@permission_required("translator.manage_language_resources", raise_exception=True)
@require_http_methods(["GET", "POST"])
def translation_resources_match_tester(request):
    form = ResourceMatchTesterForm(request.POST or None)
    result = candidates = None
    if request.method == "POST" and form.is_valid():
        # Match Tester always demonstrates the explicitly selected active DB
        # resource source, independent of the document runtime mode.
        dataset = TranslationDataset(data_mode="development_resources")
        result = dataset.translate_phrase_with_metadata(
            form.cleaned_data["text"], form.cleaned_data["source_language"], form.cleaned_data["target_language"],
        )
        candidates = dataset.candidate_matches(
            form.cleaned_data["text"], form.cleaned_data["source_language"], form.cleaned_data["target_language"],
        )
    return render(request, "translator/translation_resources/match_tester.html", {
        "form": form, "result": result, "candidates": candidates,
    })


def _staging_key(item):
    return json.dumps(item["normalized_key"], ensure_ascii=False, separators=(",", ":"))


@permission_required("translator.manage_language_resources", raise_exception=True)
def legacy_resource_staging(request):
    """Read-only legacy corpus review surface; decisions remain session-local."""
    report = analyze_resource_inventory()
    records = report["legacy_only"]
    query = request.GET.get("q", "").strip().lower()
    selected_status = request.GET.get("status", "")
    decisions = request.session.get("legacy_resource_staging_decisions", {})
    for record in records:
        record["staging_key"] = _staging_key(record)
        record["decision"] = decisions.get(record["staging_key"], "")
    if query:
        records = [
            record for record in records
            if query in " ".join(str(record["values"].get(language, "")) for language in ("tagabawa", "english", "filipino", "cebuano")).lower()
        ]
    if selected_status:
        records = [record for record in records if record["staging_status"] == selected_status]
    records.sort(key=lambda record: (record["staging_status"], record["values"].get("english", "")))
    page_obj = Paginator(records, 25).get_page(request.GET.get("page"))
    selected_imports = sum(value == "IMPORT_SELECTED" for value in decisions.values())
    return render(request, "translator/translation_resources/legacy_staging.html", {
        "page_obj": page_obj, "summary": staging_summary(report), "query": query,
        "selected_status": selected_status, "selected_imports": selected_imports,
        "expected_count": PhrasebookEntry.objects.count() + selected_imports,
        "status_choices": ["READY_FOR_ADMIN_REVIEW", "INCOMPLETE", "POSSIBLE_DUPLICATE", "CONFLICT", "POSSIBLE_OCR_ARTIFACT", "MANUAL_LANGUAGE_REVIEW"],
    })


@permission_required("translator.manage_language_resources", raise_exception=True)
@require_POST
def legacy_resource_staging_action(request):
    action = request.POST.get("action", "")
    staging_key = request.POST.get("staging_key", "")
    action_map = {
        "import": "IMPORT_SELECTED", "ignore": "IGNORED", "keep": "KEEP_LEGACY_ONLY", "review": "NEEDS_REVIEW",
    }
    if action not in action_map:
        raise Http404("Unknown staging action")
    records = { _staging_key(record): record for record in analyze_resource_inventory()["legacy_only"] }
    record = records.get(staging_key)
    if record is None:
        raise Http404("Legacy resource not found")
    if action == "import" and record["staging_status"] != "READY_FOR_ADMIN_REVIEW":
        messages.error(request, "Only structurally ready records can be selected for import.")
    else:
        decisions = request.session.get("legacy_resource_staging_decisions", {})
        decisions[staging_key] = action_map[action]
        request.session["legacy_resource_staging_decisions"] = decisions
        request.session.modified = True
        messages.success(request, "Staging decision recorded. No language resource was changed.")
    return redirect("translator:legacy_resource_staging")


@permission_required("translator.manage_language_resources", raise_exception=True)
@require_POST
def legacy_resource_staging_import_confirm(request):
    """Explicit confirmation endpoint. It is never reached by viewing/staging."""
    decisions = request.session.get("legacy_resource_staging_decisions", {})
    records = [
        record for record in analyze_resource_inventory()["legacy_only"]
        if decisions.get(_staging_key(record)) == "IMPORT_SELECTED"
        and record["staging_status"] == "READY_FOR_ADMIN_REVIEW"
    ]
    if not records:
        messages.error(request, "No ready staging records are selected for import.")
        return redirect("translator:legacy_resource_staging")
    created = 0
    with transaction.atomic():
        batch = LanguageResourceImportBatch.objects.create(
            identifier=f"legacy-corpus-staging-{uuid.uuid4().hex[:12]}",
            source_filename="cross_lingual_cleaned_v1.csv",
            source_checksum_sha256=hashlib.sha256(
                (Path(settings.BASE_DIR) / "datasets" / "cleaned" / "cross_lingual_cleaned_v1.csv").read_bytes()
            ).hexdigest(),
            imported_by=request.user, rows_processed=len(records), is_dry_run=False,
            notes="Explicitly confirmed Legacy Resource Staging import. Existing records were not overwritten.",
        )
        for record in records:
            values = record["values"]
            candidate = {
                "tagabawa": values["tagabawa"], "english": values["english"],
                "filipino": values["filipino"], "cebuano": values["cebuano"],
                "topic": "Legacy corpus staging", "source": "legacy_corpus_csv",
                "notes": f"Legacy corpus row(s): {', '.join(map(str, record['original_row_identifiers']))}",
                "is_active": record["completeness"] >= 2,
            }
            if duplicate_report(candidate, PhrasebookEntry.objects.all())["exact"]:
                batch.rows_skipped += 1
                batch.rows_duplicated += 1
                continue
            PhrasebookEntry.objects.create(import_batch=batch, **candidate)
            created += 1
        batch.rows_created = created
        batch.save(update_fields=["rows_created", "rows_skipped", "rows_duplicated", "updated_at"])
    if created:
        reset_translation_dataset()
    for record in records:
        decisions.pop(_staging_key(record), None)
    request.session["legacy_resource_staging_decisions"] = decisions
    messages.success(request, f"Confirmed non-destructive import: {created} resources created.")
    return redirect("translator:legacy_resource_staging")


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("translator:translate")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


class TranslatorLoginView(auth_views.LoginView):
    """Login view that tailors its heading when sent here to reach Translate.

    `@login_required` on `translate()` redirects here with `next=/translate/`;
    the template swaps its heading/subtext for that case instead of using a
    flash message, since the destination is already implied by `next`.
    """

    template_name = "registration/login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next_is_translate"] = self.get_redirect_url() == reverse("translator:translate")
        return context


@login_required
def translate(request):
    recent_query = (
        _owned_jobs_queryset(request)
        .select_related("uploaded_document")
        .annotate(
            segment_count=Count("segments", distinct=True),
            review_segment_count=Count(
                "segments",
                filter=Q(segments__needs_review=True),
                distinct=True,
            ),
            translation_confidence=Avg("segments__confidence"),
            ocr_confidence=Avg("ocr_results__confidence"),
            page_count=Count("pages", distinct=True),
        )
        .prefetch_related("generated_outputs", "pages", "ocr_results")
        # The heavy GROUP BY from the annotations can drop the model's
        # default ordering (same fix as the history view), and the sidebar
        # must always show the newest documents first.
        .order_by("-created_at")
    )

    # Fetch a few extra cards so the Active Job panel can still find a
    # queued/processing job that is older than the two newest documents,
    # while the compact Translate workspace never exposes more than two.
    recent_cards = [_job_card_context(job, request.user) for job in recent_query[:5]]
    recent_jobs = recent_cards[:TRANSLATE_PAGE_RECENT_JOB_LIMIT]

    active_job = next(
        (
            card
            for card in recent_cards
            if card["job"].status
            in {
                TranslationJob.Status.QUEUED,
                TranslationJob.Status.RETRYING,
                TranslationJob.Status.PROCESSING,
            }
        ),
        None,
    )

    active_state = active_job or {
        "job": None,
        "can_preview": False,
        "can_download": False,
        "is_processing": False,
        "has_failed": False,
        "can_retry": False,
    }

    return render(
        request,
        "translator/translate.html",
        {
            "upload_form": DocumentUploadForm(),
            "recent_jobs": recent_jobs,
            "active_job": active_job,
            "can_preview": active_state["can_preview"],
            "can_download": active_state["can_download"],
            "is_processing": active_state["is_processing"],
            "has_failed": active_state["has_failed"],
        },
    )


@login_required
@ensure_csrf_cookie
def history(request):
    # ensure_csrf_cookie: the Remove modal on this page POSTs via fetch()
    # using the csrftoken cookie; the page itself has no POST form that
    # would otherwise guarantee the cookie exists.
    search_query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip().lower()
    selected_sort = request.GET.get("sort", "newest").strip().lower()
    selected_date_range = request.GET.get("date_range", "all").strip().lower()

    jobs = (
        _owned_jobs_queryset(request)
        .select_related("uploaded_document")
        .annotate(
            segment_count=Count("segments", distinct=True),
            review_segment_count=Count(
                "segments",
                filter=Q(segments__needs_review=True),
                distinct=True,
            ),
            translation_confidence=Avg("segments__confidence"),
            ocr_confidence=Avg("ocr_results__confidence"),
            page_count=Count("pages", distinct=True),
            output_count=Count("generated_outputs", distinct=True),
        )
        .prefetch_related("generated_outputs", "pages", "ocr_results")
    )

    if search_query:
        jobs = jobs.filter(
            Q(original_filename__icontains=search_query)
            | Q(uploaded_document__original_filename__icontains=search_query)
        )

    valid_statuses = {value for value, _label in TranslationJob.Status.choices}

    if selected_status in valid_statuses:
        jobs = jobs.filter(status=selected_status)

    now = timezone.now()
    if selected_date_range == "today":
        jobs = jobs.filter(created_at__date=timezone.localdate())
    elif selected_date_range == "week":
        jobs = jobs.filter(created_at__gte=now - timezone.timedelta(days=7))
    elif selected_date_range == "month":
        jobs = jobs.filter(created_at__gte=now - timezone.timedelta(days=30))

    valid_sorts = {"newest", "oldest", "name_asc", "name_desc"}
    if selected_sort not in valid_sorts:
        selected_sort = "newest"

    if selected_sort == "oldest":
        jobs = jobs.order_by("created_at")
    elif selected_sort == "name_asc":
        jobs = jobs.order_by("original_filename", "-created_at")
    elif selected_sort == "name_desc":
        jobs = jobs.order_by("-original_filename", "-created_at")
    else:
        jobs = jobs.order_by("-created_at")

    return render(
        request,
        "translator/history.html",
        {
            "jobs": [_job_card_context(job, request.user) for job in jobs],
            "filters": TranslationJob.Status.choices,
            "search_query": search_query,
            "selected_status": selected_status if selected_status in valid_statuses else "",
            "selected_sort": selected_sort,
            "selected_date_range": selected_date_range,
        },
    )


@login_required
def job_detail(request, job_id):
    job = (
        _owned_jobs_queryset(request)
        .select_related("uploaded_document")
        .annotate(
            segment_count=Count("segments", distinct=True),
            review_segment_count=Count(
                "segments",
                filter=Q(segments__needs_review=True),
                distinct=True,
            ),
            translation_confidence=Avg("segments__confidence"),
            ocr_confidence=Avg("ocr_results__confidence"),
            page_count=Count("pages", distinct=True),
        )
        .prefetch_related("generated_outputs", "pages", "ocr_results")
        .filter(id=job_id)
        .first()
    )

    if not job:
        raise Http404("Job not found")

    context = _job_card_context(job, request.user)
    # Suppress the global active-job banner when we're already viewing this job's detail page
    context["hide_active_job_banner"] = context["is_processing"]

    if job.status == TranslationJob.Status.COMPLETED:
        # Show the "ready" message once per job per session — not on every
        # reload of an already-acknowledged completed job.
        notified_key = f"job_ready_notified_{job.id}"
        if not request.session.get(notified_key):
            messages.success(request, "Translated file is ready.")
            request.session[notified_key] = True

    return render(request, "translator/job_detail.html", context)


PREVIEW_SEGMENTS_PER_PAGE = 25


@login_required
def preview(request, job_id):
    job = (
        _owned_jobs_queryset(request)
        .prefetch_related(
            "ocr_results",
            "generated_outputs",
            "pages",
        )
        .select_related("uploaded_document")
        .annotate(
            segment_count=Count("segments", distinct=True),
            review_segment_count=Count(
                "segments",
                filter=Q(segments__needs_review=True),
                distinct=True,
            ),
            translation_confidence=Avg("segments__confidence"),
            ocr_confidence=Avg("ocr_results__confidence"),
            page_count=Count("pages", distinct=True),
        )
        .filter(id=job_id)
        .first()
    )

    if not job:
        raise Http404("Job not found")

    state = _job_card_context(job, request.user)

    if not state["can_preview"]:
        if state["has_failed"]:
            messages.error(request, state["failure_message"])
        elif state["is_processing"]:
            messages.info(
                request,
                "The bilingual preview will be available after processing is complete.",
            )
        else:
            messages.info(request, "The bilingual preview is not available yet.")

        return redirect("translator:job_detail", job_id=job.id)

    segments_qs = (
        TranslationSegment.objects.filter(job=job)
        .select_related("page")
        .order_by("segment_index")
    )
    if not can_view_translation_details(request.user):
        segments_qs = segments_qs.defer(
            "method", "confidence", "metadata", "source_language", "target_language"
        )
    paginator = Paginator(segments_qs, PREVIEW_SEGMENTS_PER_PAGE)
    try:
        page_number = int(request.GET.get("page", 1))
    except (ValueError, TypeError):
        page_number = 1
    segments_page = paginator.get_page(page_number)
    for segment in segments_page.object_list:
        segment.display_source_text = clean_invisible_unicode(segment.source_text)
        segment.display_translated_text = get_display_translation(segment)
        segment.review_identifier = f"P{segment.page.page_number if segment.page else '?'}-S{segment.segment_index}"

    review_copy = request.GET.get("review") == "1" and can_download_validator_copy(request.user)

    return render(
        request,
        "translator/preview.html",
        {
            **state,
            "uploaded_document": getattr(job, "uploaded_document", None),
            "document_pages": list(job.pages.all()),
            "ocr_result": job.ocr_results.first(),
            "segments": segments_page,
            "total_segments": paginator.count,
            "generated_outputs": list(job.generated_outputs.all()),
            "ocr_summary": _ocr_summary(job),
            "image_preview": _image_preview_context(job),
            "review_copy": review_copy,
            "translation_data_mode": (
                getattr(settings, "TRANSLATION_DATA_MODE", "development_unverified")
                if can_view_translation_details(request.user) else ""
            ),
            "thumbnail_url": state.get("thumbnail_url", ""),
            "status_label": state.get("status_label", _status_label(job.status)),
            "status_class": state.get("status_class", _status_class(job.status)),
        },
    )


@api_login_required
@require_POST
def api_translate(request):
    # 1. Active jobs limit check (Maximum 2 queued/processing jobs per user)
    active_jobs = TranslationJob.objects.filter(
        owner=request.user,
        status__in=[
            TranslationJob.Status.QUEUED,
            TranslationJob.Status.RETRYING,
            TranslationJob.Status.PROCESSING,
        ],
        is_deleted=False
    ).count()
    if active_jobs >= 2:
        return JsonResponse(
            {"detail": "You have reached the upload limit. Please wait before submitting another document."},
            status=400
        )

    # 2. Hourly upload attempts check (Maximum 5 attempts per hour)
    from django.core.cache import cache
    cache_key = f"upload_attempts_hourly_{request.user.id}"
    attempts = cache.get(cache_key, 0)
    if attempts >= 5:
        return JsonResponse(
            {"detail": "You have reached the upload limit. Please wait before submitting another document."},
            status=400
        )
    # Increment counter
    cache.set(cache_key, attempts + 1, timeout=3600)

    form = DocumentUploadForm(request.POST, request.FILES)

    if not form.is_valid():
        return JsonResponse({"detail": form.errors.get_json_data()}, status=400)

    uploaded = form.cleaned_data["file"]
    file_type = detect_upload_file_type(uploaded.name)

    if not file_type or file_type not in ("pdf", "docx"):
        return JsonResponse({"detail": "Please upload a PDF or DOCX document."}, status=400)

    job = None
    try:
        job = TranslationJob.objects.create(
            owner=request.user,
            original_filename=uploaded.name,
            file_type=file_type,
            source_language=form.cleaned_data["source_language"],
            target_language=form.cleaned_data["target_language"],
            ocr_languages=form.cleaned_data.get("ocr_languages", ""),
            phase_message="Document is waiting to be processed.",
        )

        stored_paths = save_uploaded_file(uploaded, job.job_id)

        job.input_file_path = stored_paths["input_file_path"]
        job.upload_file_path = stored_paths["upload_file_path"]
        job.save(update_fields=["input_file_path", "upload_file_path", "updated_at"])

        UploadedDocument.objects.create(
            owner=request.user,
            job=job,
            original_filename=uploaded.name,
            file_type=file_type,
            file_path=stored_paths["upload_file_path"],
            file_size_bytes=uploaded.size,
            checksum_sha256=_sha256_file(stored_paths["upload_file_path"]),
            metadata={
                "content_type": getattr(uploaded, "content_type", ""),
                "source_language": job.source_language,
                "target_language": job.target_language,
            },
        )

        job.metadata = {
            **(job.metadata or {}),
            "original_content_type": getattr(uploaded, "content_type", ""),
            "original_file_size_bytes": uploaded.size,
        }
        job.save(update_fields=["metadata", "updated_at"])

        UserActivityLog.objects.create(
            user=request.user,
            action="upload_document",
            object_type="TranslationJob",
            object_id=job.job_id,
            metadata={"filename": uploaded.name, "file_type": file_type},
        )

        SystemEventLog.objects.create(
            actor=request.user,
            job=job,
            event_type="translation_job_created",
            message="Translation job created from document upload.",
            metadata={"filename": uploaded.name, "file_type": file_type},
        )

        start_translation_job(job)

        payload = _job_payload(job, request.user)
        payload["message"] = "Translation started"

        return JsonResponse(payload, status=202)
    except Exception as exc:
        SystemEventLog.objects.create(
            actor=request.user,
            job=job,
            level=SystemEventLog.Level.ERROR,
            event_type="upload_request_failed",
            message=f"Upload request failed: {exc}",
            metadata={"filename": uploaded.name},
        )
        error_payload = {"ok": False, "error": GENERIC_TRANSLATION_FAILURE_MESSAGE}
        if request.user.is_staff:
            error_payload["technical_detail"] = str(exc)
        return JsonResponse(error_payload, status=500)


@api_login_required
def api_job_status(request, job_id):
    try:
        job = _get_owned_job(request, job_id)
    except Http404:
        return JsonResponse({"ok": False, "error": "Job not found."}, status=404)
    return JsonResponse(_job_payload(job, request.user))


@api_login_required
def api_structure(request, job_id):
    try:
        job = _get_owned_job(request, job_id)
    except Http404:
        return JsonResponse({"ok": False, "error": "Job not found."}, status=404)
    if not can_view_translation_details(request.user):
        return JsonResponse({"ok": False, "error": "This review information is not available for your role."}, status=403)

    structure_path = _resolve_job_file(
        job,
        job.structure_file_path or _default_structure_path(job),
    )

    if not structure_path or not structure_path.exists():
        return JsonResponse(
            {
                "error": "Structure not yet available",
                "detail": f"Job status is {job.status}.",
            },
            status=404,
        )

    try:
        with open(structure_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        return JsonResponse(
            {"error": "Failed to read structure.json", "detail": str(exc)},
            status=500,
        )

    data["status"] = job.status
    data = _display_safe_structure(data)

    return JsonResponse(data)


@api_login_required
def api_preview(request, job_id):
    try:
        job = _get_owned_job(request, job_id)
    except Http404:
        return JsonResponse({"ok": False, "error": "Job not found."}, status=404)

    if job.status != TranslationJob.Status.COMPLETED:
        return JsonResponse(
            {"error": f"Job status is {job.status}, not completed"},
            status=400,
        )

    metadata = job.metadata or {}
    include_details = can_view_translation_details(request.user)
    translation_quality = _translation_quality_context(job) if include_details else {}

    original_pages = [
        _preview_image_url(job, item)
        for item in metadata.get("preview_original", [])
        if _preview_image_url(job, item)
    ]

    translated_pages = [
        _preview_image_url(job, item)
        for item in metadata.get("preview_translated", [])
        if _preview_image_url(job, item)
    ]
    document_page_count = max(
        _metadata_document_page_count(metadata),
        int(getattr(job, "page_count", 0) or job.pages.count()),
        len(original_pages),
        len(translated_pages),
    )
    bilingual_first_page = _display_safe_bilingual_first_page(
        metadata.get("bilingual_first_page", {"blocks": []})
    )

    return JsonResponse(
        {
            "job_id": job.job_id,
            "left_page_preview": original_pages[0] if original_pages else None,
            "bilingual_first_page": bilingual_first_page,
            "original_pages": original_pages,
            "translated_pages": translated_pages,
            "page_count": document_page_count,
            "document_page_count": document_page_count,
            "previewed_page_count": max(len(original_pages), len(translated_pages)),
            "segments": [
                {
                    "segment_index": segment.segment_index,
                    "source_text": clean_invisible_unicode(segment.source_text),
                    "translated_text": get_display_translation(segment),
                    "display_translated_text": get_display_translation(segment),
                    "needs_review": segment.needs_review,
                    "page_number": segment.page.page_number if segment.page else None,
                    **({"method": segment.method, "confidence": segment.confidence, "metadata": segment.metadata} if include_details else {}),
                }
                for segment in job.segments.order_by("segment_index")
            ],
            **translation_quality,
            "translation_summary": translation_quality,
        }
    )


@login_required
def preview_image(request, job_id, image_name):
    job = _get_owned_job(request, job_id)

    if not PREVIEW_IMAGE_NAME_RE.fullmatch(image_name):
        return JsonResponse({"error": "Invalid preview image name"}, status=400)

    job_dir = Path(job_directory_path(job.job_id)).resolve()

    if not job_dir.exists():
        raise Http404("Job files not found")

    image_path = (job_dir / "preview" / image_name).resolve()

    try:
        common_path = os.path.commonpath([str(job_dir), str(image_path)])
    except ValueError:
        return JsonResponse({"error": "Access denied"}, status=403)

    if common_path != str(job_dir) or not image_path.exists():
        raise Http404("Image not found")

    return FileResponse(open(image_path, "rb"), content_type="image/png")


@login_required
def download_job(request, job_id):
    job = _get_owned_job(request, job_id)
    state = _job_state_context(job)
    requested_format = request.GET.get("format", "translated")

    if requested_format == "bilingual" and not can_download_teacher_copy(request.user):
        raise PermissionDenied("Teacher review copies are not available for this role.")

    if not state["can_download"]:
        if job.status != TranslationJob.Status.COMPLETED:
            messages.info(
                request,
                "The translated PDF will be available after processing is complete.",
            )
        else:
            messages.error(request, "The translated PDF is not available for this job.")

        return redirect("translator:job_detail", job_id=job.id)

    if requested_format == "bilingual":
        resolved_path = _resolve_job_file(job, job.bilingual_file_path)
    else:
        resolved_path = _translated_output_path(job)

    if not resolved_path or not resolved_path.exists():
        messages.error(request, "The translated PDF is missing or no longer available.")
        return redirect("translator:job_detail", job_id=job.id)

    filename_prefix = "bilingual" if requested_format == "bilingual" else "translated"

    return FileResponse(
        open(resolved_path, "rb"),
        as_attachment=True,
        filename=f"{filename_prefix}_{job.job_id[:8]}.pdf",
        content_type="application/pdf",
    )


@login_required
def download_original(request, job_id):
    """Return the owner's original upload without widening cross-user access."""
    job = _get_owned_job(request, job_id)
    resolved_path = _resolve_job_file(job, job.upload_file_path or job.input_file_path)
    if not resolved_path or not resolved_path.exists():
        messages.error(request, "The original document is missing or no longer available.")
        return redirect("translator:job_detail", job_id=job.id)
    return FileResponse(open(resolved_path, "rb"), as_attachment=True, filename=job.original_filename)


@require_http_methods(["GET", "POST"])
def quick_translate(request):
    text = request.POST.get("text") or request.GET.get("text") or ""

    if not text.strip():
        return JsonResponse({"error": "Text is required."}, status=400)

    source_language = (
        request.POST.get("source_language")
        or request.GET.get("source_language")
        or "auto"
    )

    target_language = (
        request.POST.get("target_language")
        or request.GET.get("target_language")
        or "tagabawa"
    )

    try:
        return JsonResponse(quick_translate_text(text, source_language, target_language))
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@login_required
def health(request):
    if not can_view_system_diagnostics(request.user):
        raise PermissionDenied("System diagnostics are restricted to superusers.")
    return render(
        request,
        "translator/health.html",
        {
            "checks": _health_checks(),
            "job_counts": _health_job_counts(),
        },
    )


@permission_required("translator.review_language_entry", raise_exception=True)
def validator_queue(request):
    entries = PhrasebookEntry.objects.order_by("validation_status", "updated_at")
    for field in ("validation_status", "import_batch_id", "access_restriction"):
        value = request.GET.get(field)
        if value:
            entries = entries.filter(**{field: value})
    if request.GET.get("missing_provenance") == "1":
        entries = entries.filter(Q(source_title="") | Q(source_owner=""))
    if request.GET.get("conflict") == "1":
        entries = entries.filter(has_unresolved_conflict=True)
    search_query = request.GET.get("q", "").strip()
    if search_query:
        entries = entries.filter(
            Q(english__icontains=search_query)
            | Q(tagabawa__icontains=search_query)
            | Q(filipino__icontains=search_query)
            | Q(cebuano__icontains=search_query)
        )
    sort = request.GET.get("sort", "status")
    entries = entries.order_by("-updated_at" if sort == "recent" else "validation_status", "updated_at")
    paginator = Paginator(entries, 25)
    entry_page = paginator.get_page(request.GET.get("page", 1))
    return render(
        request,
        "translator/validator_queue.html",
        {
            "entries": entry_page,
            "queue_counts": {
                "pending_entries": PhrasebookEntry.objects.filter(validation_status__in=["pending", "under_review"]).count(),
                "unknown_terms": UnknownTranslationRecord.objects.filter(review_status="pending").count(),
                "ocr_corrections": OCRCorrection.objects.filter(status="proposed").count(),
                "correction_suggestions": CorrectionSuggestion.objects.filter(status="pending").count(),
            },
            "search_query": search_query,
            "selected_sort": sort,
        },
    )


@permission_required("translator.review_language_entry", raise_exception=True)
def validator_entry(request, entry_id):
    entry = get_object_or_404(PhrasebookEntry, id=entry_id)
    if request.method == "POST":
        decision = request.POST.get("decision", "")
        notes = request.POST.get("notes", "").strip()
        if not notes:
            messages.error(request, "A reviewer note is required for every decision.")
        else:
            try:
                review_entry(entry=entry, reviewer=request.user, decision=decision, notes=notes)
                messages.success(request, "Review decision recorded.")
                return redirect("translator:validator_entry", entry_id=entry.id)
            except (PermissionError, ValueError):
                messages.error(request, "This review decision could not be recorded.")
    return render(request, "translator/validator_entry.html", {"entry": entry, "revisions": entry.revisions.all(), "reviews": entry.reviews.all()})


@login_required
@require_POST
def submit_correction_suggestion(request, job_id):
    job = _get_owned_job(request, job_id)
    segment = get_object_or_404(TranslationSegment, id=request.POST.get("segment_id"), job=job)
    suggestion = (request.POST.get("suggested_correction") or "").strip()
    if not suggestion:
        return JsonResponse({"ok": False, "error": "A suggested correction is required."}, status=400)
    CorrectionSuggestion.objects.create(
        job=job, segment=segment, source_text=segment.source_text,
        displayed_translation=get_display_translation(segment),
        suggested_correction=suggestion,
        explanation=(request.POST.get("explanation") or "").strip(), submitted_by=request.user,
    )
    return JsonResponse({"ok": True, "message": "Suggestion submitted for review."}, status=201)


@login_required
def confirm_delete_job(request, job_id):
    """GET — show a confirmation page before soft-deleting a job."""
    job = get_object_or_404(
        TranslationJob.objects.filter(is_deleted=False),
        id=job_id,
        owner=request.user,
    )
    state = _job_card_context(job)
    return render(request, "translator/confirm_delete.html", state)


@login_required
@require_POST
def delete_job(request, job_id):
    """POST — soft-delete a job owned by the current user.

    Only the job owner may delete their own job.  Superusers use the admin
    interface for administrative deletions.
    """
    from django.utils import timezone

    job = get_object_or_404(
        TranslationJob.objects.filter(is_deleted=False),
        id=job_id,
        owner=request.user,
    )

    job.is_deleted = True
    job.deleted_at = timezone.now()
    job.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    UserActivityLog.objects.create(
        user=request.user,
        action="delete_job",
        object_type="TranslationJob",
        object_id=job.job_id,
        metadata={"filename": job.original_filename, "status": job.status},
    )

    SystemEventLog.objects.create(
        actor=request.user,
        job=job,
        event_type="translation_job_deleted",
        message=f"Job soft-deleted by owner: {job.original_filename}",
        metadata={"filename": job.original_filename, "status": job.status},
    )

    # The history page's Remove modal deletes via fetch() and updates the DOM
    # in place; give it JSON instead of queueing a message that would only
    # surface on the next full page load. Non-AJAX callers (the confirm-page
    # fallback for users without JS) keep the message + redirect flow.
    wants_json = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("accept") or "").lower()
    )
    if wants_json:
        return JsonResponse({"ok": True, "message": "Document removed from history."})

    messages.success(request, f"‘{job.original_filename}’ has been removed from your history.")
    return redirect("translator:history")


def _health_checks() -> list:
    dataset_loaded = translation_dataset_loaded()
    return [
        _database_health(),
        _task_mode_health(),
        _redis_health(),
        _celery_worker_health(),
        _tesseract_health(),
        _ocr_languages_health(),
        _media_writability_health(),
        {
            "name": "Translation dataset",
            "status": "ok" if dataset_loaded else "warning",
            "detail": "Loaded" if dataset_loaded else "Not loaded",
        },
        _neural_model_health(),
    ]


def _neural_model_health() -> dict:
    """Report ByT5 neural fallback status without exposing the model path."""
    try:
        from translator.services.neural_translation_service import (
            get_neural_translation_service,
        )

        service = get_neural_translation_service()
        if not service.is_enabled():
            return {
                "name": "Neural fallback (ByT5)",
                "status": "warning",
                "detail": "Disabled (experimental; phrasebook handles all segments)",
            }
        if service.is_available():
            return {
                "name": "Neural fallback (ByT5)",
                "status": "ok",
                "detail": "Enabled and loaded (experimental; all output needs review)",
            }
        return {
            "name": "Neural fallback (ByT5)",
            "status": "warning",
            "detail": service.load_warning or "Enabled but model not loaded",
        }
    except Exception as exc:
        return {"name": "Neural fallback (ByT5)", "status": "error", "detail": str(exc)}


def _database_health() -> dict:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"name": "Database", "status": "ok", "detail": connection.vendor}
    except Exception as exc:
        return {"name": "Database", "status": "error", "detail": str(exc)}


def _task_mode_health() -> dict:
    task_mode = getattr(settings, "LINGOKATUTUBO_TASK_MODE", "thread")
    status = "ok" if str(task_mode).lower() == "celery" else "warning"
    detail = (
        "Celery background worker mode"
        if status == "ok"
        else "Development runner; use Celery for durable background processing"
    )
    return {"name": "Task mode", "status": status, "detail": f"{task_mode} - {detail}"}


def _redis_health() -> dict:
    broker_url = getattr(settings, "CELERY_BROKER_URL", "")
    safe_broker = _safe_service_url(broker_url)
    try:
        import redis

        client = redis.Redis.from_url(
            broker_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        return {"name": "Redis / broker", "status": "ok", "detail": safe_broker}
    except Exception as exc:
        return {
            "name": "Redis / broker",
            "status": "error",
            "detail": f"{safe_broker} unavailable: {exc}",
        }


def _celery_worker_health() -> dict:
    try:
        from lingokatutubo_django.celery import app as celery_app

        replies = celery_app.control.ping(timeout=1)
        if replies:
            return {
                "name": "Celery worker",
                "status": "ok",
                "detail": f"{len(replies)} worker(s) responded",
            }
        return {
            "name": "Celery worker",
            "status": "warning",
            "detail": "No workers responded",
        }
    except Exception as exc:
        return {"name": "Celery worker", "status": "error", "detail": str(exc)}


def _tesseract_health() -> dict:
    try:
        from translator.services.ocr_stage import get_ocr_service

        service = get_ocr_service()
        if service.is_available():
            return {"name": "Tesseract", "status": "ok", "detail": "Available"}
        return {"name": "Tesseract", "status": "error", "detail": "Unavailable"}
    except Exception as exc:
        return {"name": "Tesseract", "status": "error", "detail": str(exc)}


def _ocr_languages_health() -> dict:
    try:
        from translator.services.ocr_stage import get_ocr_service

        languages = get_ocr_service().get_installed_languages()
        detail = ", ".join(languages) if languages else "No languages reported"
        return {
            "name": "Installed OCR languages",
            "status": "ok" if languages else "warning",
            "detail": detail,
        }
    except Exception as exc:
        return {
            "name": "Installed OCR languages",
            "status": "error",
            "detail": str(exc),
        }


def _media_writability_health() -> dict:
    media_root = Path(settings.MEDIA_ROOT)
    probe_dir = media_root / "jobs" / ".health"
    probe_file = probe_dir / "write-check.tmp"
    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        return {
            "name": "Media/job directory",
            "status": "ok",
            "detail": f"Writable: {media_root}",
        }
    except Exception as exc:
        return {
            "name": "Media/job directory",
            "status": "error",
            "detail": f"Not writable: {exc}",
        }


def _health_job_counts() -> dict:
    cutoff = timezone.now() - timezone.timedelta(minutes=15)
    active_filter = Q(is_deleted=False)
    return {
        "queued": TranslationJob.objects.filter(
            active_filter,
            status=TranslationJob.Status.QUEUED,
        ).count(),
        "processing": TranslationJob.objects.filter(
            active_filter,
            status=TranslationJob.Status.PROCESSING,
        ).count(),
        "retrying": TranslationJob.objects.filter(
            active_filter,
            status=TranslationJob.Status.RETRYING,
        ).count(),
        "stale": TranslationJob.objects.filter(
            active_filter,
            status__in=[
                TranslationJob.Status.QUEUED,
                TranslationJob.Status.PROCESSING,
                TranslationJob.Status.RETRYING,
            ],
            updated_at__lte=cutoff,
        ).count(),
    }


def _safe_service_url(raw_url: str) -> str:
    try:
        parsed = urlparse(raw_url)
    except Exception:
        return "configured"
    if not parsed.scheme:
        return "configured"
    host = parsed.hostname or "localhost"
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or ""
    return f"{parsed.scheme}://{host}{port}{path}"


def _get_owned_job(request, job_id) -> TranslationJob:
    return get_object_or_404(_owned_jobs_queryset(request), id=job_id)


def _owned_jobs_queryset(request):
    queryset = TranslationJob.objects.filter(is_deleted=False)

    if not request.user.is_superuser:
        queryset = queryset.filter(owner=request.user)

    return queryset


def _job_payload(job: TranslationJob, user=None) -> dict:
    metadata = job.metadata or {}
    state = _job_state_context(job)
    include_details = can_view_translation_details(user)
    # The pipeline persists checkpoint values when a stage begins. They are
    # useful operational data, but they are not measured completion and must
    # never be presented to people as a precise percentage.
    progress_available = bool(metadata.get("reliable_progress_percent") is not None)
    reliable_progress = metadata.get("reliable_progress_percent") if progress_available else None
    is_partial_result = bool(metadata.get("partial_processing") or metadata.get("partial_output"))

    payload = {
        "job_id": job.job_id,
        "status": job.status,
        "message": _status_message(job.status),
        "error": _failure_message(job) if job.status == TranslationJob.Status.FAILED else None,
        "has_retained_text": _review_segment_count(job) > 0,
        "can_view_validation_markers": can_view_validation_markers(user),
        "can_preview": state["can_preview"],
        "can_download": state["can_download"],
        "is_processing": state["is_processing"],
        "has_failed": state["has_failed"],
        "is_partial_result": is_partial_result,
        "created_at": job.created_at.isoformat(),
        "started_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "is_retrying": job.status == TranslationJob.Status.RETRYING,
        "is_taking_longer": _job_is_taking_longer(job),
    }
    if include_details:
        payload.update({
            "output_file": job.output_file_path or None,
            "progress": job.progress,
            "progress_percent": reliable_progress,
            "progress_available": progress_available,
            "current_phase": job.current_phase,
            "current_step": job.current_step,
            "phase_message": job.phase_message or _status_message(job.status),
            "detection_type": job.detection_type or None,
            "file_type": job.file_type,
            "detected_language": metadata.get("detected_language"),
            "detection_confidence": metadata.get("detection_confidence"),
            "is_mixed_language": metadata.get("is_mixed_language", False),
            "metadata": metadata,
            **_translation_quality_context(job),
        })
    return payload


def _status_message(status: str) -> str:
    return {
        TranslationJob.Status.QUEUED: "Job queued",
        TranslationJob.Status.RETRYING: "Job is being retried",
        TranslationJob.Status.PROCESSING: "Translation in progress",
        TranslationJob.Status.COMPLETED: "Translation complete",
        TranslationJob.Status.FAILED: "Translation failed",
    }.get(status, status)


def _preview_image_url(job: TranslationJob, path_or_name: str) -> str:
    filename = Path(str(path_or_name).replace("\\", "/")).name

    if not filename:
        return ""

    return reverse(
        "translator:translate_preview_image",
        kwargs={"job_id": job.job_id, "image_name": filename},
    )


def _default_structure_path(job: TranslationJob) -> str:
    return job_structure_path(job.job_id)


def _resolve_job_file(job: TranslationJob, path: str):
    if not path:
        return None

    job_dir = Path(job_directory_path(job.job_id)).resolve()
    candidate = Path(path).resolve()

    try:
        common_path = os.path.commonpath([str(job_dir), str(candidate)])
    except ValueError:
        return None

    if common_path != str(job_dir):
        return None

    return candidate


def _job_state_context(job: TranslationJob) -> dict:
    is_processing = job.status in {
        TranslationJob.Status.QUEUED,
        TranslationJob.Status.RETRYING,
        TranslationJob.Status.PROCESSING,
    }

    has_failed = job.status == TranslationJob.Status.FAILED
    can_preview = job.status == TranslationJob.Status.COMPLETED
    can_download = can_preview and _translated_output_exists(job)

    # Phase 4: expose OCR/extraction metadata from job.metadata JSONField
    metadata = job.metadata or {}
    raw_extraction_method = metadata.get("extraction_method", "")
    extraction_method_label = _extraction_method_label(raw_extraction_method)

    ocr_summary = metadata.get("ocr_summary") or {}
    mean_confidence = ocr_summary.get("mean_confidence")  # 0.0–1.0 or None
    ocr_confidence_pct = round(mean_confidence * 100) if mean_confidence is not None else None
    ocr_has_low_quality = bool(ocr_summary.get("has_low_quality_warning", False))

    # Gather OCR warnings from job metadata (set by pipeline) and from OCRResults
    ocr_warnings: list = list(metadata.get("ocr_warnings") or [])
    try:
        for ocr_result in job.ocr_results.all():
            for w in (ocr_result.warnings or []):
                if w and w not in ocr_warnings:
                    ocr_warnings.append(w)
    except Exception:
        pass

    return {
        "job": job,
        "can_preview": can_preview,
        "can_download": can_download,
        "is_processing": is_processing,
        "has_failed": has_failed,
        "can_retry": False,
        # Phase 4 fields
        "extraction_method": raw_extraction_method,
        "extraction_method_label": extraction_method_label,
        "ocr_confidence_pct": ocr_confidence_pct,
        "ocr_has_low_quality": ocr_has_low_quality,
        "ocr_warnings": ocr_warnings,
    }


def _language_pair_label(job: TranslationJob) -> str:
    """Return display labels for the compact Translate workspace only.

    Stored language codes remain untouched. When an auto-detected source has
    already been resolved by the pipeline, surface that familiar label instead
    of the raw ``auto`` code.
    """
    metadata = job.metadata or {}
    source_language = job.source_language
    if source_language == "auto":
        source_language = metadata.get("detected_language") or source_language

    def label(value) -> str:
        raw_value = str(value or "").strip()
        return LANGUAGE_DISPLAY_LABELS.get(
            raw_value,
            raw_value.replace("_", " ").title() or "Unknown",
        )

    return f"{label(source_language)} \u2192 {label(job.target_language)}"


def _job_card_context(job: TranslationJob, user=None) -> dict:
    context = _job_state_context(job)
    uploaded_document = _uploaded_document_for(job)
    ocr_summary = _ocr_summary(job)
    thumbnail = _thumbnail_context(job)
    permissions = translation_permissions(user)
    translation_quality = _translation_quality_context(job)

    context.update(
        {
            "uploaded_document": uploaded_document,
            "document_title": (
                getattr(uploaded_document, "original_filename", "")
                or job.original_filename
            ),
            "uploaded_at": getattr(uploaded_document, "created_at", None)
            or job.created_at,
            "completed_at": job.completed_at,
            "has_retained_text": translation_quality["translation_has_review_items"],
            "can_download_teacher_copy": can_download_teacher_copy(user),
            "can_download_validator_copy": can_download_validator_copy(user),
            **permissions,
            "page_count": int(
                getattr(job, "page_count", 0)
                or job.pages.count()
                or _metadata_document_page_count(job.metadata or {})
            ),
            "thumbnail_url": thumbnail["url"],
            "thumbnail_kind": thumbnail["kind"],
            "thumbnail_label": thumbnail["label"],
            "file_icon_class": _file_icon_class(job.file_type),
            "language_pair_label": _language_pair_label(job),
            "status_label": _status_label(job.status),
            "status_class": _status_class(job.status),
            "failure_message": _failure_message(job),
            "technical_error_detail": (
                clean_invisible_unicode(job.error)
                if permissions["can_view_system_diagnostics"] and job.status == TranslationJob.Status.FAILED and job.error
                else ""
            ),
            "progress_percent": 100
            if job.status == TranslationJob.Status.COMPLETED
            else job.progress,
            "is_retrying": job.status == TranslationJob.Status.RETRYING,
            "is_taking_longer": _job_is_taking_longer(job),
            "status_api_url": reverse("translator:status", args=[job.id]),
            "result_summary": _translation_result_summary(job),
        }
    )

    if permissions["can_view_translation_details"]:
        context.update({
            "ocr_confidence": _annotated_or_summary(job, "ocr_confidence", ocr_summary["confidence"]),
            **translation_quality,
            "workflow_steps": _workflow_steps(job),
        })
    else:
        for key in (
            "extraction_method", "extraction_method_label", "ocr_confidence_pct",
            "ocr_has_low_quality", "ocr_warnings", "technical_error_detail",
        ):
            context.pop(key, None)
        context.update({
            "translation_has_review_items": translation_quality["translation_has_review_items"],
            "result_summary": {"partial": _translation_result_summary(job)["partial"]},
        })

    return context


def _positive_int(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def _metadata_document_page_count(metadata: dict) -> int:
    return max(
        _positive_int(metadata.get("translated_page_count")),
        _positive_int(metadata.get("source_page_count")),
        _positive_int(metadata.get("layout_page_count")),
        _positive_int(metadata.get("page_count")),
    )


def _translation_quality_context(job: TranslationJob) -> dict:
    segment_count = _segment_count(job)
    review_segment_count = _review_segment_count(job)
    translation_confidence = _translation_confidence(job)

    return {
        "segment_count": segment_count,
        "review_segment_count": review_segment_count,
        "translation_confidence": translation_confidence,
        "translation_confidence_pct": _confidence_pct(translation_confidence),
        "translation_has_review_items": review_segment_count > 0,
    }


def _translation_result_summary(job: TranslationJob) -> dict:
    """Return plain-language result metrics without leaking pipeline enums."""
    metadata = job.metadata or {}
    recorded = metadata.get("translation_summary") or metadata.get("match_counts") or {}
    methods = {"exact": 0, "normalized": 0, "fuzzy": 0}
    for raw_key, value in recorded.items():
        key = str(raw_key).lower().replace("_match", "").replace("match_", "")
        if key in methods:
            methods[key] = _positive_int(value)

    # Older jobs have no summary metadata. Derive only the familiar matching
    # families and leave unknown methods out of the user-facing display.
    if not any(methods.values()):
        for method in job.segments.values_list("method", flat=True):
            normalized = str(method or "").lower()
            if "exact" in normalized:
                methods["exact"] += 1
            elif "normal" in normalized:
                methods["normalized"] += 1
            elif "fuzzy" in normalized:
                methods["fuzzy"] += 1

    unknown_count = getattr(job, "review_segment_count", None)
    if unknown_count is None:
        unknown_count = job.segments.filter(needs_review=True).count()
    ocr_warnings = (metadata.get("ocr_warnings") or [])
    layout_warnings = (metadata.get("layout_warnings") or metadata.get("reconstruction_warnings") or [])
    return {
        **methods,
        "unknown": int(unknown_count or 0),
        "pages": _metadata_document_page_count(metadata) or job.pages.count(),
        "ocr_warnings": len(ocr_warnings),
        "layout_warnings": len(layout_warnings),
        "verified_resources": _positive_int(recorded.get("verified_resources")),
        "unverified_resources": _positive_int(recorded.get("unverified_resources")),
        "partial": bool(metadata.get("partial_processing") or metadata.get("partial_output")),
    }


def _segment_count(job: TranslationJob) -> int:
    return int(getattr(job, "segment_count", 0) or job.segments.count())


def _review_segment_count(job: TranslationJob) -> int:
    annotated = getattr(job, "review_segment_count", None)
    if annotated is not None:
        return int(annotated or 0)
    return int(job.segments.filter(needs_review=True).count())


def _translation_confidence(job: TranslationJob):
    annotated = getattr(job, "translation_confidence", None)
    if annotated is not None:
        return annotated

    aggregate = job.segments.aggregate(value=Avg("confidence"))
    return aggregate["value"]


def _confidence_pct(confidence):
    return round(confidence * 100) if confidence is not None else None


def _workflow_steps(job: TranslationJob) -> list:
    steps = [
        ("uploaded", "Uploaded"),
        ("extracting", "Extracting / OCR"),
        ("translating", "Translating"),
        ("output", "Generating Output"),
        ("completed", "Completed"),
    ]

    if job.status == TranslationJob.Status.FAILED:
        steps[-1] = ("failed", "Failed")
        completed_index = _workflow_phase_index(job.current_phase)
        active_index = None
    elif job.status == TranslationJob.Status.COMPLETED:
        completed_index = len(steps) - 1
        active_index = None
    elif job.status in {
        TranslationJob.Status.QUEUED,
        TranslationJob.Status.RETRYING,
        TranslationJob.Status.PROCESSING,
    }:
        active_index = _workflow_phase_index(job.current_phase)
        completed_index = max(0, active_index - 1)
    else:
        completed_index = 0
        active_index = None

    output = []

    for index, (key, label) in enumerate(steps):
        if job.status == TranslationJob.Status.FAILED and index == len(steps) - 1:
            state = "failed"
        elif active_index == index:
            state = "active"
        elif index <= completed_index:
            state = "complete"
        else:
            state = "pending"

        output.append({"key": key, "label": label, "state": state})

    return output


def _workflow_phase_index(phase: str) -> int:
    phase = str(phase or "").lower()
    phase_map = {
        "queued": 0,
        "retrying": 0,
        "uploading": 0,
        "detecting": 1,
        "extracting": 1,
        "ocr": 1,
        "translating": 2,
        "reconstructing": 3,
        "preview_generation": 3,
        "bilingual_output": 3,
        "completed": 4,
        "failed": 4,
    }
    return phase_map.get(phase, 1)


def _job_is_taking_longer(job: TranslationJob) -> bool:
    if job.status not in {
        TranslationJob.Status.QUEUED,
        TranslationJob.Status.PROCESSING,
        TranslationJob.Status.RETRYING,
    }:
        return False
    threshold_minutes = int(
        getattr(settings, "LINGOKATUTUBO_LONG_JOB_MINUTES", 10)
    )
    return job.created_at <= timezone.now() - timezone.timedelta(
        minutes=threshold_minutes
    )


def _uploaded_document_for(job: TranslationJob):
    try:
        return job.uploaded_document
    except UploadedDocument.DoesNotExist:
        return None


def _annotated_or_summary(job: TranslationJob, name: str, fallback):
    value = getattr(job, name, None)
    return fallback if value is None else value


def _thumbnail_context(job: TranslationJob) -> dict:
    for page in _iter_related(job, "pages"):
        url = _safe_preview_url(job, getattr(page, "source_image_path", ""))

        if url:
            return {
                "url": url,
                "kind": "image",
                "label": f"Page {page.page_number}",
            }

    metadata = job.metadata or {}

    for item in metadata.get("preview_original", []):
        url = _safe_preview_url(job, item)

        if url:
            return {
                "url": url,
                "kind": "image",
                "label": "Preview",
            }

    for output in _iter_related(job, "generated_outputs"):
        if output.output_type != GeneratedOutput.OutputType.PREVIEW_IMAGE:
            continue

        url = _safe_preview_url(job, output.file_path)

        if url:
            return {
                "url": url,
                "kind": "image",
                "label": "Preview",
            }

    return {
        "url": "",
        "kind": "icon",
        "label": _file_type_label(job.file_type),
    }


def _safe_preview_url(job: TranslationJob, path_or_name: str) -> str:
    if not path_or_name:
        return ""

    filename = Path(str(path_or_name).replace("\\", "/")).name

    if not filename or not PREVIEW_IMAGE_NAME_RE.fullmatch(filename):
        return ""

    return _preview_image_url(job, filename)


def _iter_related(job: TranslationJob, related_name: str):
    manager = getattr(job, related_name)

    try:
        return list(manager.all())
    except Exception:
        return []


def _file_type_label(file_type: str) -> str:
    return {
        "pdf": "PDF",
        "docx": "DOCX",
        "jpg": "IMG",
        "png": "IMG",
        "txt": "TXT",
    }.get(str(file_type).lower(), "DOC")


def _file_icon_class(file_type: str) -> str:
    return f"file-{str(file_type or 'document').lower()}"


def _extraction_method_label(method: str) -> str:
    """Convert internal extraction_method code to a human-readable label."""
    return {
        'direct_pdf_text': 'Direct PDF Text (PyMuPDF)',
        'ocr_image': 'OCR - Tesseract',
        'docx_text': 'DOCX Text (python-docx)',
        'plain_text': 'Plain Text',
        'hybrid': 'Hybrid (text + OCR)',
        'text_extraction': 'Text Extraction',
    }.get(method, method.replace('_', ' ').title() if method else '—')


def _status_label(status: str) -> str:
    return {
        TranslationJob.Status.QUEUED: 'Pending',
        TranslationJob.Status.RETRYING: 'Retrying',
        TranslationJob.Status.PROCESSING: 'Processing',
        TranslationJob.Status.COMPLETED: 'Completed',
        TranslationJob.Status.FAILED: 'Failed',
    }.get(status, status.title() if status else 'Unknown')


def _status_class(status: str) -> str:
    if status == TranslationJob.Status.QUEUED:
        return 'pending'
    if status == TranslationJob.Status.RETRYING:
        return 'retrying'
    return str(status or 'unknown')


def _failure_message(job: TranslationJob) -> str:
    """User-facing failure copy — always the safe generic message.

    The raw backend error (``job.error``) may contain codec errors,
    tracebacks, or file paths; it is exposed separately, only to staff, via
    ``_job_card_context``'s ``technical_error_detail``.
    """
    if job.status != TranslationJob.Status.FAILED:
        return ''
    return GENERIC_TRANSLATION_FAILURE_MESSAGE


def _translated_output_exists(job: TranslationJob) -> bool:
    return _translated_output_path(job) is not None


def _translated_output_path(job: TranslationJob):
    resolved = _resolve_job_file(job, job.output_file_path)

    if resolved and resolved.exists():
        return resolved

    for output in job.generated_outputs.filter(
        output_type=GeneratedOutput.OutputType.TRANSLATED_PDF
    ):
        output_path = _resolve_job_file(job, output.file_path)

        if output_path and output_path.exists():
            return output_path

    return None


def _ocr_summary(job: TranslationJob) -> dict:
    results = list(job.ocr_results.all())
    confidences = [
        result.confidence for result in results if result.confidence is not None
    ]

    return {
        "count": len(results),
        "confidence": round(sum(confidences) / len(confidences), 4)
        if confidences
        else None,
        "warnings": [
            warning for result in results for warning in (result.warnings or [])
        ],
    }


def _image_preview_context(job: TranslationJob) -> dict:
    metadata = job.metadata or {}

    original_pages = [
        _preview_image_url(job, item)
        for item in metadata.get("preview_original", [])
        if _preview_image_url(job, item)
    ]

    translated_pages = [
        _preview_image_url(job, item)
        for item in metadata.get("preview_translated", [])
        if _preview_image_url(job, item)
    ]
    declared_page_count = _metadata_document_page_count(metadata)

    document_pages = list(_iter_related(job, "pages"))
    page_text = {
        page.page_number: clean_invisible_unicode(page.extracted_text or "").strip()
        for page in document_pages
    }
    source_segments = {}
    translated_segments = {}
    page_numbers = set(page_text)

    for segment in job.segments.select_related("page").order_by("segment_index"):
        # Segments are normally linked to the DocumentPage they were
        # extracted from. Fall back to page 1 so a segment without that
        # link (e.g. legacy data) still surfaces in the normal-user-facing
        # Original/Translated panels instead of disappearing.
        page_number = segment.page.page_number if segment.page else 1
        page_numbers.add(page_number)
        if segment.source_text:
            source_segments.setdefault(page_number, []).append(
                clean_invisible_unicode(segment.source_text)
            )
        display_translation = get_display_translation(segment)
        if display_translation:
            translated_segments.setdefault(page_number, []).append(display_translation)

    image_page_count = max(len(original_pages), len(translated_pages))
    if image_page_count:
        page_numbers.update(range(1, image_page_count + 1))
    if declared_page_count:
        page_numbers.update(range(1, declared_page_count + 1))

    page_pairs = []
    for page_number in sorted(page_numbers):
        original_text = page_text.get(page_number) or "\n".join(
            source_segments.get(page_number, [])
        )
        translated_text = "\n".join(translated_segments.get(page_number, []))
        page_pairs.append(
            {
                "number": page_number,
                "original_url": original_pages[page_number - 1]
                if page_number - 1 < len(original_pages)
                else "",
                "translated_url": translated_pages[page_number - 1]
                if page_number - 1 < len(translated_pages)
                else "",
                "original_text": original_text,
                "translated_text": translated_text,
            }
        )

    return {
        "original_pages": original_pages,
        "translated_pages": translated_pages,
        "page_pairs": page_pairs,
        "page_count": max(
            len(original_pages),
            len(translated_pages),
            len(page_pairs),
            declared_page_count,
        ),
        "document_page_count": max(len(page_pairs), declared_page_count),
        "previewed_page_count": image_page_count,
    }


def _display_safe_bilingual_first_page(data: dict) -> dict:
    safe = copy.deepcopy(data or {"blocks": []})
    for block in safe.get("blocks", []):
        source_text = clean_invisible_unicode(
            block.get("source_text") or block.get("original_text") or ""
        )
        method = block.get("translation_method") or block.get("method")
        cascade_stage = block.get("cascade_stage")
        translated_text = block.get("display_translated_text")
        if translated_text is None:
            translated_text = block.get("translated_text")
        display_text = get_display_translation_text(
            source_text,
            translated_text,
            method,
            cascade_stage,
        )
        block["display_translated_text"] = display_text
        block["translated_text"] = display_text
        block.pop("raw_translated_text", None)
    return safe


def _display_safe_structure(data: dict) -> dict:
    safe = copy.deepcopy(data)
    for page in safe.get("pages", []):
        for block in page.get("blocks", []):
            if block.get("type") != "text" and block.get("block_type") != "text":
                continue
            block_source_parts = []
            block_display_parts = []
            for line in block.get("lines", []):
                source_text = clean_invisible_unicode(
                    line.get("source_text") or line.get("text") or ""
                ).strip()
                method = line.get("translation_method") or line.get("cascade_stage")
                cascade_stage = line.get("cascade_stage")
                translated_text = line.get("display_translated_text")
                if translated_text is None:
                    translated_text = line.get("translated_text")
                display_text = get_display_translation_text(
                    source_text,
                    translated_text,
                    method,
                    cascade_stage,
                )
                line["display_translated_text"] = display_text
                line["translated_text"] = display_text
                if source_text:
                    block_source_parts.append(source_text)
                if display_text:
                    block_display_parts.append(display_text)

            block_source = clean_invisible_unicode(
                block.get("source_text") or block.get("original_text") or " ".join(block_source_parts)
            )
            block_method = block.get("translation_method") or block.get("cascade_stage")
            block_display = block.get("display_translated_text")
            if block_display is None:
                block_display = block.get("translated_text")
            display_text = get_display_translation_text(
                block_source,
                block_display or " ".join(block_display_parts),
                block_method,
                block.get("cascade_stage"),
            )
            block["display_translated_text"] = display_text
            block["translated_text"] = display_text
    return safe


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()

    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()
