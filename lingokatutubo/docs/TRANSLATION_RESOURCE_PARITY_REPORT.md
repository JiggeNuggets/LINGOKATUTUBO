# Translation Resource Runtime Parity Report

Date: 2026-08-10. This report is generated from the read-only `translation_resource_parity` inventory command and controlled matching matrix. No language entry was created, edited, imported, deactivated, or deleted for this analysis.

## Inventory reconciliation

| Source | Raw rows | Unique four-language keys | Unique normalized keys | Exact duplicate rows | Normalized duplicate rows |
|---|---:|---:|---:|---:|---:|
| `translation_data.json` | 1,028 | 1,020 | 1,018 | 8 | 10 |
| `cross_lingual_cleaned_v1.csv` | 612 | 612 | 611 | 0 | 1 |
| Legacy runtime total | 1,640 | 1,632 | 1,629 | 8 | 11 |
| Active `PhrasebookEntry` database | 1,018 | 1,018 | 1,018 | 0 | 0 |

Normalized four-language-key overlap is **1,018**. There are **611** legacy-only normalized keys, **0** database-only normalized keys, and **1** legacy-only key with a structural term conflict against a differently keyed database record.

### Why `1,640 / 1,018 / 611` does not subtract directly

The 1,640 value is a raw row count; the 1,018 overlap and 611 legacy-only values are unique normalized four-language keys. The legacy sources contain 11 rows that collapse under matching normalization. Therefore:

```text
1,640 raw legacy rows
− 11 normalized duplicate rows
= 1,629 unique normalized legacy keys

1,629 unique normalized legacy keys
= 1,018 overlapping keys + 611 legacy-only keys
```

The apparent difference of 622 (`1,640 − 1,018`) is one larger than 611 because it includes the 11 duplicate normalized rows rather than only distinct keys.

## Legacy-only classification and recommendation

Every legacy-only normalized key was classified structurally, not linguistically:

| Classification | Count | Recommendation | Technical reason |
|---|---:|---|---|
| `corpus_only_phrase` | 610 | `KEEP_LEGACY_ONLY` | Present only in the cleaned CSV corpus; it has not undergone a database migration or linguistic validation decision. |
| `conflicting_translation` | 1 | `MANUAL_REVIEW_REQUIRED` | Shares normalized term(s) with a differently keyed database record. |
| All other requested categories | 0 | — | No structural evidence was found for malformed, incomplete, generated, OCR-artifact, unsupported-direction, or import-candidate legacy-only keys. |

The conflicting key is from the cleaned CSV corpus and has English text “one day and one night.” It is not imported or altered. The conflict flag is structural only; it is not a claim about linguistic correctness.

Import recommendation totals: **0 `IMPORT_CANDIDATE`**, **610 `KEEP_LEGACY_ONLY`**, **0 `EXCLUDE`**, and **1 `MANUAL_REVIEW_REQUIRED`**. A future import, if approved, should create an immutable import batch, preserve `cross_lingual_cleaned_v1.csv` provenance, insert entries inactive or in a separately reviewed staging state, never mark them verified, and roll back by deactivation/batch tracking rather than deletion. The projected row count is deliberately not proposed because no candidates are approved.

## Legacy Resource Staging

The administrator-only **Legacy Resource Staging** page presents all 611 legacy-only normalized resources without modifying the corpus or database. It shows all four language values, CSV source and original row identifier, completeness, normalized key, duplicate/conflict/anomaly state, phrase length, runtime usability, status, reason, search, filters, and pagination.

Current technical staging summary:

| Status | Count | Disposition |
|---|---:|---|
| `READY_FOR_ADMIN_REVIEW` | 610 | Structurally complete and technically usable, but not linguistically asserted correct. Default disposition: keep legacy-only until an administrator explicitly selects it. |
| `CONFLICT` | 1 | Must receive human language review; cannot be selected for import from staging. |
| `INCOMPLETE`, `POSSIBLE_DUPLICATE`, `POSSIBLE_OCR_ARTIFACT`, `MANUAL_LANGUAGE_REVIEW` | 0 | No structural records in these categories. |

Staging decisions (`Import`, `Ignore`, `Keep Legacy Only`, `Needs Review`) are session-local and non-destructive. Selecting `Import` only creates a dry selection count; a separate confirmation POST is required before any `PhrasebookEntry` or import-batch record is written. No real records were selected or imported during this milestone.

### Structural conflict for human review

| Field | Legacy CSV `SENT-0544` | Database record `#784` |
|---|---|---|
| Bagobo-Tagabawa | `Sábbad álló asta sábbad dukilám.` | `sábbad álló asta sábbad dukilám` |
| English | `One day and one night.` | `one day` |
| Filipino | `Isang araw at isang gabi.` | `isang araw at isang gabi` |
| Cebuano | `Usa ka adlaw ug usa ka gabii.` | `usa ka adlaw ug usa ka gabii` |

The normalized Bagobo-Tagabawa, Filipino, and Cebuano fields coincide, while the normalized English fields differ (`one day and one night` versus `one day`). That is a structural translation conflict, not an automated linguistic judgment. In `development_unverified`, the legacy English sentence matches exactly. In `development_resources`, it is retained as unknown because the exact four-language resource has not been imported. Disposition: **manual human review; no record changed.**

Current database resource coverage is **1,018 / 1,629 = 62.49%**. This is resource-key coverage only; it is not translation accuracy.

## Controlled matching matrix

The read-only matrix instantiates both real runtime modes with the same inputs. Shared-resource cases produced identical text, cascade method, and fuzzy score where applicable.

| Case | Source → target | Result | Difference |
|---|---|---|---|
| Exact | English → Bagobo-Tagabawa | Both `exact_phrase` | None |
| Case/punctuation/whitespace normalization | English → Bagobo-Tagabawa | Both `normalized_phrase` | None |
| Multi-word phrase | English → Bagobo-Tagabawa | Both `exact_phrase` | None |
| Segmented input | English → Bagobo-Tagabawa | Both `segmented_phrase` | None |
| Conservative fuzzy | English → Bagobo-Tagabawa | Both `fuzzy_match`, score 0.9412 | None |
| Short-word fuzzy protection | English → Bagobo-Tagabawa | Both retain source as `unknown_for_review` | None |
| Filipino/Tagalog and Cebuano/Bisaya aliases | Tagalog → Bisaya | Both `exact_phrase` | None |
| Bagobo-Tagabawa reverse direction | Bagobo-Tagabawa → English | Both `exact_phrase` | None |
| Unknown preservation | English → Bagobo-Tagabawa | Both retain source as `unknown_for_review` | None |
| Legacy-only corpus phrase | English → Bagobo-Tagabawa | Legacy exact match; database mode retains source | Expected: record is intentionally database-absent |

The matrix is exposed by `run_matching_parity_matrix()` in `translator.services.resource_parity`; it uses the same `TranslationDataset` service as documents, Quick Translation, and Match Tester.

## Workflow findings

- **Quick Translation:** controlled shared-entry parity is covered by tests. The public endpoint now returns only text, language labels, review-required state, and a user-safe reason. It does not expose method, similarity, dataset/cache state, resource IDs, or provenance.
- **Document pipeline:** controlled layout parity covers known and unknown lines, result method, and review-required state. Existing pipeline, preview, download, PDF routing, and reconstruction regression groups pass, but the full digital/scanned/image/DOCX end-to-end comparison has not been run separately under both live modes.
- **Preview/PDF:** existing regression groups pass with legacy mode. A two-mode visual/PDF fixture comparison remains required before cutover.
- **Cache refresh:** `TranslationResource` add/edit/toggle/import paths call `reset_translation_dataset()`. New/edited active entries are available on the next lookup without restart; deactivation removes matches on the next lookup; reactivation restores them. This was covered by focused tests.
- **Match Tester:** it constructs `TranslationDataset(data_mode="development_resources")` and calls `translate_phrase_with_metadata`, the same cascade used by document translation. It has no duplicate matcher.
- **Administrator resource change E2E:** test-database coverage passes: add via the protected resource form, Match Tester lookup, authenticated Quick Translation, document-layout lookup, deactivate exclusion, and reactivation refresh. No production entry was used.

## Cutover decision

`development_unverified` remains the current default. `development_resources` is **not** safe to make the normal development default yet: 611 unique normalized corpus records would change from a match to retained source text, and the full two-mode document/PDF/preview and browser parity work remains incomplete.

### Rollback

No cutover has occurred. If a future approved cutover is reversed, set:

```text
TRANSLATION_DATA_MODE=development_unverified
```

Restart the application process only to reload its environment configuration. Do not delete legacy files or database resources. `verified_only` remains separately available and fail-closed.
