# Phase 6 Translation Loading Research

## Current behavior

The upload page submitted through `fetch`, then kept users on that page while showing queue, worker, stage, percentage, background, validation, and privacy messages. The job page repeated the internal timeline, current step, numerical progress, network state, and metadata. Django creates a `TranslationJob`, dispatches it through the configured background runner, and the browser polls the owner-scoped status endpoint.

The persisted `progress` values are pipeline stage checkpoints (for example, a fixed value when extraction starts), not measured completion. They must not be displayed as a user-facing percentage.

## Sources reviewed

- [WAI-ARIA 1.2](https://www.w3.org/TR/wai-aria/) defines the polite `status` live-region role and explains `aria-busy` while a region is being updated.
- [MDN: `<progress>`](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/progress) documents labelled native progress elements and the indeterminate form created by omitting `value`.
- [MDN: ARIA progressbar](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles/progressbar_role) says indeterminate progressbars must not expose `aria-valuenow`.
- [web.dev: Animation and motion](https://web.dev/learn/accessibility/motion) recommends honouring `prefers-reduced-motion` and avoiding unnecessary infinite movement.
- [W3C WCAG 2.2.2](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html) covers movement and auto-updating content; this implementation keeps motion small, purpose-specific, and disabled for reduced-motion preferences.

## Pattern comparison

| Pattern | Result |
| --- | --- |
| A. Full-screen modal until complete | Strong initial confirmation, but traps the user on an operation that is intentionally background work. Poor navigation freedom and weak failure recovery. Rejected. |
| B. Brief submission overlay then compact status card | Confirms the click, disables duplicates during upload/job creation, then redirects to an owner-scoped, pollable status page the user can leave. The card keeps technical details optional. Selected. |
| C. Inline progress only | Allows navigation, but is too easy to miss after activation and does not make submission acknowledgement unambiguous. Rejected. |

## Selected design

Pattern B is implemented. A centered overlay appears only after native browser validation succeeds and while the upload request/job creation is pending. It visibly contains only the animated document icon and “Translating”; its additional explanation is screen-reader-only. On a 202 response the browser navigates to the accepted job. The job page has one compact centered card whose primary word is Translating, Ready, Failed, or Review.

## Accessibility and responsive requirements

- The overlay and job state use a polite `role="status"` live region; normal progress is never assertive.
- The form/job card use `aria-busy` for active work.
- The native `<progress>` is indeterminate by default because progress is not reliably quantitative. If the backend later supplies `metadata.reliable_progress_percent`, the API exposes `progress_available` and the client sets the native value.
- The Details controls are semantic `<details>/<summary>` controls and retain the site focus treatment.
- The SVG is decorative; the text status is the accessible state.
- `prefers-reduced-motion: reduce` stops the looping language-line animation but preserves the icon and status information.
- The overlay uses `inset: 0`, bounded content width, padding, and overflow handling; the job card uses a responsive `min()` width and no horizontal scrolling.

## Error handling

Native validation runs before the overlay. Duplicate submissions are ignored while one request is pending. A rejected request, invalid file, CSRF/network failure, or server error hides the overlay, removes `aria-busy`, restores the Start Translation button, keeps selected controls, and shows the safe inline error. Job/worker failures are shown as safe failure guidance with a return-to-upload action; raw diagnostics remain staff-only.

## Implementation files

- `translator/templates/translator/translate.html`
- `translator/templates/translator/job_detail.html`
- `static/js/app.js`
- `static/css/styles.css`
- `translator/views.py`
- `translator/test_phase6_ui.py`

## Acceptance criteria

- Submission acknowledgement is immediate and duplicate-safe.
- The overlay contains no fake percentage or worker terminology.
- Status is background-safe, owner-scoped, accessible, responsive, and technical information is disclosed only on request.
- Only backend-declared reliable progress can receive a numeric value.
- Complete, failed, and partial states have distinct, safe actions.
- No language records, translation logic, permissions, or job ownership rules are changed.

## Rollback

Revert the six implementation files above in one commit. No migration, database schema, language-record, or background-runner rollback is required. The former stage checkpoint fields remain intact, so a rollback does not alter queued or completed jobs.
