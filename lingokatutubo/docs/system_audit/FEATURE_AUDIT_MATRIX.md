# Feature Audit Matrix

This document provides a comprehensive audit of all features identified within the LINGOKATUTUBO system.

## 1. Feature Status Summary

| Status | Count | Description |
|--------|-------|-------------|
| **Fully Implemented** | 30 | Available and functioning end-to-end (UI + Backend). |
| **Partially Implemented** | 1 | Code exists but is disabled, experimental, or incomplete. |
| **Backend Only** | 4 | Backend logic or admin functionality exists, but no user-facing UI. |
| **Total Features** | **35** | |

## 2. Complete Feature Audit Matrix

| ID | Feature | Users | Status | Main Components | Auth | Test Coverage | Evidence | Issues |
|-----|---------|-------|--------|-----------------|------|---------------|----------|--------|
| F-01 | User Registration | Guest | Fully Implemented | views.signup, SignUpForm, registration/signup.html | None (correct) | Tested (tests.py) | [EV-FEAT-001] views.py:154-163, forms.py:119-124 | Email field is optional |
| F-02 | User Login | Guest | Fully Implemented | TranslatorLoginView, registration/login.html | None (correct) | Tested | [EV-FEAT-002] views.py:166-179, urls.py:13-17 | No brute-force protection |
| F-03 | User Logout | Authenticated | Fully Implemented | Django LogoutView | login_required (built-in) | Tested | [EV-FEAT-003] urls.py:18 | -- |
| F-04 | Password Reset | Guest | Fully Implemented | Django auth views, 4 templates | None (correct) | Not directly tested | [EV-FEAT-004] lingokatutubo_django/urls.py, templates/translator/password_reset_*.html | Console email backend in dev |
| F-05 | Dashboard | Authenticated | Fully Implemented | views.dashboard, dashboard.html | @login_required | Tested (test_phase4.py) | [EV-FEAT-005] views.py:128-151 | Role-specific content blocks |
| F-06 | Document Upload | Authenticated | Fully Implemented | views.api_translate, DocumentUploadForm | @api_login_required + rate limits | Extensively tested | [EV-FEAT-006] views.py:430-546 | Max 2 active jobs, 5/hr limit |
| F-07 | PDF Processing (Digital) | System | Fully Implemented | ExtractionService (PyMuPDF), PipelineService | System process | Tested | [EV-FEAT-007] services/extraction_service.py, services/pipeline_service.py | -- |
| F-08 | PDF Processing (Scanned/OCR) | System | Fully Implemented | OCRService (Tesseract), PipelineService | System process | Tested | [EV-FEAT-008] services/ocr_stage/ocr_service.py | Depends on tesseract binary |
| F-09 | Image Processing (JPG/PNG) | System | Fully Implemented | OCRService | System process | Tested | [EV-FEAT-009] forms.py:28, pipeline_service.py | Treated as single-page scan |
| F-10 | DOCX Processing | System | Fully Implemented | PipelineService | System process | Tested | [EV-FEAT-010] pipeline_service.py | -- |
| F-11 | TXT Processing | System | Fully Implemented | PipelineService | System process | Tested | [EV-FEAT-011] pipeline_service.py, forms.py:103-108 | UTF-8 validation |
| F-12 | Phrasebook Translation Cascade | System | Fully Implemented | TranslationDataset, PipelineService | System process | Extensively tested | [EV-FEAT-012] services/translation_dataset.py, services/pipeline_service.py | 1015-row dataset |
| F-13 | Neural Translation (ByT5) | System | Partially Implemented | NeuralTranslationService | Disabled by default | Partially tested | [EV-FEAT-013] services/neural_translation_service.py, settings.py:216-228 | Experimental, needs model files |
| F-14 | Unknown Word Detection | System | Fully Implemented | PipelineService, UnknownTranslationRecord model | System process | Tested | [EV-FEAT-014] models.py:289-315, pipeline_service.py | Creates review queue items |
| F-15 | Document Reconstruction | System | Fully Implemented | ReconstructionService | System process | Tested | [EV-FEAT-015] services/reconstruction_service.py | Best-effort layout preservation |
| F-16 | Preview Image Generation | System | Fully Implemented | PipelineService, views.preview_image | @login_required + owner check | Tested | [EV-FEAT-016] views.py:660-682 | PNG images per page |
| F-17 | Bilingual PDF Output | System | Fully Implemented | ReconstructionService | System process | Tested | [EV-FEAT-017] reconstruction_service.py | Alternating original/translated pages |
| F-18 | Bilingual Text Preview | Authenticated | Fully Implemented | views.preview, preview.html | @login_required + owner check | Tested | [EV-FEAT-018] views.py:344-427 | Paginated segments |
| F-19 | Translation History | Authenticated | Fully Implemented | views.history, history.html | @login_required + owner filter | Tested | [EV-FEAT-019] views.py:251-299 | Search + status filter |
| F-20 | Job Status Polling API | Authenticated | Fully Implemented | views.api_job_status, app.js PollingController | @api_login_required + owner check | Tested | [EV-FEAT-020] views.py:549-555, static/js/app.js | Real-time progress updates |
| F-21 | Download Translated PDF | Authenticated | Fully Implemented | views.download_job | @login_required + owner check | Tested | [EV-FEAT-021] views.py:685-719 | Supports translated + bilingual format |
| F-22 | Soft Delete Jobs | Authenticated | Fully Implemented | views.delete_job, confirm_delete.html | @login_required + owner check | Tested | [EV-FEAT-022] views.py:808-868 | AJAX + fallback HTML |
| F-23 | Quick Translate API | Any (NO AUTH!) | Fully Implemented | quick_translate.py, views.quick_translate | NONE | Tested (test_phase1.py) | [EV-FEAT-023] views.py:722-744, urls.py:55 | Missing auth check! |
| F-24 | Correction Suggestions | Authenticated | Fully Implemented | views.submit_correction_suggestion, CorrectionSuggestion model | @login_required + owner check | Partially tested | [EV-FEAT-024] views.py:791-805, models.py:499-515 | No reviewer UI for suggestions |
| F-25 | Validator Queue | Validator | Fully Implemented | views.validator_queue/entry, validator_queue/entry.html | @permission_required | Tested (test_phase2.py) | [EV-FEAT-025] views.py:759-788 | Filtering by validation_status |
| F-26 | System Health Dashboard | Staff | Fully Implemented | views.health, health.html | @staff_member_required | Tested | [EV-FEAT-026] views.py:747-756, 871-917 | DB, Redis, Celery, Tesseract, OCR langs, Neural |
| F-27 | Admin Interface | Staff | Fully Implemented | admin.py (438 lines) | Django admin auth | Not directly tested | [EV-FEAT-027] admin.py:1-438 | Comprehensive ModelAdmin configs |
| F-28 | Audit Logging | System | Fully Implemented | SystemEventLog, UserActivityLog | System writes | Tested | [EV-FEAT-028] models.py:618-675, views.py:512-526 | Read-only in admin |
| F-29 | Language Resource Import | Admin (CLI) | Backend Only | import_language_resources, import_phrasebook commands | Management command | Partially tested | [EV-FEAT-029] management/commands/ | No web UI |
| F-30 | Governance Eligibility | System | Backend Only | services/governance.py | System process | Tested (test_phase2.py) | [EV-FEAT-030] governance.py:17-47 | Controls runtime translation data |
| F-31 | GlossaryTerm Management | Staff | Backend Only | GlossaryTerm model, admin.py | Admin only | Not tested | [EV-FEAT-031] models.py:517-549, admin.py:361-378 | Not used in translation pipeline |
| F-32 | Dataset Import Batch | Staff | Backend Only | DatasetImportBatch model, admin.py | Admin only | Not tested | [EV-FEAT-032] models.py:588-615 | No processing workflow |
| F-33 | Review Manifest | Authenticated | Fully Implemented | review_manifest.py | URL exists | Not found | [EV-FEAT-033] urls.py:37 | Unclear implementation scope |
| F-34 | Job Structure JSON API | Authenticated | Fully Implemented | views.api_structure | @api_login_required + owner | Tested | [EV-FEAT-034] views.py:558-591 | Reads from disk |
| F-35 | Password Reset Email | Guest | Fully Implemented | Django password reset views | None (correct) | Not directly tested | [EV-FEAT-035] settings.py:153-170, templates | Console backend in dev |

## 3. Feature Details

* **F-01: User Registration** (`EV-FEAT-001`) - Enables guest users to sign up, relying on a basic form with an optional email field.
* **F-02: User Login** (`EV-FEAT-002`) - Authenticates users to access restricted sections of the platform. Lacks brute-force protection.
* **F-03: User Logout** (`EV-FEAT-003`) - Standard session termination via Django's built-in LogoutView.
* **F-04: Password Reset** (`EV-FEAT-004`) - Allows unauthenticated users to recover access via a console-backed email service in development.
* **F-05: Dashboard** (`EV-FEAT-005`) - Main authenticated landing page displaying role-specific content blocks.
* **F-06: Document Upload** (`EV-FEAT-006`) - Protected endpoint for uploading documents, capped at 2 active jobs or 5 uploads per hour.
* **F-07: PDF Processing (Digital)** (`EV-FEAT-007`) - System extraction service leveraging PyMuPDF for native PDF text processing.
* **F-08: PDF Processing (Scanned/OCR)** (`EV-FEAT-008`) - Uses Tesseract to process scanned PDFs through a designated OCR stage.
* **F-09: Image Processing (JPG/PNG)** (`EV-FEAT-009`) - Routes standard image formats through the single-page scan OCR pipeline.
* **F-10: DOCX Processing** (`EV-FEAT-010`) - Document parsing and translation workflow for Microsoft Word files.
* **F-11: TXT Processing** (`EV-FEAT-011`) - Extracts text from raw `.txt` files with enforced UTF-8 validation.
* **F-12: Phrasebook Translation Cascade** (`EV-FEAT-012`) - Implements deterministic translation via a 1015-row dictionary dataset.
* **F-13: Neural Translation (ByT5)** (`EV-FEAT-013`) - Experimental, partially implemented machine learning fallback that is currently disabled by default.
* **F-14: Unknown Word Detection** (`EV-FEAT-014`) - Flags unrecognized terms during translation and queues them for human review.
* **F-15: Document Reconstruction** (`EV-FEAT-015`) - Repackages extracted text into output documents while attempting best-effort layout preservation.
* **F-16: Preview Image Generation** (`EV-FEAT-016`) - Creates static PNG thumbnails of document pages for authenticated owners.
* **F-17: Bilingual PDF Output** (`EV-FEAT-017`) - Produces an alternating page PDF output showing both the original and translated text side-by-side.
* **F-18: Bilingual Text Preview** (`EV-FEAT-018`) - Authenticated web viewer displaying paginated, side-by-side text segments.
* **F-19: Translation History** (`EV-FEAT-019`) - Lists past translations with search capabilities and status filtering.
* **F-20: Job Status Polling API** (`EV-FEAT-020`) - Serves real-time progress updates to frontend components for active translation jobs.
* **F-21: Download Translated PDF** (`EV-FEAT-021`) - Endpoint restricted to job owners for retrieving final bilingual or standard PDFs.
* **F-22: Soft Delete Jobs** (`EV-FEAT-022`) - Provides an AJAX interface to mark translations as deleted without purging immediately from the database.
* **F-23: Quick Translate API** (`EV-FEAT-023`) - An unauthenticated testing/utility endpoint found to have missing authorization checks.
* **F-24: Correction Suggestions** (`EV-FEAT-024`) - Allows users to propose translation corrections, though lacking a dedicated validator UI.
* **F-25: Validator Queue** (`EV-FEAT-025`) - Permission-restricted queue view for reviewing system items by validation status.
* **F-26: System Health Dashboard** (`EV-FEAT-026`) - Staff-only dashboard reporting on critical service states (Redis, Celery, Tesseract).
* **F-27: Admin Interface** (`EV-FEAT-027`) - Extensive built-in Django administration site configured with detailed ModelAdmins.
* **F-28: Audit Logging** (`EV-FEAT-028`) - Background tracking of user and system events, exposed read-only in the admin panel.
* **F-29: Language Resource Import** (`EV-FEAT-029`) - Command-line tools for bootstrapping dictionaries without an equivalent web interface.
* **F-30: Governance Eligibility** (`EV-FEAT-030`) - Backend logic controlling which translation resources are valid for runtime use.
* **F-31: GlossaryTerm Management** (`EV-FEAT-031`) - Staff data-entry feature that remains disconnected from the core translation pipeline.
* **F-32: Dataset Import Batch** (`EV-FEAT-032`) - Exists in models and admin but lacks a dedicated automated processing workflow.
* **F-33: Review Manifest** (`EV-FEAT-033`) - A routed endpoint with an unclear implementation scope or detailed functionality.
* **F-34: Job Structure JSON API** (`EV-FEAT-034`) - Exposes internal on-disk job structures to authenticated owners.
* **F-35: Password Reset Email** (`EV-FEAT-035`) - Utilizes Django's internal template mechanisms for routing reset tokens via development console email.

## 4. Features Not Found

During the audit, the following standard features were expected but **not found** in the current implementation:
* **Notifications**: No system for alerting users (in-app or email) when background jobs complete.
* **Data Export**: No utility for users or administrators to bulk-export their history, translation data, or glossary terms.
* **Search within Translations**: Users cannot search for specific text inside a completed translated document via the web interface.
* **User Profile Management**: Beyond the basic Django admin panel, there is no user-facing page to update profile details, change email, or manage account preferences.
