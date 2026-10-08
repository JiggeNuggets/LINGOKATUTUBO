# LingoKatutubo Current-State Capabilities

Status: **Current** — Phase 1, 2026-08-02. This document supersedes conflicting runtime claims in planning documents.

## Official runtime

The proposed official production framework is **Django**. Django templates, Django authentication, Django models, and `translator.services` make up the supported web application. `backend/main.py` is a **legacy FastAPI component**; it is not part of the approved production deployment path pending external-client confirmation.

## Supported operation

- Database: PostgreSQL is the production configuration; SQLite is a local/test option.
- Uploads: PDF, DOCX, JPG/JPEG, PNG, and UTF-8 TXT, subject to the configured size limit.
- Language labels: Bagobo-Tagabawa language (`tagabawa`), English, Filipino / Tagalog (`filipino`), and Cebuano (`cebuano`). Bisaya is normalized to Cebuano, not a separate category.
- Translation: phrasebook exact/normalized lookup, segmentation, and controlled fuzzy matching. Experimental ByT5 fallback is disabled by default and always requires review.
- OCR: Tesseract for supported installed packs. Bagobo-Tagabawa language has no project OCR language pack; English fallback is warned and must be reviewed.
- Background work: development defaults to a thread; production should use Celery with Redis.
- Storage: private local `MEDIA_ROOT` storage today. Durable object storage, retention, and recovery controls remain a production requirement.

## Safety behavior

- Document jobs require authenticated ownership; previews and downloads are owner-scoped.
- Quick translation requires authenticated JSON POST with CSRF protection, size limits, and per-user rate limiting. It does not accept text in URLs.
- Unknown source text is retained. Review-required segments receive the learner-safe label: “Original text retained, translation requires validation.” A review CSV is available to the document owner.
- Current primary phrasebook: 1,028 fully populated rows. The runtime also loads 612 cleaned-corpus rows. These resources remain unverified unless explicitly approved through governance workflow.

## Known limitations

- No Bagobo-Tagabawa OCR pack is included.
- Complex-table, embedded-font, and overlapping-layout preservation are approximate.
- No production object storage, durable queue, or approved retention policy is configured in this repository.
- Existing language resources lack confirmed source owner, license, validation, and sensitivity metadata. Do not claim them as community-validated.

## Document status guide

- `CURRENT_STATE_CAPABILITIES.md`: Current.
- `ARCHITECTURE_DIAGRAM.md`, `IMPLEMENTATION_GUIDE.md`, `IMPLEMENTATION_PLAN.md`: Historical/proposed design references; verify against this document before using their runtime claims.
- `DATASET_MODEL_PREP.md`: Historical dataset/model-preparation reference; its counts may predate the 1,028-row runtime JSON.

## Reproducible Phase 1 checks

```powershell
$env:DJANGO_DEBUG='1'
$env:DJANGO_USE_SQLITE='1'
.\.venv\Scripts\python.exe manage.py test translator.test_phase1 --verbosity 2
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe scripts\create_phase1_inventory.py
```

The tests use synthetic text and do not use restricted cultural documents.
