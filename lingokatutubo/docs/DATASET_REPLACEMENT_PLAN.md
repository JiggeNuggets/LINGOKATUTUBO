# Dataset Replacement Plan

## 1. Status and scope

Phase 2 is review triage and inactive candidate preparation only. No database import, runtime replacement, translation-mode change, model action, commit, or push was performed. Candidate files are **STRUCTURALLY VALID**, not linguistically verified.

## 2. Phase 1 verification

Verification result: **CONSISTENT**. Recomputed counts match the Phase 1 summary: 1,436 staging rows, 1,403 unique records, 1,248 unique sources, 33 exact duplicate groups/excess rows, 1 normalized duplicate group, 999 exact old matches, 1 normalized match, 9 changed records, 394 new-only, 630 old-only, 41 conflict keys, and 685 review-required source rows. Discrepancies: 0.

All eight Phase 1 artifacts were hashed before and after Phase 2 generation and remained unchanged.

## 3. Review triage

| level | source_rows | meaning |
| --- | --- | --- |
| LEVEL 1 - MECHANICALLY SAFE | 2 | Case-only normalized duplicate rows; no linguistic selection. |
| LEVEL 2 - LIKELY SAFE BUT REVIEWABLE | 393 | Complete new-only or non-conflicting rows; candidate status only. |
| LEVEL 3 - LINGUISTIC REVIEW REQUIRED | 269 | Changed, target-variant, or possible multiple-meaning rows. |
| LEVEL 4 - HIGH-RISK CONFLICT | 21 | Direct/incomplete/semantically dangerous first-wins collision candidates. |

The four levels partition exactly 685 Phase 1 review-required new source rows. Exact duplicate excess rows were already mechanically safe and were not part of the Phase 1 manual-review count.

## 4. Mechanical duplicate decisions

- Removed from inactive candidates only: 33 exact duplicate excess rows.
- Normalized group inspected: source rows 185 and 1243.
- Values: `Duwa / Two / Dalawa / Duha` versus lowercase equivalents.
- Assessment: case-only; punctuation, accents, and lexical content are identical.
- Candidate action: keep row 185 and remove row 1243 from inactive candidates. Original and Phase 1 staging files remain unchanged.

## 5. Nine changed translations

| source_row | bagobo_tagabawa | old_english | new_english | old_filipino | new_filipino | old_cebuano | new_cebuano | phase1_status | recommendation | rationale |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 60 | géna | a while ago | earlier | kanina | kanina | ganiha | ganiha | SAME_SOURCE_ADDITIONAL_MEANING | KEEP_BOTH | 'Earlier' and 'a while ago' are compatible temporal senses, but context should be recorded. |
| 89 | géna | a while ago | last night | kanina | kagabi | ganiha | kagabii | SAME_SOURCE_ADDITIONAL_MEANING | MANUAL LINGUISTIC REVIEW | 'Last night' is semantically distinct from 'a while ago/earlier' for the same source. |
| 124 | ágkataláng | confused | confused | nalilito | nalito | nalibug | nalibug | CONFLICT | KEEP_BOTH | Filipino 'nalito' and 'nalilito' may encode aspect/tense variation; do not collapse without review. |
| 144 | salamat | Thank you | thank you | Salamat po | salamat | Salamat | salamat | CONFLICT | KEEP_BOTH | The old Filipino adds politeness ('po'); preserve both pending context/governance review. |
| 156 | magánnó | It's cold | cold | Maginaw | malamig | Tugnaw | tugnaw | SAME_SOURCE_ADDITIONAL_MEANING | KEEP_BOTH | 'Cold' and 'It's cold' may be lexical versus sentence-level uses of the same source. |
| 723 | Ágriyun | Feeling / Sensing | Feeling | Damdamin | Damdamin | Gibati | Gibati | SAME_SOURCE_ADDITIONAL_MEANING | KEEP_BOTH | The old English includes 'Sensing' while the new value narrows to 'Feeling'; retain pending sense review. |
| 1138 | Lagénut yu dád kag basa kó | Read silently | Read silently | Basahin (ninyo) ng tahimik | Basahin ninyo ng tahimik | Hinaya lang ninyo'g basa | Hinaya lang ninyo'g basa | CONFLICT | MANUAL LINGUISTIC REVIEW | Parenthesized versus explicit pronoun wording is not guaranteed to be formatting-only. |
| 1144 | Unsad kó | Sit down | Stand up | Maupo kayo | Maupo kayo | Lingkod mo | Maglingkod mo | SAME_SOURCE_ADDITIONAL_MEANING | KEEP OLD | New English 'Stand up' conflicts with new Filipino/Cebuano sitting translations and the old 'Sit down'. |
| 1158 | Ándin urasi tumigkané tô miting? | What time does the meeting start? | What time does the meeting start? | Anong oras magsisimula ang pulong | Anong oras magsisimula ang meeting | Unsang orasa mosugod ang miting? | Unsang orasa mosugod ang miting? | CONFLICT | MANUAL LINGUISTIC REVIEW | Filipino 'pulong' versus code-switched 'meeting' is a terminology/governance choice. |

These are recommendations for review, not executed decisions.

## 6. Forty-one conflict source keys

`high_priority_conflicts.csv` contains 41 unique normalized keys and 342 provenance-specific old/new variant rows. P1 marks dangerous/incomplete semantic collisions, P2 marks direct old/new changes, and P3 marks possible target synonyms or contextual variants.

## 7. New-only classification

| classification | count |
| --- | --- |
| NEW_COMPLETE | 372 |
| NEW_PARTIAL | 0 |
| NEW_CONFLICTING | 22 |
| NEW_REVIEW | 0 |

All remain `NEW_DATASET_CANDIDATE`; none is marked verified.

## 8. Old-only classification

| classification | count |
| --- | --- |
| OLD_ONLY_RUNTIME_VALID | 614 |
| OLD_ONLY_LEGACY | 0 |
| OLD_ONLY_GOVERNED | 14 |
| OLD_ONLY_DUPLICATED_ELSEWHERE | 0 |
| OLD_ONLY_MANUAL_REVIEW | 2 |

`OLD_ONLY_RUNTIME_VALID` means structurally complete and currently runtime-sourced, not linguistically verified. Governed rows retain their current metadata/status requirements.

## 9. Candidate A — strict replacement

- File: `dataset_outputs/new_only_replacement_candidate.csv`
- Rows: 1,402
- Exact duplicates removed: 33
- Mechanically safe normalized duplicate excess removed: 1
- Old unique records not represented: 633
- Old unique source keys not represented: 630
- Expected old source coverage loss: 42.23%
- New-only records gained: 394
- Conflict keys still requiring resolution: 41

## 10. Candidate B — merged preservation

- File: `dataset_outputs/merged_preservation_candidate.csv`
- Total rows: 2,030
- New candidate rows: 1,402
- Structurally preserved old-only rows: 628
- Old-only rows excluded for manual review: 2
- Old unique records still not represented: 5
- Exact/normalized mechanical duplicates in final file: 0/0
- Conflict keys still requiring resolution: 41

## 11. Strategy comparison

**Strategy A — strict replacement:** simpler 1,402-row file, adds 394 new-only records, but removes 633 old unique translation records across 630 old source keys. It does not resolve the 41 conflict keys and risks coverage regression.

**Strategy B — merged preservation:** retains 628 structurally safe old-only rows and materially reduces coverage loss. It has higher provenance/governance complexity and still requires conflict decisions. Neither strategy is selected automatically.

## 12. Exact runtime replacement implications

Current `development_unverified` precedence is:

1. `translator/services/translation_data.json`
2. `datasets/cleaned/cross_lingual_cleaned_v1.csv`
3. `datasets/validated/*.csv` in filename order

Earlier indexed rows win when a source key collides and has a non-empty target. A future file-based replacement must therefore treat all three layers as one release: replace or deliberately retire conflicting JSON/corpus rows, generate validated exports from the approved canonical set, document collision decisions, and verify file hashes/counts. Replacing only one file cannot establish a new source of truth.

## 13. PhrasebookEntry implications

One approved four-language candidate row maps to one `PhrasebookEntry` (`tagabawa`, `english`, `filipino`, `cebuano`). `development_resources` reads active database rows only. `verified_only` reads active, verified, runtime-approved governed entries and fails closed. Future synchronization must preserve source, license, cultural-sensitivity, access, validation, review, conflict, approval, revision, validator, and import-batch metadata. No database row was written in this phase.

## 14. Recommended future source of truth

Recommend the architecture already supported by the project: make governed `PhrasebookEntry` the canonical maintenance source, use `development_resources` for database-backed development, and move production to `verified_only` only after parity, governance, and regression approval. Runtime JSON/corpus exports should become versioned generated rollback snapshots, not separately hand-maintained competing sources. This minimizes stale copies and precedence drift. Do not switch modes until the migration dry-run and rollback package are approved.

## 15. Manual review queue

`manual_review_queue.csv` contains 292 genuine decision rows after mechanical triage: {'P1': 21, 'P2': 6, 'P3': 263, 'P5': 2}. `review_decision` and `review_notes` are blank. Structurally complete, non-conflicting new-only rows and mechanically safe duplicate actions are excluded to reduce human workload.

## 16. Future dry-run specification

The dry-run must be read-only and report:

- `RUNTIME_JSON_ADD`, `RUNTIME_JSON_REMOVE`, `RUNTIME_JSON_CHANGE`
- `CORPUS_ADD`, `CORPUS_REMOVE`, `CORPUS_CHANGE`
- `PHRASEBOOK_CREATE`, `PHRASEBOOK_UPDATE`, `PHRASEBOOK_UNCHANGED`
- `PHRASEBOOK_CONFLICT`, `PHRASEBOOK_PRESERVE`

Every row must carry canonical values, normalized keys, provenance, governing decision, old/new hashes, and a reversible action identifier.

## 17. Future replacement phases

1. Resolve P1/P2 conflicts.
2. Approve candidate strategy.
3. Back up database and runtime resources.
4. Generate the dry-run.
5. Inspect and approve the dry-run.
6. Replace runtime resources as one versioned set.
7. Synchronize PhrasebookEntry if approved.
8. Run translation regression without neural/model evaluation unless separately authorized.
9. Roll back database, files, mode, and cache state if parity or regression fails.

## 18. Safety and rollback evidence

- PhrasebookEntry created/updated/deleted: 0/0/0
- TranslationDataset changed: 0
- Runtime JSON changed: 0
- Cleaned corpus changed: 0
- Validated runtime exports changed: 0
- Database replacement performed: NO
- ByT5 files modified/executions/training/configuration changes: 0/0/0/0
- Production database and runtime hashes remained unchanged.

## 19. Tests

`python manage.py check`: **PASS**. Focused dataset/resource tests: **PASS** (13 tests). No model evaluation or ByT5 test was run.
