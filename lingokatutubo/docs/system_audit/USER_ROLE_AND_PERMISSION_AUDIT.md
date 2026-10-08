# User Role and Permission Audit

## 1. Role-by-Role Analysis

### Guest (Unauthenticated)
*   **Assigned**: Default for non-logged-in users.
*   **Available Pages**: Home, Log In, Sign Up.
*   **Allowed Actions**: Viewing the landing page, creating an account, authenticating. API access to `/api/quick-translate/` (due to missing authorization check).
*   **Restricted Actions**: Access to Dashboard, document translation, translation history, admin pages, validator queues.
*   **Data CRUD**: Cannot create, read, update, or delete authenticated resources.
*   **Authorization Evidence**: [EV-ROLE-001] Missing `@login_required` on `quick_translate` (`views.py:722-744`). [EV-ROLE-002] `base.html` navigation for unauthenticated users.

### Authenticated User (Base)
*   **Assigned**: Successfully logged in via Django auth.
*   **Available Pages**: Home, Dashboard, Translate Document, Translation History.
*   **Allowed Actions**: Translating documents, viewing own translation history.
*   **Restricted Actions**: Viewing other users' jobs, validating entries, accessing health/admin pages.
*   **Data CRUD**: Create and read own `translationjob` entries.
*   **Authorization Evidence**: [EV-ROLE-003] Document views protected by `@login_required`. [EV-ROLE-004] Owner filtering via `_owned_jobs_queryset` (`views.py:1078-1084`).

### Learner
*   **Assigned**: Added to "Learner" group.
*   **Available Pages**: Same as Authenticated.
*   **Allowed Actions**: Same as Authenticated, plus permissions defined in `ROLE_PERMISSIONS`.
*   **Restricted Actions**: Validation, administration.
*   **Data CRUD**: `view_translationjob`, `add_correctionsuggestion`, `view_correctionsuggestion`.
*   **Role-Specific Workflows**: Can submit correction suggestions.
*   **Authorization Evidence**: [EV-ROLE-005] Defined in `setup_governance_roles.py:5-10`.

### Teacher
*   **Assigned**: Added to "Teacher" group.
*   **Available Pages**: Same as Authenticated.
*   **Allowed Actions**: Currently identical to Learner based on `ROLE_PERMISSIONS`.
*   **Restricted Actions**: Validation, administration.
*   **Data CRUD**: `view_translationjob`, `add_correctionsuggestion`, `view_correctionsuggestion`.
*   **Role-Specific Workflows**: Expected to have higher trust than Learner, but currently undifferentiated in permissions.
*   **Authorization Evidence**: [EV-ROLE-005] Defined in `setup_governance_roles.py:5-10`.

### Validator
*   **Assigned**: Added to "Validator" group.
*   **Available Pages**: Language Review Queue, Validator Entry.
*   **Allowed Actions**: Reviewing language entries, validating translations.
*   **Restricted Actions**: System administration, managing language resources.
*   **Data CRUD**: `view_phrasebookentry`, `change_phrasebookentry`, `view_phrasebookentryrevision`, `add_languageentryreview`, `view_languageentryreview`. Custom permission: `review_language_entry`.
*   **Role-Specific Workflows**: Processing the validator queue, approving/rejecting entries.
*   **Authorization Evidence**: [EV-ROLE-006] Checked in `views.py` `dashboard` via `translator.review_language_entry` (`views.py:128-151`). [EV-ROLE-007] `@permission_required("translator.review_language_entry")` on `validator_queue` and `validator_entry` (`views.py:759, 773`).

### Administrator
*   **Assigned**: Added to "Administrator" group.
*   **Available Pages**: Admin Link, Health Link (if also staff).
*   **Allowed Actions**: Managing language resource import batches and issues.
*   **Restricted Actions**: Superuser-only system actions.
*   **Data CRUD**: `view_phrasebookentry`, `add_phrasebookentry`, `change_phrasebookentry`, `view_languageresourceimportbatch`, `add_languageresourceimportbatch`, `change_languageresourceimportbatch`, `view_languageresourceissue`. Custom permission: `manage_language_resources`.
*   **Role-Specific Workflows**: Overseeing language resource imports and system health.
*   **Authorization Evidence**: [EV-ROLE-005] Defined in `setup_governance_roles.py:5-10`. [EV-ROLE-008] Health link visibility (`base.html`, `context_processors.py:28-38`).

### Staff / Superuser
*   **Assigned**: `is_staff=True` or `is_superuser=True`.
*   **Available Pages**: Health view, Django Admin, all jobs.
*   **Allowed Actions**: Global access, viewing all translation jobs.
*   **Data CRUD**: Full access.
*   **Authorization Evidence**: [EV-ROLE-009] `@staff_member_required` on `health` (`views.py:747`). [EV-ROLE-010] `_owned_jobs_queryset` superuser check (`views.py:1078-1084`).


## 2. Role-Permission Matrix

| Feature/Resource | Guest | Authenticated | Learner | Teacher | Validator | Administrator | Staff | Superuser | Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Home / Landing** | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | [EV-ROLE-011] |
| **Sign Up / Log In** | Yes | No | No | No | No | No | No | No | [EV-ROLE-011] |
| **Quick Translate API**| Yes ⚠️ | Yes | Yes | Yes | Yes | Yes | Yes | Yes | [EV-ROLE-001] |
| **Translate Document** | No | Yes | Yes | Yes | Yes | Yes | Yes | Yes | [EV-ROLE-003] |
| **Own Translation History**| No | Yes | Yes | Yes | Yes | Yes | Yes | Yes | [EV-ROLE-004] |
| **All Translation Jobs** | No | No | No | No | No | No | No | Yes | [EV-ROLE-010] |
| **Submit Correction** | No | No | Yes | Yes | Yes | Yes | Yes | Yes | [EV-ROLE-005] |
| **Language Review Queue**| No | No | No | No | Yes | No | Yes | Yes | [EV-ROLE-007] |
| **Manage Imports** | No | No | No | No | No | Yes | Yes | Yes | [EV-ROLE-005] |
| **System Health** | No | No | No | No | No | No | Yes | Yes | [EV-ROLE-009] |

## 3. Analysis

### Navigation Visibility vs. Backend Enforcement
The application heavily relies on navigation visibility toggles using `role_navigation()` from `context_processors.py:28-38`. This exposes `is_teacher`, `is_validator`, and `is_administrator` to all templates, allowing `base.html` to conditionally render links (e.g., Language Review Queue for Validators, Admin/Health links for Administrators/Staff) [EV-ROLE-012]. 

This frontend visibility is correctly backed by backend enforcement for critical areas:
- Validator views are protected by `@permission_required("translator.review_language_entry")` (`views.py:759, 773`).
- Document views are protected by `@login_required`.
- The Health view is protected by `@staff_member_required`.
- API views use `@api_login_required` (except `quick_translate`).

### Frontend-Only Restrictions
Currently, the `dashboard` view (`views.py:128-151`) performs group checks for Teacher and Administrator, and checks for `translator.review_language_entry` for the Validator. It is crucial to ensure that any sensitive data or actions exposed on the dashboard are also protected at the corresponding form submission or API endpoints, rather than relying solely on the dashboard rendering logic.

### Missing Authorization Checks (Vulnerability)
**[EV-ROLE-001] Missing Authentication on Quick Translate API**
The `quick_translate` view (`views.py:722-744`) completely lacks `@login_required`, `@api_login_required`, or any other authentication/authorization decorator. This is a significant gap allowing unauthenticated users (Guests) to call the `/api/quick-translate/` endpoint and consume system translation APIs. This could lead to a Denial of Wallet (DoW) or resource exhaustion.

### Learner vs. Teacher Distinction
According to `setup_governance_roles.py` (lines 5-10) [EV-ROLE-005], the "Learner" and "Teacher" groups have exactly the same set of permissions assigned:
- `view_translationjob`
- `add_correctionsuggestion`
- `view_correctionsuggestion`

While the roles represent different personas, the system currently fails to technically differentiate their privileges via native permissions. Any feature intended strictly for Teachers must currently rely on group membership checks (`user.groups.filter(name='Teacher')`) rather than native Django permission checks, which breaks the standard Role-Based Access Control (RBAC) pattern in Django.

## 4. Evidence References

*   **[EV-ROLE-001]**: `translator/views.py` lines 722-744 (Missing auth decorator on `quick_translate`)
*   **[EV-ROLE-002]**: `base.html` (Unauthenticated navigation options)
*   **[EV-ROLE-003]**: `translator/views.py` (Standard document views using `@login_required`)
*   **[EV-ROLE-004]**: `translator/views.py` lines 1078-1084 (`_owned_jobs_queryset` filters jobs by `user` unless superuser)
*   **[EV-ROLE-005]**: `translator/management/commands/setup_governance_roles.py` lines 5-10 (Definition of `ROLE_PERMISSIONS`)
*   **[EV-ROLE-006]**: `translator/views.py` lines 128-151 (`dashboard` view role and permission checks)
*   **[EV-ROLE-007]**: `translator/views.py` lines 759, 773 (`validator_queue` and `validator_entry` `@permission_required` decorators)
*   **[EV-ROLE-008]**: `translator/context_processors.py` lines 28-38 (`role_navigation` exposing roles to templates)
*   **[EV-ROLE-009]**: `translator/views.py` line 747 (`health` view `@staff_member_required` decorator)
*   **[EV-ROLE-010]**: `translator/views.py` lines 1078-1084 (Superusers bypass owner filtering)
*   **[EV-ROLE-011]**: General routing behavior for `home` and `signup` (Publicly accessible)
*   **[EV-ROLE-012]**: `base.html` template analysis (Conditional rendering based on `role_navigation`)
*   **[EV-ROLE-013]**: `PhrasebookEntry.Meta.permissions` (Definition of `review_language_entry`, `approve_runtime_entry`, `manage_language_resources`)
