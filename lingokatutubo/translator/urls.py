from django.contrib.auth import views as auth_views
from django.urls import path

from . import quick_translate, review_manifest, views


app_name = "translator"

urlpatterns = [
    path("", views.home, name="home"),
    path("bagobo-tagabawa/", views.bagobo_tagabawa, name="bagobo_tagabawa"),
    path("culture/", views.culture, name="culture"),
    path("nature/", views.nature, name="nature"),
    path("community/", views.community, name="community"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("accounts/signup/", views.signup, name="signup"),
    path(
        "accounts/login/",
        views.TranslatorLoginView.as_view(),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("translate/", views.translate, name="translate"),
    path("translate/history/", views.history, name="history"),
    path("translate/job/<uuid:job_id>/", views.job_detail, name="job_detail"),
    path("translate/job/<uuid:job_id>/preview/", views.preview, name="job_preview"),
    path("translate/job/<uuid:job_id>/download/", views.download_job, name="job_download"),
    path("translate/job/<uuid:job_id>/download-original/", views.download_original, name="job_download_original"),
    path("translate/job/<uuid:job_id>/delete/", views.confirm_delete_job, name="job_delete_confirm"),
    path("translate/job/<uuid:job_id>/delete/confirm/", views.delete_job, name="job_delete"),
    path("translate/upload/", views.api_translate, name="upload"),
    path("translate/status/<uuid:job_id>/", views.api_job_status, name="status"),
    path("translate/structure/<uuid:job_id>/", views.api_structure, name="structure"),
    path("translate/preview-data/<uuid:job_id>/", views.api_preview, name="preview_data"),
    path(
        "translate/preview-image/<uuid:job_id>/<str:image_name>/",
        views.preview_image,
        name="translate_preview_image",
    ),
    path("translate/download/<uuid:job_id>/", views.download_job, name="translate_download"),
    path("translate/preview/<uuid:job_id>/", views.preview, name="preview"),
    path("translate/review-manifest/<uuid:job_id>/", review_manifest.review_manifest, name="review_manifest"),
    path("health/", views.health, name="health"),
    path("translation-resources/", views.translation_resources, name="translation_resources"),
    path("translation-resources/add/", views.translation_resource_add, name="translation_resource_add"),
    path("translation-resources/<int:entry_id>/edit/", views.translation_resource_edit, name="translation_resource_edit"),
    path("translation-resources/<int:entry_id>/toggle/", views.translation_resource_toggle, name="translation_resource_toggle"),
    path("translation-resources/import/", views.translation_resources_import, name="translation_resources_import"),
    path("translation-resources/import/confirm/", views.translation_resources_import_confirm, name="translation_resources_import_confirm"),
    path("translation-resources/export/", views.translation_resources_export, name="translation_resources_export"),
    path("translation-resources/match-tester/", views.translation_resources_match_tester, name="translation_resources_match_tester"),
    path("translation-resources/legacy-staging/", views.legacy_resource_staging, name="legacy_resource_staging"),
    path("translation-resources/legacy-staging/action/", views.legacy_resource_staging_action, name="legacy_resource_staging_action"),
    path("translation-resources/legacy-staging/import/confirm/", views.legacy_resource_staging_import_confirm, name="legacy_resource_staging_import_confirm"),
    path("governance/validator/", views.validator_queue, name="validator_queue"),
    path("governance/validator/<int:entry_id>/", views.validator_entry, name="validator_entry"),
    path("translate/job/<uuid:job_id>/suggest-correction/", views.submit_correction_suggestion, name="submit_correction_suggestion"),

    # Compatibility aliases for earlier Next.js/FastAPI-style API calls.
    path("api/translate/", views.api_translate, name="api_translate"),
    path("api/jobs/<uuid:job_id>/", views.api_job_status, name="api_job_status"),
    path("api/status/<uuid:job_id>/", views.api_job_status, name="api_status"),
    path("api/structure/<uuid:job_id>/", views.api_structure, name="api_structure"),
    path("api/preview/<uuid:job_id>/", views.api_preview, name="api_preview"),
    path(
        "api/preview-image/<uuid:job_id>/<str:image_name>/",
        views.preview_image,
        name="preview_image",
    ),
    path("api/download/<uuid:job_id>/", views.download_job, name="download"),
    path("api/quick-translate/", quick_translate.quick_translate, name="quick_translate"),
]
