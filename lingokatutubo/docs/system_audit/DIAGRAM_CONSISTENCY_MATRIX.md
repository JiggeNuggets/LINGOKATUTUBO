# Diagram and Documentation Consistency Matrix

This document provides a comprehensive comparison between the audited features, existing system diagrams, and the actual implementation state. It identifies inconsistencies, missing implementations, and documentation drifts.

## Consistency Matrix

| Requirement/Feature | Repository Evidence | ERD | Use Case | Activity Diagram | DFD | Consistency Status | Finding |
|---|---|---|---|---|---|---|---|
| **Quick Translate API** | F-23 (Code, Tests) | N/A | UC-16 | N/A | Present | Partially Consistent | Feature exists but lacks authentication checks in backend; missing from primary architecture docs. |
| **GlossaryTerm** | Model exists | Present | N/A | N/A | N/A | Missing from Implementation | Model exists but is not used in the translation pipeline; accessible only via Admin UI. |
| **DatasetImportBatch** | Model exists | Present | N/A | N/A | N/A | Missing from Implementation | Admin only; no user-facing web UI implemented. |
| **Language/LanguagePair** | Models exist | Present | N/A | N/A | N/A | Partially Consistent | Models exist and GlossaryTerm FK uses them, but translation pipeline relies on string codes. |
| **PaddleOCR** | Not Implemented | N/A | N/A | N/A | N/A | Inconsistent | Documented in ARCHITECTURE_DIAGRAM.md but not implemented (only Tesseract is wired). |
| **FastAPI/Next.js Architecture**| Django codebase | N/A | N/A | N/A | N/A | Inconsistent | Architecture docs describe FastAPI/Next.js, but system is actually a Django monolith. |
| **Neural Translation (ByT5)**| Model service | N/A | N/A | N/A | N/A | Partially Consistent | Experimental feature; partially implemented and disabled by default. |
| **Correction Suggestions**| F-24 exists | Present | N/A | N/A | N/A | Partially Consistent | User submission works, but reviewer UI/workflow is completely missing. |
| **OCR Correction** | Model exists | Present | N/A | N/A | N/A | Partially Consistent | Backend/Admin UI only; no user-facing correction workflow exists. |
| **UnknownTranslationRecord**| Model exists | Present | N/A | N/A | N/A | Partially Consistent | Dashboard shows counts for validators, but dedicated resolution workflow in validator queue is missing. |
| **`approve_runtime_entry`**| Permission code | N/A | N/A | N/A | N/A | Missing from Implementation | Permission defined in Meta but not assigned to roles in governance setup or checked in views. |
| **Notifications** | Not found | N/A | N/A | N/A | N/A | Missing from Implementation | No notification model, views, or UI exist. |
| **Data Export** | Management cmd | N/A | N/A | N/A | N/A | Missing from Implementation | Missing user-facing export; limited to admin and JSONL management commands. |
| **User Profile Management**| Not found | N/A | N/A | N/A | N/A | Missing from Implementation | No profile model, views, or templates exist. |
| **Search in translations**| File history | N/A | N/A | N/A | N/A | Missing from Implementation | Not available as a standalone feature; only filename search on History page. |

## Documentation Accuracy

The following assessment compares existing documentation files against the actual system implementation:

- **ARCHITECTURE_DIAGRAM.md**: **Inconsistent** (describes FastAPI+Next.js architecture instead of the actual Django monolith)
- **IMPLEMENTATION_GUIDE.md**: **Partially Consistent** (some described features match the implementation, others are outdated)
- **RUNNING_GUIDE.md**: **Consistent** (accurately acknowledges the Django migration)
- **LAYOUT_PRESERVATION_QA.md**: **Consistent** (accurately describes system limitations)
- **DATASET_MODEL_PREP.md**: **Consistent** (correctly marks neural models as experimental)
