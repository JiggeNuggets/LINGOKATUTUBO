# Legacy FastAPI Dependency Report

Status: Current as of Phase 1. Django is the proposed official production runtime.

## Findings

| Area inspected | Result | Evidence |
| --- | --- | --- |
| Django runtime | No Django route imports or mounts FastAPI. | `lingokatutubo_django/urls.py` includes `translator.urls`. |
| Django frontend | No Django template or static JavaScript calls the FastAPI service. | The live pages use Django URL names and same-origin `/translate/` routes. |
| Background processing | Django uses `translator.services.task_runner`, not `backend/main.py`. | `translator/services/task_runner.py`. |
| Deployment configuration | No Dockerfile, Procfile, or compose file declares FastAPI. | Repository top-level inspection during Phase 1. |
| Environment variables | `LEGACY_API_CORS_ORIGINS` is used only by the FastAPI app. | `backend/main.py`. |
| Automated tests | Backend tests exercise legacy modules directly; Django tests exercise Django services. | `backend/test_*.py`, `translator/tests.py`. |
| Documentation | Historical architecture documents describe FastAPI/Next.js target paths. | `ARCHITECTURE_DIAGRAM.md`, `IMPLEMENTATION_GUIDE.md`. |
| External clients | Not verifiable from repository evidence. | Requires maintainer confirmation. |

## Retirement plan

1. Keep `backend/` intact during Phase 1; label it legacy in current-state documentation.
2. Do not expose or deploy `backend/main.py` in production.
3. Confirm that no external client uses its routes before removal.
4. Preserve its tests as migration references until the official Django smoke suite covers the equivalent behavior.
5. In a later approved change, move legacy code to an archival location or remove it in a dedicated, reversible release.

Rollback: remove the legacy label and restore the previous deployment only after a documented security review. No FastAPI files are deleted by this report.
