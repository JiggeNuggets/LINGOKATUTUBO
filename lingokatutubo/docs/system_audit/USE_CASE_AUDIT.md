# LingoKatutubo System Use Case Audit

## 1. Introduction

This document provides a comprehensive use case audit of the LingoKatutubo system. It defines the specific actors, their roles within the system, and details the interactions through a use case diagram and specification table. Evidence tags (e.g., EV-001) reference the underlying codebase elements confirming these capabilities.

## 2. Actors and Hierarchies

The system defines the following actors and role hierarchies:

1. **Guest**: An unauthenticated user interacting with public areas of the site.
2. **Authenticated User**: Any logged-in user in the system. Inherits basic authenticated permissions.
3. **Learner**: A specific Django Group with permissions geared toward learning features. Inherits from Authenticated User.
4. **Teacher**: A specific Django Group with instructional permissions. Inherits from Authenticated User.
5. **Validator**: A Django Group with `review_language_entry` permission. Inherits from Authenticated User.
6. **Administrator**: A Django Group with `manage_language_resources` permission. Inherits from Authenticated User.
7. **Staff**: A user with the `is_staff` flag set to True, granting admin interface and system health access. Inherits from Authenticated User.
8. **Superuser**: A user with the `is_superuser` flag set to True, granting overarching access. Inherits from Staff.
9. **System**: The automated background pipeline processor responsible for asynchronous tasks.

---

## 3. Use Case Diagram

The following Mermaid diagram illustrates the actors, their use cases, and relationship structures (includes, extends, and hierarchies).

```mermaid
flowchart LR
    %% Actors
    Guest([Guest])
    AuthUser([Authenticated User])
    Learner([Learner])
    Teacher([Teacher])
    Validator([Validator])
    Administrator([Administrator])
    Staff([Staff])
    Superuser([Superuser])
    System([System])

    %% Actor Hierarchies
    Learner -.-|> AuthUser
    Teacher -.-|> AuthUser
    Validator -.-|> AuthUser
    Administrator -.-|> AuthUser
    Staff -.-|> AuthUser
    Superuser -.-|> Staff

    %% Guest Use Cases
    UC01([UC-01: View Home Page])
    UC02([UC-02: Register Account])
    UC03([UC-03: Log In])
    UC05([UC-05: Reset Password])
    UC16([UC-16: Quick Translate Text])

    Guest --> UC01
    Guest --> UC02
    Guest --> UC03
    Guest --> UC05
    Guest --> UC16

    %% AuthUser Use Cases
    UC04([UC-04: Log Out])
    UC06([UC-06: View Dashboard])
    UC07([UC-07: Upload Document])
    UC08([UC-08: View Translation Status])
    UC09([UC-09: View Translation History])
    UC10([UC-10: View Job Detail])
    UC11([UC-11: Preview Bilingual Translation])
    UC12([UC-12: Download Translated PDF])
    UC13([UC-13: Download Bilingual PDF])
    UC14([UC-14: Delete Translation Job])
    UC15([UC-15: Submit Correction])

    AuthUser --> UC01
    AuthUser --> UC04
    AuthUser --> UC06
    AuthUser --> UC07
    AuthUser --> UC08
    AuthUser --> UC09
    AuthUser --> UC10
    AuthUser --> UC11
    AuthUser --> UC12
    AuthUser --> UC13
    AuthUser --> UC14
    AuthUser --> UC15
    AuthUser --> UC16

    %% Validator Use Cases
    UC17([UC-17: Review Phrasebook Entry])
    UC18([UC-18: Record Validation Decision])
    Validator --> UC17
    Validator --> UC18

    %% Staff Use Cases
    UC19([UC-19: View System Health])
    UC20([UC-20: Manage System via Admin])
    Staff --> UC19
    Staff --> UC20

    %% Administrator Use Cases
    UC27([UC-27: Import Language Resources])
    Administrator --> UC27

    %% Superuser Use Cases
    UC28([UC-28: Manage All Users' Jobs])
    Superuser --> UC28

    %% System Use Cases
    UC21([UC-21: Process Translation Job])
    UC22([UC-22: Extract Text / Perform OCR])
    UC23([UC-23: Match Translations via Phrasebook])
    UC24([UC-24: Detect Unknown Words])
    UC25([UC-25: Reconstruct Document Layout])
    UC26([UC-26: Generate Preview Images])
    
    System --> UC21
    
    %% Relationships (Includes / Extends)
    UC21 -.->|<<includes>>| UC22
    UC21 -.->|<<includes>>| UC23
    UC21 -.->|<<includes>>| UC24
    UC21 -.->|<<includes>>| UC25
    UC21 -.->|<<includes>>| UC26
    
    UC07 -.->|<<triggers>>| UC21
```

---

## 4. Use Case Specifications

| UC ID | Use Case | Primary Actor | Preconditions | Main Flow | Alternative Flow | Result | Evidence |
|---|---|---|---|---|---|---|---|
| **UC-01** | View Home Page | Guest, Authenticated | None | 1. User navigates to root URL.<br>2. System displays home page. | None | Page rendered successfully. | EV-001 (`urls.py`) |
| **UC-02** | Register Account | Guest | Must not be logged in. | 1. Guest accesses registration.<br>2. Fills form.<br>3. System creates account. | Form validation fails, error shown. | Account created. | EV-002 (`views.py`) |
| **UC-03** | Log In | Guest | Valid credentials exist. | 1. Guest enters credentials.<br>2. System authenticates.<br>3. Redirects to dashboard. | Invalid credentials, error shown. | User authenticated. | EV-002 (`views.py`) |
| **UC-04** | Log Out | Authenticated | Must be logged in. | 1. User clicks log out.<br>2. Session destroyed. | None | User logged out. | EV-002 (`views.py`) |
| **UC-05** | Reset Password | Guest | Must provide valid email. | 1. Guest requests reset.<br>2. System emails link.<br>3. Guest resets password. | Email not found. | Password reset. | EV-002 (`views.py`) |
| **UC-06** | View Dashboard | Authenticated | Must be logged in. | 1. User navigates to dashboard.<br>2. System loads role-specific view. | None | Dashboard displayed. | EV-002 (`views.py`) |
| **UC-07** | Upload Document for Translation | Authenticated | Must be logged in. | 1. User uploads document.<br>2. System verifies format/size.<br>3. Job queued. | Invalid format/size rejected. | Translation Job created. | EV-003 (`pipeline_service.py`) |
| **UC-08** | View Translation Status | Authenticated | Job exists. | 1. User views job list.<br>2. System displays current status. | None | Status rendered. | EV-002 (`views.py`) |
| **UC-09** | View Translation History | Authenticated | Must be logged in. | 1. User navigates to history.<br>2. System lists past jobs. | None | History rendered. | EV-002 (`views.py`) |
| **UC-10** | View Job Detail | Authenticated | Must own the job. | 1. User selects job.<br>2. System shows detailed metadata. | Job not found/ unauthorized (404/403). | Job details shown. | EV-002 (`views.py`) |
| **UC-11** | Preview Bilingual Translation | Authenticated | Job completed. | 1. User selects preview.<br>2. System renders side-by-side view. | Generation pending. | Preview displayed. | EV-002 (`views.py`) |
| **UC-12** | Download Translated PDF | Authenticated | Job completed. | 1. User requests target PDF.<br>2. System streams file. | File missing. | PDF downloaded. | EV-002 (`views.py`) |
| **UC-13** | Download Bilingual PDF | Authenticated | Job completed. | 1. User requests bilingual PDF.<br>2. System streams file. | File missing. | PDF downloaded. | EV-002 (`views.py`) |
| **UC-14** | Delete Translation Job | Authenticated | Must own the job. | 1. User requests deletion.<br>2. System removes job and files. | Unauthorized. | Job deleted. | EV-002 (`views.py`) |
| **UC-15** | Submit Correction Suggestion | Authenticated | Must own the job. | 1. User flags error.<br>2. Submits proposed fix.<br>3. System logs suggestion. | Validation failure. | Suggestion logged. | EV-002 (`views.py`) |
| **UC-16** | Quick Translate Text | Any (No Auth) | None | 1. User enters text.<br>2. System returns translation. | API limits reached. | Text translated. | EV-002 (`views.py`) |
| **UC-17** | Review Phrasebook Entry | Validator | Has `review_language_entry`. | 1. Validator views pending entries. | None | Entries listed. | EV-002 (`views.py`) |
| **UC-18** | Record Validation Decision | Validator | Has `review_language_entry`. | 1. Validator approves/rejects.<br>2. System updates state. | None | State updated. | EV-002 (`views.py`) |
| **UC-19** | View System Health | Staff | `is_staff` = True. | 1. Staff accesses health endpoint.<br>2. System returns metrics. | 403 Forbidden. | Metrics shown. | EV-002 (`views.py`) |
| **UC-20** | Manage System via Admin | Staff | `is_staff` = True. | 1. Staff accesses Django admin. | 403 Forbidden. | Admin rendered. | EV-001 (`urls.py`) |
| **UC-21** | Process Translation Job | System | Job queued by UC-07. | 1. System initiates pipeline.<br>2. Executes sub-tasks.<br>3. Marks complete. | Pipeline failure (marks as error). | Job processed. | EV-003 (`pipeline_service.py`) |
| **UC-22** | Extract Text / Perform OCR | System | Job processing active. | 1. System parses PDF.<br>2. Extracts text/runs OCR. | Document unreadable. | Text extracted. | EV-003 (`pipeline_service.py`) |
| **UC-23** | Match Translations via Phrasebook | System | Text extracted. | 1. System looks up phrases.<br>2. Applies translations. | None | Text translated. | EV-003 (`pipeline_service.py`) |
| **UC-24** | Detect Unknown Words | System | During translation match. | 1. System flags untranslated tokens.<br>2. Logs for later review. | None | Unknowns logged. | EV-003 (`pipeline_service.py`) |
| **UC-25** | Reconstruct Document Layout | System | Translation matched. | 1. System aligns translated text to original bounding boxes. | Layout failure. | PDF generated. | EV-003 (`pipeline_service.py`) |
| **UC-26** | Generate Preview Images | System | Job completed. | 1. System converts PDF pages to images for web preview. | Image generation fails. | Images created. | EV-003 (`pipeline_service.py`) |
| **UC-27** | Import Language Resources | Administrator | `manage_language_resources`. | 1. Admin runs CLI command.<br>2. System imports CSV/JSON. | File format error. | Resources imported. | EV-004 (`management/commands`) |
| **UC-28** | View/Manage All Jobs | Superuser | `is_superuser` = True. | 1. Superuser accesses global job list. | 403 Forbidden. | Global jobs shown. | EV-002 (`views.py`) |

---

## 5. Evidence Cross-Reference
* **EV-001**: URL configurations mapping endpoints to functional views (`urls.py`).
* **EV-002**: View controllers handling HTTP requests, enforcing access control, and invoking domain logic (`views.py`).
* **EV-003**: Background pipeline processor orchestrating OCR, translation, layout reconstruction, and status management (`pipeline_service.py`).
* **EV-004**: Administrative CLI utilities for bulk operations and maintenance (`management/commands/`).
