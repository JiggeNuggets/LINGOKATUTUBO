# Translation Resources

Translation Resources is an administrator-only, routine maintenance surface for the canonical `PhrasebookEntry` model. It intentionally does not expose validator decisions, provenance controls, access restrictions, or runtime approval controls.

```text
Administrator
      ↓
Translation Resources
      ↓
Central Matching Service (TranslationDataset)
      ↓
Document Translation / Quick Translation / Match Tester
```

## Runtime modes

`TRANSLATION_DATA_MODE` is explicit:

- `development_unverified` (default) retains the existing JSON/CSV/corpus loading path as rollback.
- `development_resources` uses **only active `PhrasebookEntry` records**. It does not mix database entries with legacy JSON/CSV/corpus data.
- `verified_only` uses only governed, verified, runtime-approved records and fails closed when none qualify. It does not fall back to either development source.

The current default remains `development_unverified`. The database-backed mode has **not** been promoted because the reconciliation found 611 unique normalized legacy-only corpus keys. See [the parity report](TRANSLATION_RESOURCE_PARITY_REPORT.md) for the count methodology, classification, matching results, and rollback gate.

Document translation and Quick Translate both use the shared `TranslationDataset` service. Changing a resource through the UI clears that process cache; no document translation text is rewritten.

## Resource manager workflow

Users need `translator.manage_language_resources` (or superuser status) for every resource route. Normal users, teachers, and validators without that permission receive a server-side denial.

Add and edit expose only Bagobo-Tagabawa, English, Filipino, Cebuano, entry type, category, source, notes, and active status. Active rows need at least two language values. Exact duplicates are blocked; normalized duplicates and conflicting translations are warnings and are never automatically merged or overwritten. Ordinary saves continue to create `PhrasebookEntryRevision` records.

Imports accept CSV or JSON and always run a dry preview first. Confirmation creates a `LanguageResourceImportBatch`; valid new rows are inserted, while duplicates, conflicts, and incomplete rows are skipped and recorded as issues. Exports contain only the routine resource fields and can be active-only (default) or all records.

The Match Tester uses `development_resources` regardless of the current document mode so it can inspect active database resources safely. It reports match metadata and candidate scores. Fuzzy results remain review-required suggestions.

## Legacy Resource Staging

`Legacy Resource Staging` is an administrator-only review surface for the legacy-only cleaned-corpus rows. It is separate from Validator governance and never changes a resource merely by being viewed, filtered, or marked with a staging decision. Administrators can select technically ready rows for a future import, but a separate confirmation is required. Confirmed imports preserve the original text, `legacy_corpus_csv` origin, row reference, ordinary revision history, and duplicate protection; they are not marked linguistically verified.

Current staging coverage is 610 `READY_FOR_ADMIN_REVIEW` rows and one `CONFLICT` requiring a human decision. The database covers 1,018 of 1,629 unique normalized legacy resource keys (62.49% resource coverage, not translation accuracy). The current default remains `development_unverified`; see the parity report for the conflict and cutover status.

## Parity before switching document runtime

Do not set `TRANSLATION_DATA_MODE=development_resources` as the normal document source until the following comparisons pass against the legacy source for each supported language pair: exact match, normalized match, phrase match, segmented match, fuzzy match, unknown fallback, and source/target language alias handling. Retain `development_unverified` as rollback until the suite demonstrates accepted parity and the known record-count difference is resolved or explicitly accepted.

Resource edits are cache-safe: routine add, edit, activate/deactivate, and confirmed import operations invalidate the in-process dataset cache. The next lookup reloads the selected explicit resource mode; changing the environment-selected default still requires an application restart.
