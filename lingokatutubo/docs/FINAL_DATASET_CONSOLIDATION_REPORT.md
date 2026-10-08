# Final Dataset Consolidation Report

## 1. Original datasets

The finalization used the 1,436-row corrected staging dataset, the 1,028-row runtime JSON, the 612-row cleaned corpus, current PhrasebookEntry records, and the historical legacy archive. ByT5 was excluded from every step.

## 2. New dataset corrections

The established column correction was retained: rows 1–460 used Bagobo-Tagabawa/English/Filipino/Cebuano, while rows 461–1,436 had English and Cebuano restored to their correct positions. Accents and punctuation were preserved.

## 3. Comparison results

Phase 1 identified 999 exact matches, one normalized-only match, 394 new-only records, 630 old-only source keys, and 41 conflict keys.

## 4. Duplicate cleanup

The merged base already excluded 33 exact duplicate excess rows and one mechanically safe normalized duplicate excess. The final master contains zero exact duplicate excess rows.

## 5. Preservation strategy

The 2,030-row merged preservation candidate was the base. The strict replacement candidate was not used because its projected old-source coverage loss was approximately 42.23%.

## 6. Human decisions

Eight approved structural decisions were applied: four explicit keep/reject decisions and four KEEP_BOTH decisions. KEEP_BOTH sources remain marked `MULTI_SENSE_REQUIRES_CONTEXT`; row order is not presented as linguistic verification.

## 7. Quarantined linguistic conflicts

Six unresolved review groups were excluded from active translation and preserved in the validator-review dataset. An unaccented `madigar` lookup collision was included under P1-003 so the quarantined accented source cannot resolve through diacritic-insensitive matching.

## 8. Final canonical dataset

The final master contains **2,011 rows** across **1,866 normalized Bagobo-Tagabawa sources**. It is UTF-8, four-column, nonblank, and exact-duplicate-free.

## 9. Phrasebook synchronization

PhrasebookEntry changed from 1,018 total/1,018 active records to 2,029 total/2,011 active records. Existing IDs and governance were preserved for matches; historical rejected or unresolved records were deactivated, not deleted. New records remain pending and review-aware.

## 10. Runtime synchronization

Runtime JSON and cleaned corpus now each contain 2,011 active final rows. Their exact tuple sets match the final master. Validated exports remained empty; no false validated file was created.

## 11. Document translator verification

`development_unverified` and `development_resources` both passed set parity and representative exact-lookup parity against the final master. TranslationDataset remained the existing in-memory loader; no new database table or duplicate storage layer was created.

## 12. PDF/DOCX testing

Small text PDF and DOCX documents completed extraction, translation, reconstruction, bilingual preview generation, and translated PDF output. Results: PDF **PASS**; DOCX **PASS**.

## 13. Governance preservation

Existing validation, SME status, licensing, access, cultural-sensitivity, reviewer/history, import-batch, and provenance fields were retained. Structural approval was not converted into SME verification or runtime approval.

## 14. Backup and rollback

Rollback package: `C:\Users\wapak\Downloads\YAWA\lingokatutubo\dataset_backups\finalization_20260901_234801`. It contains an online-consistent database backup, raw SQLite companions, active runtime files, legacy archive, audit artifacts, governance export, and a SHA-256 manifest.

## 15. Excel report

`dataset_outputs/LINGOKATUTUBO_FINAL_DATASET_REPORT.xlsx` contains the final master, applied decisions, quarantine, comparisons, synchronization logs, QA/tests, backup manifest, and provenance inventory.

## 16. ByT5 safety

- ByT5 files modified: 0
- ByT5 configuration changes: 0
- ByT5 executions: 0
- ByT5 evaluations: 0
- ByT5 training runs: 0

## 17. Remaining validator work

P1-001, P1-002, P1-003, P1-008, P2-001, and P2-006 remain `VALIDATOR_REVIEW_REQUIRED`. Until governed validation occurs, those exact lookup families preserve source text through unknown handling.

## Integrity hashes

- Final master: `aa5590aa1759431d5da15cdd1e305b08eefe6f60a9498b99dd2b0841e926d35e`
- Runtime JSON: `3e2f3b901579d681d695450fb30786c26b7caff16e7771039bed0f711ffc010d`
- Cleaned corpus: `aa5590aa1759431d5da15cdd1e305b08eefe6f60a9498b99dd2b0841e926d35e`
- Database: `22e941d73568eecbb531b476ea6d1c5477a1c816dcbdbf4d2f8880b05f0d5f40`
