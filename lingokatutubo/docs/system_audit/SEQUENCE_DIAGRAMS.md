# System Sequence Diagrams

This document outlines the critical interactions in the LingoKatutubo system through sequence diagrams.

## SD-01: Document Upload and Processing

```mermaid
sequenceDiagram
    participant U as User
    participant B as Browser (app.js)
    participant S as Django Server (views.py)
    participant DB as Database
    participant W as Background Worker (pipeline_service.py)
    participant T as Tesseract OCR

    U->>B: Selects file, clicks "Start Translation"
    B->>B: Client-side validation (extension check)
    B->>S: POST /translate/upload/ (multipart form with CSRF token)
    S->>S: Check auth (api_login_required)
    S->>S: Check active jobs < 2
    S->>S: Check hourly uploads < 5
    S->>S: Validate form (extension, size, content-type, signature)
    S->>DB: Create TranslationJob (status=queued)
    S->>DB: Save file to MEDIA_ROOT/jobs/{id}/
    S->>DB: Create UploadedDocument
    S->>DB: Create UserActivityLog, SystemEventLog
    S->>W: Dispatch background job (thread/celery)
    S->>B: 202 Accepted JSON {job_id, status_url}
    B->>B: Start PollingController
    
    loop Polling (every few seconds)
        B->>S: GET /translate/status/{id}/
        S->>DB: Fetch TranslationJob
        S->>B: JSON {status, progress, phase}
        B->>B: Update progress bar
    end
    
    W->>W: Phase 1 - Detect document type
    W->>DB: Update job progress 10%
    W->>W: Phase 2 - Extract text (PyMuPDF/Tesseract)
    opt if scanned
        W->>T: OCR
        T-->>W: OCR text + confidence
    end
    W->>DB: Create DocumentPage, OCRResult records
    W->>DB: Update job progress 50%
    W->>W: Phase 3 - Translate (phrasebook cascade)
    W->>DB: Read PhrasebookEntry / translation_data.json
    W->>DB: Create TranslationSegment records
    W->>W: Phase 4 - Reconstruct document
    W->>W: Save translated PDF, bilingual PDF, preview PNGs
    W->>DB: Create GeneratedOutput records
    W->>DB: Update job status=completed, progress=100%
    
    B->>S: GET /translate/status/{id}/ (final poll)
    S->>B: JSON {status: 'completed', can_preview, can_download}
    B->>B: Show Preview/Download buttons
```

- **Participants**: User, Browser (app.js), Django Server (views.py), Background Worker (pipeline_service.py), Tesseract OCR, Database
- **Trigger**: User selects a file and clicks "Start Translation"
- **Preconditions**: User is logged in. System is accepting jobs.
- **Error Paths**: Invalid file extension/size, API auth failure, active jobs >= 2 limit reached, hourly uploads >= 5 limit reached, OCR failure.
- **Evidence**: EV-001 (views.py), EV-002 (pipeline_service.py)

---

## SD-02: Bilingual Preview Loading

```mermaid
sequenceDiagram
    participant U as User
    participant B as Browser
    participant S as Server
    participant DB as Database
    participant FS as File System

    U->>B: Click "Preview Bilingual"
    B->>B: Show loading overlay ("Preparing bilingual preview...")
    B->>S: GET /translate/job/{id}/preview/
    S->>S: Check auth, check ownership
    S->>DB: Load TranslationJob, TranslationSegments
    S->>S: Paginate segments (25/page)
    S->>B: Render preview.html template
    B->>S: GET /translate/preview-image/{id}/original_page_1.png
    S->>FS: Read image file (path validation)
    S->>B: FileResponse (image/png)
    B->>B: Render side-by-side preview
```

- **Participants**: User, Browser, Server, File System
- **Trigger**: User clicks "Preview Bilingual"
- **Preconditions**: TranslationJob is completed, and user owns the job.
- **Error Paths**: Job not found, not authorized, image file missing on disk.
- **Evidence**: EV-003 (views.py), EV-004 (preview.html)

---

## SD-03: User Login

```mermaid
sequenceDiagram
    participant U as User
    participant B as Browser
    participant S as Server
    participant DB as Database

    U->>B: Navigate to /accounts/login/
    B->>S: GET /accounts/login/
    S->>B: Render login.html (with CSRF token)
    U->>B: Enter username + password
    B->>S: POST /accounts/login/ (form + CSRF)
    S->>DB: Authenticate credentials
    alt Authentication Success
        S->>S: Create session
        S->>B: 302 Redirect to /translate/
    else Authentication Failure
        S->>B: Render login.html with errors
    end
```

- **Participants**: User, Browser, Server, Database
- **Trigger**: User navigates to /accounts/login/ and submits credentials
- **Preconditions**: None
- **Error Paths**: Invalid credentials, account disabled.
- **Evidence**: EV-005 (accounts/views.py)

---

## SD-04: Validator Reviews Entry

```mermaid
sequenceDiagram
    participant V as Validator
    participant B as Browser
    participant S as Server
    participant DB as Database
    participant G as governance.py

    V->>B: Navigate to /governance/validator/
    B->>S: GET /governance/validator/
    S->>S: Check permission_required(review_language_entry)
    S->>DB: Query PhrasebookEntry (filtered by status)
    S->>B: Render validator_queue.html
    V->>B: Click on entry
    B->>S: GET /governance/validator/{entry_id}/
    S->>DB: Load PhrasebookEntry with revisions and reviews
    S->>B: Render validator_entry.html
    V->>B: Select decision (verify/reject/etc), enter notes
    B->>S: POST /governance/validator/{entry_id}/
    S->>G: review_entry(entry, reviewer, decision, notes)
    G->>G: Create governance_snapshot()
    G->>DB: Update PhrasebookEntry fields
    G->>DB: Create LanguageEntryReview
    S->>B: Redirect to validator_entry (with success message)
```

- **Participants**: Validator, Browser, Server, Database, governance.py
- **Trigger**: Validator clicks on an entry in the review queue and submits a review decision
- **Preconditions**: User has `review_language_entry` permission.
- **Error Paths**: Permission denied, entry not found.
- **Evidence**: EV-006 (governance.py), EV-007 (views.py)

---

## SD-05: Quick Translate (No Auth)

```mermaid
sequenceDiagram
    participant U as Any User
    participant C as Browser/Client
    participant S as Server
    participant QT as quick_translate.py

    U->>C: Enter text, select languages
    C->>S: POST /api/quick-translate/ {text, source, target}
    S->>S: NO AUTH CHECK
    S->>S: Check rate limit (30/hour via session)
    S->>S: Check text length (max 5000 chars)
    S->>S: Check request body size (max 12000 bytes)
    S->>QT: quick_translate_text(text, source, target)
    QT->>QT: Phrasebook cascade lookup
    QT->>S: TranslationResult
    S->>C: JSON {translated_text, method, confidence}
```

- **Participants**: Any User, Browser/Client, Server, quick_translate.py
- **Trigger**: User enters text and selects languages to translate using the Quick Translate feature
- **Preconditions**: Text length < 5000 chars, request body < 12000 bytes
- **Error Paths**: Rate limit exceeded (30/hour), text too long, request too large.
- **Evidence**: EV-008 (quick_translate.py)

---

## SD-06: Job Deletion (AJAX)

```mermaid
sequenceDiagram
    participant U as User
    participant B as Browser (app.js)
    participant S as Server
    participant DB as Database

    U->>B: Click "Remove" on document card
    B->>B: Show confirmation modal
    U->>B: Confirm deletion
    B->>S: POST /translate/job/{id}/delete/confirm/ (CSRF + Accept: application/json)
    S->>S: Check auth, check ownership
    S->>DB: Set is_deleted=True, deleted_at=now()
    S->>DB: Create UserActivityLog, SystemEventLog
    S->>B: JSON {success: true, redirect_url}
    B->>B: Remove card from DOM, show success toast
```

- **Participants**: User, Browser (app.js), Server, Database
- **Trigger**: User clicks "Remove" on a job and confirms
- **Preconditions**: Job belongs to user.
- **Error Paths**: Unauthorized, job not found.
- **Evidence**: EV-009 (views.py), EV-010 (app.js)

---

## SD-07: Correction Suggestion

```mermaid
sequenceDiagram
    participant U as User
    participant B as Browser
    participant S as Server
    participant DB as Database

    U->>B: Click suggest correction on preview segment
    B->>S: POST /translate/job/{id}/suggest-correction/ {segment_id, correction, explanation}
    S->>S: Check auth, check ownership
    S->>DB: Load TranslationSegment
    S->>DB: Create CorrectionSuggestion (status=pending)
    S->>B: JSON {success: true}
    
    Note over S, DB: NO reviewer workflow exists - suggestions accumulate in database
```

- **Participants**: User, Browser, Server, Database
- **Trigger**: User submits a correction suggestion on a preview segment
- **Preconditions**: Job belongs to user, TranslationSegment exists
- **Error Paths**: Unauthorized, segment not found
- **Evidence**: EV-011 (views.py)
