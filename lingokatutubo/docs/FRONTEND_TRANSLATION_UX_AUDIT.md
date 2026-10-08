# Frontend Translation UX Audit

Date: 2026-08-16  
Scope: normal-user document translation UI only. The Django translation pipeline,
resources, model configuration, data, permissions, and records are out of scope.

## A. Current problem and root cause

The observed jump is real, but it is not caused by job creation, the redirect,
or polling. It is caused by two separate loading implementations and an
incorrect job-page layout context.

1. `translator/templates/translator/translate.html` renders the submission
   overlay `#translation-submission-overlay`. `static/js/app.js` shows it in
   `setSubmissionState(true)` and redirects with `window.location.assign(...)`
   after the upload API returns a job id. Navigation necessarily unloads that
   DOM, so the overlay disappears.
2. `translator/templates/translator/job_detail.html` separately renders
   `.translation-state-card` for the job page. `initStatusPage()` in
   `static/js/app.js` polls the status endpoint for this second component.
3. In `static/css/styles.css`, `.job-detail-layout` is a two-column grid:
   `200px minmax(0, 1fr)`, but the template supplies only one child:
   `.translation-state-layout`. CSS grid therefore places it in the 200px
   first column. Its `justify-content: center` centers the state card only in
   that narrow column, and the card's `width: min(100%, 600px)` resolves to
   that column's width. Its `min-height: 310px` and `margin: 32px 0` make the
   misplaced component feel unnecessarily large and low on the page.

This is a template/CSS grid-structure problem. It is not an absolute/fixed
positioning failure, status mapping problem, duplicate polling timer, or
translation-backend issue.

## B. Files responsible before the fix

| Concern | File(s) | Evidence |
| --- | --- | --- |
| Upload submission state | `translator/templates/translator/translate.html`, `static/js/app.js` | Overlay is revealed before the AJAX upload and unloaded by the redirect. |
| Job processing state | `translator/templates/translator/job_detail.html`, `static/js/app.js` | Separate card with `data-status-poller`; polling starts for queued, processing, and retrying jobs. |
| Incorrect placement | `static/css/styles.css` | One child in a two-column job grid; internal centering is constrained to the 200px first column. |
| History/recent density | `translator/templates/translator/partials/_document_card.html`, `static/css/styles.css` | Cards use the same component but compact recent rows hide status and devote a separate action row to Remove. |

## C. Loading-state trace

`Translate Document` → form submit → `initUpload()` validates the file and
shows the upload overlay → `POST /translate/upload/` creates the job → JSON
returns `job_id` → `window.location.assign(job detail)` → old document and
overlay unload → job detail renders its independent card → `initStatusPage()`
starts one keyed polling controller → terminal completed/failed status stops
that controller.

Two visual loading implementations existed. They shared an SVG class but not
template markup, positioning, width, or behavior. Upload uses a fixed,
viewport-centered backdrop; job detail used a normal-flow card in an
incorrect grid column. The first disappeared because a document navigation
occurred, not because its hidden state was toggled incorrectly.

## D. Research and principles adopted

Sources consulted before implementation:

* [Atlassian spacing foundation](https://atlassian.design/foundations/grid-beta/applying-grid)
  — use a limited 8px-based space scale and consistent rhythm for repeated
  content.
* [Atlassian grid guidance](https://atlassian.design/foundations/grid-beta/applying-grid/)
  — align top-level containers to the content grid; overlays live outside it.
* [IBM Carbon spacing overview](https://carbondesignsystem.com/elements/spacing/overview/)
  — use a defined scale to control vertical rhythm and component density.
* [Material responsive layout guidance](https://m1.material.io/layout/responsive-ui.html)
  — responsive layouts require fluid content, intentional gutters, and a
  maximum width on very wide screens.
* Current document-translator UX patterns reviewed through public product
  pages/search: upload-first flow, labelled source/target controls, compact
  document history rows, non-numeric processing feedback, and completion
  actions separated from destructive controls. No branding, assets, layouts,
  or proprietary code are copied.

Adopted principles: a single reusable translating visual, an indeterminate
indicator when no trustworthy numeric progress exists, clear labelled language
controls, a bounded normal content column, compact history entries, and
content-driven breakpoints rather than desktop-only sizing.

## E. CSS and layout findings before the fix

* Existing useful tokens: `--space-1` through `--space-12`, `--container-content`,
  radii, shadows, and focus ring. They will be extended semantically rather
  than replaced.
* Significant conflict: `.translation-overlay-content, .translation-state-card`
  share large-card rules even though one is a fixed overlay and the other is
  normal flow. The later `.translation-state-card` override makes the second
  still larger (`600px`, `min-height: 310px`).
* Significant layout error: `.job-detail-layout` retains an obsolete sidebar
  column after the template removed the companion job-info panel.
* Compact recent cards hide status to avoid a collision rather than using a
  robust row layout; the visible `Remove` action receives disproportionate
  emphasis.
* Current responsive rules collapse the job grid at 900px, but cannot fix its
  desktop first-column placement.

## F. Planned targeted fix

1. Create a reusable translating-state partial used by both upload and
   processing job detail.
2. Render job processing as a fixed, non-modal status overlay with `aria-live`
   and `aria-busy`; after terminal polling, reload once to render real result
   actions rather than inventing client-side result markup.
3. Remove the obsolete job-detail grid path and oversized normal-flow loading
   card rules.
4. Use existing spacing tokens plus semantic layout tokens; compact recent and
   history cards without exposing technical details or changing backend data.
5. Add focused template/status regression tests and verify Django checks.

## G. Browser QA status before the fix

The in-app browser capability was available as a skill but no browser instance
was available in this environment. Browser QA is therefore **PENDING**. The
code path, DOM structure, and server-rendered templates will be tested with
focused Django tests; interactive browser widths require a browser-enabled
environment.

## H. Implementation completed

### Templates

* Added `translator/templates/translator/partials/_translating_state.html`.
  Both the upload submission overlay and job-detail processing overlay render
  this partial, so they use one document icon, one `Translating` label, and
  one indeterminate native progress control.
* `job_detail.html` now renders the reusable state in a fixed status overlay
  only while the job is queued, processing, or retrying. It renders a compact
  result/error banner after a terminal state; normal-user preview/download
  buttons continue to be rendered by Django's existing permission checks.
* `translate.html` now has explicit source and target labels with a guarded
  language-swap control. Auto-detect cannot be swapped into an unsupported
  target state.
* `partials/_document_card.html` now orders metadata as language direction,
  then date, and gives compact recent rows an explicit Open action.

### CSS conflicts removed and rules added

Removed:

* `.job-detail-layout { grid-template-columns: 200px minmax(0, 1fr); }` and
  its responsive reference. This was the direct cause of the left-column
  processing card.
* The shared large normal-flow rules for
  `.translation-overlay-content, .translation-state-card`, including the
  `600px` width and `310px` minimum height that made a compact processing
  state look like an oversized content card.
* The compact-card rule that hid status instead of laying filename and status
  out safely.

Added/modified:

* `.translation-processing-overlay` uses `position: fixed; inset: 0; display:
  grid; place-items: center;` and the established dialog layer. It is a live
  status region, not a dialog, because it has no required user decision or
  focus trap.
* `.translating-state` is a compact 360px maximum card with 24px padding;
  native indeterminate progress is used without a made-up percentage.
* Semantic layout tokens: `--content-max`, `--preview-content-max`,
  `--page-gutter`, `--card-padding`, `--section-gap`, `--component-gap`, and
  document-row padding tokens.
* The normal content column uses a bounded fluid width. Preview has a distinct
  wider bounded width; document forms and history do not stretch with it.
* Compact recent-card layout preserves its status badge and de-emphasizes the
  Remove action until hover/focus.

### JavaScript

`initUpload()` now enables swap only when a concrete source language is
selected and swaps only supported values. The upload POST, redirect, CSRF,
owner-scoped API, and backend response contract are unchanged.

`initStatusPage()` keeps the existing keyed polling controller and intervals.
On a completed or failed response it reloads once after 120ms, letting Django
render the real terminal state instead of synthesising sensitive actions in
JavaScript. Polling still stops on a terminal status; a temporary network
problem updates the screen-reader status with a safe instruction and retries
using the existing backoff.

### Responsive behavior and accessibility

* 1440px, 1280px, and 1024px use 24px page gutters and a 1200px normal-content
  maximum. Processing remains viewport-centred, independent of page grid.
* 768px uses 20px gutters and 20px standard card padding. The existing
  dashboard stack and navigation breakpoint at 900px remains in effect.
* 390px and 360px use 16px gutters and card padding. Source, swap, and target
  stack vertically; the swap icon rotates to indicate the vertical direction.
* Existing focus-visible treatment is reused. The processing state has
  `role="status"`, `aria-live="polite"`, `aria-atomic="true"`, and the job
  status region sets `aria-busy`. It does not misuse `role="dialog"` or trap
  focus. `prefers-reduced-motion` already disables the document-line animation.

### Actual spacing values

| Token/use | Desktop | Tablet | Mobile |
| --- | ---: | ---: | ---: |
| Page gutter | 24px | 20px | 16px |
| Normal content maximum | 1200px | 1200px | fluid within gutter |
| Preview maximum | 1440px | 1440px | fluid within gutter |
| Standard card padding | 24px | 20px | 16px |
| Recent/history document row horizontal padding | 16px | 16px | 16px |
| Recent/history document row vertical padding | 14px | 14px | 14px |
| Section gap | 32px | 32px | 32px |
| Component gap | 16px | 16px | 16px |

The compact translation dashboard intentionally keeps its existing 16px panel
override so the upload, settings, and recent-documents columns remain
productive rather than oversized.

## I. Verification

* `node --check static/js/app.js`: passed.
* `python -m compileall translator -q`: passed.
* `python manage.py check` with the project's `.venv` and local validation
  settings: passed, no issues.
* `python manage.py test translator.test_phase6_ui --verbosity 2`: passed,
  16 tests. The focused suite covers owner scoping, role visibility,
  processing/terminal templates, upload validation, polling UI contracts,
  language control labels, preview/download visibility, and Translation
  Resources compatibility.

Browser QA remains **PENDING**: the in-app browser skill was available, but no
browser instance was exposed by this environment. No browser-width result is
claimed. A browser-enabled follow-up should capture the requested 1440px,
1280px, 1024px, 768px, 390px, and 360px views and exercise upload through
completion.

## J. Remaining issue and recommended next improvement

The browser cannot retain a DOM overlay across a full document navigation, but
the two navigation stages now render the same reusable, fixed, centred status
visual rather than a centred overlay followed by a misplaced card. The next
frontend improvement should be browser-based visual regression coverage for
the six requested widths, including long filenames and actual slow document
jobs.

## K. Centered loading popup follow-up

The centred processing implementation was re-audited against the stricter
loading-popup requirements. The old inline layout was caused by the orphaned
job-detail child occupying the first `200px` column of `.job-detail-layout`,
while its internal grid only centred content inside that narrow column.

The final reusable component is
`translator/templates/translator/partials/_translating_state.html`, rendered
inside `.translation-processing-overlay` on initial upload and job detail. It
uses a CSS indeterminate bar rather than browser-native progress styling:

* popup maximum width: 360px;
* popup padding: 32px desktop, 24px at 600px and below;
* icon width: 64px–88px;
* progress width: 100% of the popup content, capped at 260px;
* backdrop: a subtle 42% deep-green dim;
* reduced motion: icon-line and progress-bar animations stop.

`initUpload()` shows the overlay only after valid submission and locks
background scrolling. `initStatusPage()` shows it immediately for `queued`,
`processing`, and `retrying` (the application's queued state is its pending
state), including after refresh. Its single keyed poller retains the existing
interval/backoff, hides the overlay and unlocks scrolling on terminal status,
then reloads once so Django renders terminal content without synthesising
permission-sensitive actions in JavaScript.

There is no dedicated check route in `translator/urls.py`. The existing
owner-scoped `job_preview` route is the completed-document inspection action.
On completion, the centred popup transforms into a success state with a check
icon, **Translation Complete**, and a primary button labelled **CHECK** only.
The CHECK link uses that existing preview URL and ownership checks. It remains
hidden for queued, processing, and failed jobs; the failed popup instead shows
Translation Failed and Try Again. Download remains available from the preview
flow, while History and Remove stay behind the terminal popup.

Follow-up verification: `node --check static/js/app.js` and `manage.py check`
passed. A 24-test focused run initially exposed a missing teacher-only review
copy action; that existing permission-scoped action was restored without
duplicating normal-user result buttons. The direct regression retest for the
teacher action, terminal CHECK action, and top action bar then passed
(3/3). Browser QA remains pending because no browser instance is available.

### Final terminal-copy correction

The successful terminal popup now uses the exact visible button label `CHECK`.
It does not say Check Word, Check Translation, Check Translated Document, or
any other expansion. The popup has a check icon and the exact heading
`Translation Complete`; its CHECK link navigates to the existing
owner-protected bilingual preview for that job. The failed terminal popup uses
an X icon, `Translation Failed`, safe generic guidance, and `Try Again`.

The terminal popup is a fixed overlay (`.translation-terminal-overlay`) just
like the processing overlay. It blocks background interaction and scrolling
without being labelled as a dialog or trapping focus. The underlying top bar
does not duplicate the CHECK action. Final terminal-copy regression tests for
successful state, failed state, and action-bar placement passed (3/3).
