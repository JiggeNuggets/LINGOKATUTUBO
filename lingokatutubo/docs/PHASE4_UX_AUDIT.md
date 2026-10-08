# Phase 4 UX audit

Audit date: 2026-08-04. This describes the Django application before Phase 4 interface changes. API compatibility aliases are intentionally not navigation destinations.

## Page and route inventory

| Page/route | Role and primary task | Secondary actions/data | States and risks |
|---|---|---|---|
| `/` Home | Public; understand service | Sign in, translate | Clear entry but uses Home rather than task-oriented dashboard. |
| `/accounts/signup/`, `/accounts/login/`, `/accounts/logout/` | Public/authenticated; account access | Safe redirect | Form errors are present; login is not a role landing page. |
| `/translate/` | Authenticated; upload document | Choose language/OCR options | Limitations and copy choices are split across later pages. |
| `/translate/upload/` and `/api/translate/` | Authenticated JSON upload | Starts private job | Safe errors; API-only loading/error state. |
| `/translate/history/` | Owner; find past jobs | Preview/delete/download via cards | No role-specific review grouping. |
| `/translate/job/<id>/` | Owner; monitor job | Retry/status, preview/download | Quality information is technical and fragmented. |
| `/translate/job/<id>/preview/` | Owner; inspect output | Download, manifest, correction suggestion | Learner/reviewer modes exist but copy distinctions are not explicit. |
| `/translate/job/<id>/download/` | Owner; download translated artifact | — | One generic download; no clean/teacher/validator choice. |
| `/translate/job/<id>/delete/…` | Owner; delete job | Confirm deletion | Safe confirmation; lifecycle policy is unclear. |
| `/translate/status/…`, `/structure/…`, `/preview-data/…`, `/preview-image/…` | Owner JSON/media | Progress/preview data | Server ownership checks exist; not UI navigation. |
| `/translate/review-manifest/…` | Owner; detailed CSV review | — | Private but its purpose needs explanation. |
| `/translate/job/<id>/suggest-correction/` | Owner; submit correction | Source/translation context | Needs visible status workflow. |
| `/health/` | Staff; operational health | Service state | Correctly staff-protected, not dashboard-integrated. |
| `/governance/validator/` | Validator; review language entries | Queue | Document/OCR/unknown-term queues are absent. |
| `/governance/validator/<id>/` | Validator; review governed entry | Revisions/decision | Immutable history exists; no unified queues. |
| `/admin/` | Staff/admin; Django administration | Models/imports | Protected but not task-guided. |
| Password-reset routes | Public/authenticated recovery | Email flow | Standard Django states. |

## Navigation and terminology audit

The current primary navigation is `Home`, `Translate`, authenticated `History`, and staff-only `Health`/`Admin`. It does not expose validator queues to validators, nor distinguish teacher workflows from learner workflows. Hidden navigation is not a security control: route decorators and ownership checks are the existing enforcement and must remain so.

Normalize public labels to **Bagobo-Tagabawa language**, **source language**, **target language**, **needs validation**, **original text retained**, **clean learner copy**, **teacher review copy**, and **validator review copy**. Do not use “dialect”; do not choose an unapproved autonym.

## Journey audit

1. Learner translation: sign in → Translate → upload/options → job status → Preview → generic download or review manifest → optional correction. Gaps: privacy/OCR/uncertainty notices are dispersed; no dashboard or copy explanation.
2. Teacher translation/correction: same as learner. Gaps: no teacher queue, correction status, or teacher-copy choice.
3. Validator language review: direct validator queue → entry detail → decision/revision. Gaps: unknown terms, OCR corrections, conflicts and duplicates are not unified.
4. Validator document review: only owner preview/review manifest exists. Gap: no assigned document-review queue.
5. Administrator governance: staff admin/health plus management commands. Gap: operational/import/governance decisions are not a coherent dashboard.
6. History/deletion: History → job detail → confirmation → soft deletion. Ownership enforcement is clear; empty state and retention explanation need clearer wording.

## Cross-cutting issues and acceptance targets

The current templates use semantic landmarks and live progress regions, but tables/previews need clearer mobile behavior and review markers must always have text. Errors must continue to avoid file paths, raw OCR content, traces, and internal identifiers. Phase 4 should add role-aware navigation and dashboards, a public terminology reference, result summaries and correction status without changing language-resource approval or document ownership.
