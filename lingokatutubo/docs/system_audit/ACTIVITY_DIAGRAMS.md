# Activity Diagrams

This document contains activity diagrams for the major workflows within the LingoKatutubo system.

## AD-01: User Authentication (Login)

```mermaid
flowchart TD
    Start((Start)) --> Visit[User visits login page]
    Visit --> EnterCreds[Enters credentials]
    EnterCreds --> Submit[Submits form]
    Submit --> Validate{System validates credentials}
    Validate -- Valid --> Success[Login successful]
    Success --> Redirect[Redirect to /translate/]
    Validate -- Invalid --> Fail[Show error message]
    Fail --> Visit
    Redirect --> End((End))
```

*   **Actors:** User, System
*   **Preconditions:** User has an existing account.
*   **Trigger:** User navigates to the login page.
*   **Main Process:** User inputs username and password -> System validates against DB -> Upon success, session is created and user is redirected to the main application.
*   **Error Paths:** Incorrect username or password results in an error message, prompting the user to try again.
*   **Final Output:** Authenticated session, redirection to `/translate/`.
*   **Evidence:** `views.py:166-179` (TranslatorLoginView), `registration/login.html`

## AD-02: User Registration

```mermaid
flowchart TD
    Start((Start)) --> Visit[Guest visits signup page]
    Visit --> FillForm[Fills form: username, password x2, optional email]
    FillForm --> Submit[Submits form]
    Submit --> Validate{System validates form}
    Validate -- Invalid --> Fail[Show validation errors]
    Fail --> FillForm
    Validate -- Valid --> Create[Creates user]
    Create --> AutoLogin[Auto-login user]
    AutoLogin --> Redirect[Redirect to /translate/]
    Redirect --> End((End))
```

*   **Actors:** Guest, System
*   **Preconditions:** None.
*   **Trigger:** Guest navigates to the registration page.
*   **Main Process:** Guest provides required details -> System applies Django password validators and uniqueness checks -> System creates the user -> Auto-logs in the user -> Redirects to main app.
*   **Error Paths:** Weak passwords or existing usernames trigger form errors, returning the user to the form.
*   **Final Output:** New user record, authenticated session, redirection to `/translate/`.
*   **Evidence:** `views.py:154-163`, `forms.py:119-124`

## AD-03: Document Upload and Translation Pipeline

```mermaid
flowchart TD
    Start((Start)) --> Select[User selects file]
    Select --> JSCheck{JS validation: extension}
    JSCheck -- Invalid --> JSError[Show client error]
    JSCheck -- Valid --> Upload[POST to /translate/upload/]
    Upload --> QuotaCheck{Check quotas: <2 active, <5/hour?}
    QuotaCheck -- Exceeded --> QuotaError[Show quota error]
    QuotaCheck -- OK --> FormCheck{Form validation: size, type, signature}
    FormCheck -- Invalid --> FormError[Show form error]
    FormCheck -- Valid --> InitJob[Create TranslationJob, UploadedDocument, log]
    InitJob --> StartJob[Start background job]
    
    StartJob --> Phase1[1. Detecting: Classify DIGITAL/SCANNED/HYBRID]
    Phase1 --> Phase2[2. Extracting: PyMuPDF / Tesseract / Both]
    Phase2 --> Phase3[3. Translating: Cascade lookup]
    Phase3 --> Phase4[4. Reconstructing: Redact & draw text]
    Phase4 --> Phase5[5. Preview Gen: PNG images]
    Phase5 --> Phase6[6. Bilingual Output: Alternating pages PDF]
    Phase6 --> Complete[7. Complete: Update status]
    
    Complete --> UserPolls{Frontend polling /status/}
    UserPolls -- Polling --> ShowOptions[Show preview/download options]
    
    StartJob -. Failure .-> JobFail[Set status=failed, log error]
    JobFail --> GenericError[Show generic error to user]
    
    ShowOptions --> End((End))
    GenericError --> End
```

*   **Actors:** User, System, Background Worker (Thread/Celery)
*   **Preconditions:** User is authenticated.
*   **Trigger:** User selects a file and clicks upload.
*   **Main Process:** 
    1. Client and server validation of the uploaded file.
    2. Quota verification.
    3. Job initialization and database record creation.
    4. Execution of the background pipeline (Detect -> Extract -> Translate -> Reconstruct -> Preview -> Output).
    5. Frontend polling for completion.
*   **Error Paths:** File validation failures, quota exceedance, or pipeline processing errors. Pipeline errors show generic messages to users but log technical details for staff.
*   **Final Output:** Completed translation job, preview images, output PDF.
*   **Evidence:** `views.py:430-546`, `pipeline_service.py`, `reconstruction_service.py`

## AD-04: Translation History Management

```mermaid
flowchart TD
    Start((Start)) --> Visit[User visits /translate/history/]
    Visit --> Query[System queries owned, non-deleted jobs]
    Query --> Render[Render history cards]
    Render --> Filter{User applies filter?}
    Filter -- Status --> FilterStatus[Filter by status dropdown]
    Filter -- Search --> FilterSearch[Filter by search text]
    FilterStatus --> Display[Display filtered results]
    FilterSearch --> Display
    Filter -- None --> Display
    Display --> End((End))
```

*   **Actors:** User, System
*   **Preconditions:** User is authenticated and has previously uploaded documents.
*   **Trigger:** User navigates to the history page.
*   **Main Process:** System retrieves active jobs for the user -> Applies any selected status or text filters -> Displays the results.
*   **Error Paths:** None (empty results are displayed normally).
*   **Final Output:** Filtered list of translation jobs.
*   **Evidence:** `views.py:251-299`

## AD-05: Bilingual Preview

```mermaid
flowchart TD
    Start((Start)) --> Click[User clicks Preview button]
    Click --> CheckReady{Check can_preview: status==completed}
    CheckReady -- No --> NotReady[Redirect with message]
    CheckReady -- Yes --> Load[Load segments, pages, images]
    Load --> Paginate[Paginate segments 25/page]
    Paginate --> Display[Display side-by-side original/translated]
    Display --> End((End))
```

*   **Actors:** User, System
*   **Preconditions:** Job status is 'completed'.
*   **Trigger:** User requests to preview a specific translation job.
*   **Main Process:** System verifies job status -> Loads translation segments and preview images -> Paginates segments -> Renders side-by-side comparison.
*   **Error Paths:** Requesting preview for a non-completed or non-existent job results in a redirect or error.
*   **Final Output:** Bilingual preview interface.
*   **Evidence:** `views.py:344-427`, `preview.html`

## AD-06: Download Translated PDF

```mermaid
flowchart TD
    Start((Start)) --> Click[User clicks Download]
    Click --> CheckAccess{Check can_download & format}
    CheckAccess -- Invalid --> FailAccess[Redirect with error]
    CheckAccess -- Valid --> Resolve[Resolve file path]
    Resolve --> CheckExists{Verify file exists & in job dir}
    CheckExists -- Missing --> FailMissing[Redirect with error]
    CheckExists -- Exists --> Serve[Serve as attachment]
    Serve --> End((End))
```

*   **Actors:** User, System
*   **Preconditions:** Job status is 'completed'.
*   **Trigger:** User requests to download the translated or bilingual PDF.
*   **Main Process:** System verifies permissions and job status -> Resolves file path safely -> Serves the file as a download attachment.
*   **Error Paths:** Invalid access, missing file, or path traversal attempts result in errors/redirects.
*   **Final Output:** Downloaded PDF file.
*   **Evidence:** `views.py:685-719`

## AD-07: Job Deletion (Soft Delete)

```mermaid
flowchart TD
    Start((Start)) --> Click[User clicks Remove]
    Click --> Confirm[Show confirm page or JS modal]
    Confirm --> Submit[POST to /delete/confirm/]
    Submit --> CheckOwn{Verify ownership}
    CheckOwn -- Fail --> Error[Access denied]
    CheckOwn -- Pass --> SoftDel[Set is_deleted=True, deleted_at=now]
    SoftDel --> Log[Log activity]
    Log --> Return[Return JSON or redirect]
    Return --> End((End))
```

*   **Actors:** User, System
*   **Preconditions:** User owns the job.
*   **Trigger:** User confirms deletion of a job.
*   **Main Process:** System verifies ownership -> Performs soft deletion (flags record instead of removing data) -> Logs the action -> Returns success response.
*   **Error Paths:** Attempting to delete another user's job fails ownership check.
*   **Final Output:** Soft-deleted job record.
*   **Evidence:** `views.py:808-868`

## AD-08: Validator Review

```mermaid
flowchart TD
    Start((Start)) --> Visit[Validator visits /governance/validator/]
    Visit --> CheckPerm{Check review_language_entry}
    CheckPerm -- Denied --> Error[Access Denied]
    CheckPerm -- Granted --> ViewList[View filtered list of PhrasebookEntries]
    ViewList --> Select[Select entry]
    Select --> ViewDetails[View details, revisions, past reviews]
    ViewDetails --> Submit[Submit decision: verify/reject/restrict/duplicate/request_review with notes]
    Submit --> Update[governance.py: update entry status, create LanguageEntryReview]
    Update --> End((End))
```

*   **Actors:** Validator, System
*   **Preconditions:** User has appropriate validator permissions.
*   **Trigger:** Validator selects a dictionary entry for review.
*   **Main Process:** Validator views entry details and history -> Submits a review decision -> System updates entry status and logs the review.
*   **Error Paths:** Insufficient permissions block access.
*   **Final Output:** Updated entry status, new review record.
*   **Evidence:** `views.py:759-788`, `governance.py:50-84`

## AD-09: Correction Suggestion

```mermaid
flowchart TD
    Start((Start)) --> View[User viewing preview page]
    View --> Click[Clicks suggest correction on a segment]
    Click --> Fill[Fills suggestion & explanation]
    Fill --> Submit[POST to submit suggestion]
    Submit --> Create[Create CorrectionSuggestion with status=pending]
    Create --> End((End))
```

*   **Actors:** User, System
*   **Preconditions:** User is viewing a translation preview.
*   **Trigger:** User submits a correction for a specific segment.
*   **Main Process:** System receives the suggested text and explanation -> Creates a pending correction record for review.
*   **Error Paths:** Invalid segment ID or empty input.
*   **Final Output:** Pending `CorrectionSuggestion` record.
*   **Evidence:** `views.py:791-805`

## AD-10: System Health Check (Staff)

```mermaid
flowchart TD
    Start((Start)) --> Visit[Staff visits /health/]
    Visit --> CheckPerm{Check staff status}
    CheckPerm -- Denied --> Error[Access Denied]
    CheckPerm -- Granted --> RunChecks[Run parallel checks]
    
    RunChecks --> DB[Check DB]
    RunChecks --> Redis[Check Redis/Celery]
    RunChecks --> Tesseract[Check Tesseract & OCR langs]
    RunChecks --> Media[Check Media writability]
    RunChecks --> Model[Check Translation Dataset & Neural Model]
    
    DB & Redis & Tesseract & Media & Model --> Aggregate[Aggregate Results]
    Aggregate --> Stats[Calculate job counts: queued, processing, retrying, stale]
    Stats --> Display[Display status grid]
    Display --> End((End))
```

*   **Actors:** Staff, System
*   **Preconditions:** User is authenticated as staff.
*   **Trigger:** Staff member navigates to the health dashboard.
*   **Main Process:** System verifies permissions -> Executes multiple subsystem checks (database, cache, OCR engines, filesystem, models) -> Aggregates operational statistics -> Renders comprehensive health dashboard.
*   **Error Paths:** Insufficient permissions block access.
*   **Final Output:** System health dashboard.
*   **Evidence:** `views.py:747-756`, `871-1058`
