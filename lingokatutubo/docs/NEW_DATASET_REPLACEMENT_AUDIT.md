# New Dataset Replacement Audit

## 1. Executive summary

The supplied CSV is **STRUCTURALLY CLEAN after staging correction, not linguistically verified**. The immutable source has 2,059 CSV records: 1,436 populated and 623 blank trailing records. The cleaned staging file has 1,436 data rows. No import, replacement, database mutation, model execution, or training occurred.

Comparison counts use unique four-language records so duplicate source rows do not inflate exact/new/changed totals. The comparison scope is the current default runtime union (JSON + cleaned corpus + validated exports), all PhrasebookEntry rows for governance visibility, and the legacy phrasebook archive, collapsed by exact four-language value.

## 2. New dataset structure

- Source: `C:\Users\wapak\Downloads\cross_lingual_datasets(Sheet1)%20(3).csv`
- SHA-256: `b0e93f4a93e3931352e71aa5c3f0631d135d7ff4bdc89a6bd3a87d1bc5842011`
- Encoding: UTF-8 with BOM
- Header: absent
- Maximum columns: 5; column 5 is completely empty
- Populated rows: 1,436
- Blank trailing rows removed from staging: 623
- Malformed CSV rows: 0

## 3. Current/old dataset architecture

| source | format | languages | records | role | used_during_translation | governance | safe_to_replace |
| --- | --- | --- | --- | --- | --- | --- | --- |
| translator/services/translation_data.json | JSON | Bagobo-Tagabawa, English, Filipino, Cebuano | 1028 | Default runtime base; first-loaded precedence | YES in development_unverified | Legacy/development-unverified | NO — active source; back up and dry-run first |
| datasets/cleaned/cross_lingual_cleaned_v1.csv | CSV | Bagobo-Tagabawa, English, Filipino, Cebuano | 612 | Default runtime additive text corpus; model-preparation input elsewhere | YES in development_unverified | Legacy/development-unverified | NO — active source; retain for rollback |
| datasets/validated/*.csv | CSV | Bagobo-Tagabawa, English, Filipino, Cebuano | 0 | Optional sorted additive validated exports (0 files present) | YES when files exist in development_unverified | Expected SME-validated export | Only through governed export/import workflow |
| db.sqlite3:translator_phrasebookentry | SQLite/Django model | Bagobo-Tagabawa, English, Filipino, Cebuano | 1018 | Translation Resources governance store | Only in development_resources or verified_only | Per-row active/verification/approval/restriction metadata | NO — export and preserve governance first |
| translator.services.translation_dataset.TranslationDataset | Python in-memory service | Bagobo-Tagabawa, English, Filipino, Cebuano | not a table | Loader/index and matching engine | YES | Mode-dependent | Not a dataset to replace |
| backend/tagabawa_phrasebook_cleaned_auto(phrases).csv | CSV | Bagobo-Tagabawa, English, Filipino, Cebuano | 1015 | Legacy source/archive and converter input | NO while bundled JSON loads successfully | Legacy/read-only; not governed | Retain as rollback evidence |
| datasets/review_candidates/unknown_for_review_candidates_2026-07-08.csv | CSV | Bagobo-Tagabawa, English, Filipino, Cebuano | 59 | Manual review candidates | NO | Review-only/unverified | Do not promote automatically |
| translator tests and evaluate_translation_pipeline command inputs | Synthetic JSON/temporary fixtures | Bagobo-Tagabawa, English, Filipino, Cebuano | test-defined | Tests/evaluation only | NO in production | Test-only | Not replacement targets |
| docs/phase1 and docs/phase2 JSON reports/manifests | JSON reports | Bagobo-Tagabawa, English, Filipino, Cebuano | metadata only | Audit/governance evidence | NO | Read-only reporting | Retain; not translation data |

`TranslationDataset` is a Python loader/index service, not a Django database model or table. `Translation Resources` is the UI/governance layer over `PhrasebookEntry`.

## 4. Current translation source of truth

The current process environment resolves `TRANSLATION_DATA_MODE` to `development_unverified`. With the observed/default `development_unverified` mode, load precedence is:

1. `translator/services/translation_data.json`
2. `datasets/cleaned/cross_lingual_cleaned_v1.csv` appended
3. `datasets/validated/*.csv` appended in filename order when present

Indices preserve insertion order and matching returns the first row with a non-empty target, so the JSON wins over later sources for colliding keys. The lookup cascade is raw/exact phrase, safe normalized variants, conservative segmented phrase, fuzzy match, then explicit unknown/review preservation. CSV/Excel discovery beside the JSON is only a file-load fallback when the configured JSON does not load; the backend archive is in another directory and is not reached in the current successful-JSON path.

Mode alternatives are isolated: `development_resources` reads active `PhrasebookEntry` rows only; `verified_only` reads only active, verified, explicitly runtime-approved governed entries and fails closed. Current DB inventory: 1,018 total PhrasebookEntry rows, 1,018 active, and 0 meeting the loader's initial active/verified/approved query shape before the additional governance eligibility function.

## 5. New CSV structural problems

- No canonical header.
- A fifth column is present but empty throughout.
- English and Cebuano change physical positions after row 460.
- 623 fully blank trailing records.
- 37 cells across 23 rows had accidental outer whitespace.
- Missing values after correction: `{}`.
- Unicode cells differing from NFC: 0; these source values were preserved, with NFC used only in comparison keys.

## 6. Column-order findings

| start_row | end_row | column_1_language | column_2_language | column_3_language | column_4_language | confidence | notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 460 | Bagobo-Tagabawa | English | Filipino | Cebuano | HIGH | Chosen by exact old-record anchors and English/Cebuano token evidence. |
| 461 | 1436 | Bagobo-Tagabawa | Cebuano | Filipino | English | HIGH | Proven swapped block; corrected mechanically in staging. |

Evidence: 45 canonical-layout exact anchors, 961 swapped-layout exact anchors, and 0 contrary anchors. Confidence is HIGH.

## 7. Safe corrections performed

- Added canonical header `bagobo_tagabawa,english,filipino,cebuano`.
- Mechanically reordered English/Cebuano for 976 proven swapped-block rows.
- Removed the completely empty fifth column and 623 trailing blank records.
- Trimmed outer whitespace only; internal whitespace, punctuation, accents, apostrophes, and linguistic marks were preserved.
- Retained all duplicate and questionable meanings for review; no linguistic rewriting was performed.

## 8. Old dataset totals

- Runtime JSON: 1,028 rows
- Runtime cleaned corpus: 612 rows
- Validated additive exports: 0 rows across 0 files
- PhrasebookEntry: 1,018 total / 1,018 active / 0 inactive
- Legacy backend archive: 1,015 rows
- Comparison union after exact collapse: 1,632 unique records and 1,492 unique normalized Bagobo-Tagabawa sources

## 9. New dataset totals

- Clean rows: 1,436
- Unique exact four-language records: 1,403
- Unique normalized Bagobo-Tagabawa sources: 1,248

## 10. Comparison totals

- Source overlap: 865
- Old-source coverage by new: 57.98%
- New-source overlap with old: 69.31%
- Exact matches: 999
- Normalized-only matches: 1
- Changed/additional/conflicting records: 9
- New-only records: 394
- Old-only records (source absent in new): 630

## 11. Exact matches

`new_vs_old_comparison.csv` contains 999 unique exact matches. Source row lists preserve all duplicate occurrences.

## 12. Changed translations

There are 9 unique new records with the same normalized source but changed, additional, or conflicting translations. Each language is shown separately in `new_vs_old_comparison.csv`; no value was automatically selected.

## 13. New-only entries

There are 394 unique new-only records. They are labeled `NEW_DATASET_CANDIDATE`, not verified.

## 14. Old-only entries

There are 630 unique old records whose normalized Bagobo-Tagabawa source is absent from the new file. They are labeled `OLD_ONLY_REVIEW` and must not be deleted automatically.

## 15. Duplicate analysis

- Exact duplicate groups: 33
- Exact duplicate excess rows: 33
- Normalized duplicate groups not already exact: 1
- Multiple-meaning source candidates: 95

Exact duplicates remain in staging. `exact_duplicates.csv` records every original row number so a later approved dry-run can propose safe removals.

## 16. Conflict analysis

There are 41 distinct normalized source keys with conservative conflict evidence. Same-source/different-English variants are treated as additional-meaning candidates; same-source/same-English rows with different Filipino or Cebuano values are conflicts. All are retained and require linguistic review.

## 17. Suspicious-language analysis

Conservative marker and structural checks flagged 0 source rows. Heuristics require multiple distinctive wrong-language markers and are not claimed as definitive language identification. Missing fields, malformed fragments, headers in data, Unicode replacement/control characters, and common mojibake sequences are also flagged. Mechanically proven raw column swaps are documented separately and do not require linguistic rewriting.

## 18. Proposed Django mapping

One cleaned four-language row maps naturally to one `PhrasebookEntry` because the existing model stores `tagabawa`, `english`, `filipino`, and `cebuano` together. The runtime builds an index for every populated language on that row, so one stored row already supports the existing code's permitted forward and reverse lookups. Do **not** create three or twelve pairwise duplicate records. Proposed field map:

| Staging field | Django field |
| --- | --- |
| `bagobo_tagabawa` | `PhrasebookEntry.tagabawa` |
| `english` | `PhrasebookEntry.english` |
| `filipino` | `PhrasebookEntry.filipino` |
| `cebuano` | `PhrasebookEntry.cebuano` |

## 19. Governance considerations

Future candidates must enter as pending/review-required with provenance, license, cultural-sensitivity, access-restriction, and import-batch metadata. The new CSV does not confer SME verification or runtime approval. Preserve existing `is_active`, `is_sme_verified`, `needs_review`, `validation_status`, `is_approved_for_runtime`, conflicts, restrictions, revisions, validator identity/date, and source metadata. Never overwrite a governed record merely because the text key matches.

## 20. Replacement risks

- Replacing only the JSON would leave the additive corpus and optional validated exports active.
- Switching modes changes whether the database or files are the entire source set; mixing them silently is explicitly prevented by current code.
- First-loaded precedence can hide later conflicting rows.
- Polysemy can look like duplication; normalized matching can hide meaningful case/spacing distinctions.
- Old-only records may be valid omissions from the new sheet.
- Any eventual replacement can change all language directions because one row is indexed under every populated language.

## 21. Recommended next phase

Before any import, back up the database, export all PhrasebookEntry rows with governance/revisions, export Translation Resources/import batches/issues, preserve the JSON, cleaned corpus, validated exports, legacy archive, file hashes, row counts, and mode/configuration evidence. Then implement a read-only dry-run reporting `CREATED`, `UNCHANGED`, `UPDATED`, `SKIPPED`, `CONFLICT`, `OLD_ONLY`, `INVALID`, and `REVIEW_REQUIRED`. Require explicit reviewer decisions for changed, conflict, normalized-duplicate, new-only, and old-only groups.

## 22. Rollback requirements

Rollback must restore the database and all file-based runtime resources as one versioned set, restore governance states and revision history, restore the prior `TRANSLATION_DATA_MODE`, clear only the normal in-process dataset cache after an approved deployment, and verify pre/post counts and hashes. No rollback action was needed in this audit because no replacement occurred.

## Quality validation

Staging QA: `{"data_row_count": 1436, "database_sha256_unchanged": true, "exactly_four_columns": true, "header_exact": true, "mechanical_values_exactly_preserved": true, "no_fully_blank_data_rows": true, "no_line_corruption": true, "source_file_sha256_unchanged": true, "utf8_bom_present": false, "valid_utf8": true}`

## Protection confirmations

- PhrasebookEntry rows created: 0
- PhrasebookEntry rows updated: 0
- PhrasebookEntry rows deleted: 0
- TranslationDataset rows changed: 0 (it is an in-memory service, not a table)
- Database replacement performed: NO
- ByT5 files modified: 0
- ByT5 configuration changes: 0
- ByT5 model executions: 0
- ByT5 training runs: 0

## Tests

Artifact structural QA passed inside the audit script. `python manage.py check`: **PASS**. Focused `translator.test_resource_parity` and `translator.test_translation_resources` suite: **PASS** (14 tests). The focused suite used Django's disposable test database; the production `db.sqlite3` hash remained unchanged. The neural model was not loaded or executed.
