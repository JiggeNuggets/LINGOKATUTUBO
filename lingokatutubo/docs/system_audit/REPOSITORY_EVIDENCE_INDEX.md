# Repository Evidence Index

This document indexes all evidence used throughout the audit. 

| Evidence ID | File | Component | What It Proves | Related Feature/Diagram |
|-------------|------|-----------|----------------|------------------------|
| EV-001 | translator/models.py | TranslationJob model (lines 60-130) | Core job entity with UUID PK, owner FK, status choices, soft-delete fields | ERD, F-06 to F-22 |
| EV-002 | translator/models.py | UploadedDocument model (lines 132-160) | Document metadata tracking with checksum | ERD, F-06 |
| EV-003 | translator/models.py | DocumentPage model (lines 163-187) | Per-page extraction data with dimensions | ERD, AD-03 |
| EV-004 | translator/models.py | OCRResult model (lines 190-244) | OCR output with confidence, review status | ERD, F-08 |
| EV-005 | translator/models.py | TranslationSegment model (lines 247-286) | Individual translation segments with method/confidence | ERD, F-12 |
| EV-006 | translator/models.py | UnknownTranslationRecord (lines 289-315) | Review queue for untranslatable text | ERD, F-14 |
| EV-007 | translator/models.py | OCRCorrection model (lines 318-338) | Append-only OCR correction history | ERD |
| EV-008 | translator/models.py | PhrasebookEntry model (lines 341-413) | Multilingual phrasebook with governance fields | ERD, F-12, F-25 |
| EV-009 | translator/models.py | PhrasebookEntryRevision (lines 416-424) | Revision tracking for phrasebook entries | ERD, F-25 |
| EV-010 | translator/models.py | LanguageResourceImportBatch (lines 427-449) | Import batch tracking with statistics | ERD, F-29 |
| EV-011 | translator/models.py | LanguageResourceIssue (lines 455-476) | Issue tracking for imports | ERD, F-29 |
| EV-012 | translator/models.py | LanguageEntryReview (lines 478-496) | Validator review decisions | ERD, F-25, UC-18 |
| EV-013 | translator/models.py | CorrectionSuggestion (lines 499-515) | User-submitted corrections | ERD, F-24, UC-15 |
| EV-014 | translator/models.py | GlossaryTerm (lines 517-549) | Term glossary (UNUSED in pipeline) | ERD, F-031 |
| EV-015 | translator/models.py | GeneratedOutput (lines 552-585) | Output files tracking | ERD, F-16, F-17, F-21 |
| EV-016 | translator/models.py | DatasetImportBatch (lines 588-615) | Legacy import batch (no workflow) | ERD, F-032 |
| EV-017 | translator/models.py | SystemEventLog (lines 618-652) | System-level event logging | ERD, F-28 |
| EV-018 | translator/models.py | UserActivityLog (lines 655-675) | User action audit trail | ERD, F-28 |
| EV-019 | translator/views.py | home() (line 124-125) | Public landing page, no auth | F-01, UC-01 |
| EV-020 | translator/views.py | dashboard() (lines 128-151) | Role-scoped dashboard with validator metrics | F-05, UC-06 |
| EV-021 | translator/views.py | signup() (lines 154-163) | Registration with auto-login | F-01, UC-02, AD-02 |
| EV-022 | translator/views.py | TranslatorLoginView (lines 166-179) | Custom login with redirect context | F-02, UC-03, AD-01 |
| EV-023 | translator/views.py | translate() (lines 182-248) | Main translation page with upload form | F-06, UC-07 |
| EV-024 | translator/views.py | history() (lines 251-299) | Filterable/searchable job history | F-19, UC-09, AD-04 |
| EV-025 | translator/views.py | job_detail() (lines 302-338) | Detailed job view with completion notification | F-10, UC-10 |
| EV-026 | translator/views.py | preview() (lines 344-427) | Paginated bilingual preview with review mode | F-18, UC-11, AD-05 |
| EV-027 | translator/views.py | api_translate() (lines 430-546) | Upload API with rate limits and file validation | F-06, UC-07, AD-03 |
| EV-028 | translator/views.py | api_job_status() (lines 549-555) | Job status polling endpoint | F-20, UC-08 |
| EV-029 | translator/views.py | api_structure() (lines 558-591) | Structure JSON API | F-34, UC-08 |
| EV-030 | translator/views.py | api_preview() (lines 594-657) | Preview data API with segments | F-18 |
| EV-031 | translator/views.py | preview_image() (lines 660-682) | Secure image serving with path validation | F-16 |
| EV-032 | translator/views.py | download_job() (lines 685-719) | PDF download with format selection | F-21, UC-12, UC-13, AD-06 |
| EV-033 | translator/views.py | quick_translate() (lines 722-744) | NO AUTH - public quick translate | F-23, UC-16 |
| EV-034 | translator/views.py | health() (lines 747-756) | Staff-only health dashboard | F-26, UC-19, AD-10 |
| EV-035 | translator/views.py | validator_queue() (lines 759-770) | Permission-gated validator queue | F-25, UC-17, AD-08 |
| EV-036 | translator/views.py | validator_entry() (lines 773-788) | Validator review entry page | F-25, UC-18, AD-08 |
| EV-037 | translator/views.py | submit_correction_suggestion() (lines 791-805) | Correction submission | F-24, UC-15, AD-09 |
| EV-038 | translator/views.py | confirm_delete_job() (lines 808-817) | Delete confirmation page | F-22, UC-14 |
| EV-039 | translator/views.py | delete_job() (lines 820-868) | Soft delete with AJAX support | F-22, UC-14, AD-07 |
| EV-040 | translator/views.py | _owned_jobs_queryset() (lines 1078-1084) | Owner isolation (superuser override) | Role Audit |
| EV-041 | translator/urls.py | URL configuration (57 lines) | All route definitions | All features |
| EV-042 | translator/forms.py | DocumentUploadForm (lines 43-116) | Upload validation with magic bytes | F-06, AD-03 |
| EV-043 | translator/forms.py | SignUpForm (lines 119-124) | Registration form with optional email | F-01, AD-02 |
| EV-044 | translator/context_processors.py | role_navigation() (lines 28-38) | Template role flags | Role Audit |
| EV-045 | translator/admin.py | All ModelAdmin configs (438 lines) | Admin interface configuration | F-27 |
| EV-046 | translator/services/governance.py | review_entry() (lines 50-84) | Validator review logic | F-25, AD-08 |
| EV-047 | translator/services/governance.py | eligibility_reasons() (lines 17-38) | Runtime eligibility rules | F-30 |
| EV-048 | translator/services/pipeline_service.py | PipelineService (~96KB) | Complete translation pipeline | F-07 to F-17, AD-03 |
| EV-049 | translator/services/reconstruction_service.py | ReconstructionService (~46KB) | PDF reconstruction with layout | F-15, AD-03 |
| EV-050 | translator/services/extraction_service.py | ExtractionService (~14KB) | PyMuPDF text extraction | F-07, AD-03 |
| EV-051 | translator/services/ocr_stage/ocr_service.py | OCRService (~35KB) | Tesseract OCR integration | F-08, AD-03 |
| EV-052 | translator/services/translation_dataset.py | TranslationDataset (~39KB) | Phrasebook cascade matching | F-12, AD-03 |
| EV-053 | translator/services/neural_translation_service.py | NeuralTranslationService (~11KB) | ByT5 neural fallback | F-13 |
| EV-054 | translator/management/commands/setup_governance_roles.py | ROLE_PERMISSIONS dict (22 lines) | Role definitions | Role Audit |
| EV-055 | translator/management/commands/import_language_resources.py | import command (~8KB) | Language resource import | F-29 |
| EV-056 | translator/management/commands/import_phrasebook.py | phrasebook import (~6KB) | Phrasebook CSV import | F-29 |
| EV-057 | lingokatutubo_django/settings.py | Django settings (261 lines) | System configuration | All |
| EV-058 | translator/tests.py | Main test suite (~492KB, 430+ tests) | Feature/auth/pipeline testing | Test Audit |
| EV-059 | translator/test_phase1.py | Phase 1 tests (~5KB) | Quick translate, phrasebook governance | Test Audit |
| EV-060 | translator/test_phase2.py | Phase 2 tests (~5KB) | Governance workflow | Test Audit |
| EV-061 | translator/test_phase3.py | Phase 3 tests (~5KB) | Translation safety, review persistence | Test Audit |
| EV-062 | translator/test_phase4.py | Phase 4 tests (~1KB) | Navigation role-scoping | Test Audit |
| EV-063 | static/js/app.js | Frontend JavaScript (~36KB) | PollingController, AJAX interactions | F-20, F-22 |
| EV-064 | static/css/styles.css | CSS styles (~68KB) | UI styling | All UI features |
| EV-065 | ARCHITECTURE_DIAGRAM.md | Architecture documentation (~40KB) | Outdated FastAPI/Next.js architecture description | Consistency Matrix |
| EV-066 | RUNNING_GUIDE.md | Running guide (~10KB) | Acknowledges Django migration | Consistency Matrix |
| EV-067 | LAYOUT_PRESERVATION_QA.md | Layout QA (~8KB) | Honest limitation documentation | Consistency Matrix |
| EV-068 | DATASET_MODEL_PREP.md | Dataset prep (~6KB) | Neural model experimental status | F-13 |
| EV-069 | translator/services/translation_data.json | Translation dataset (~275KB) | ~1015 phrasebook entries for runtime | F-12, F-14 |
