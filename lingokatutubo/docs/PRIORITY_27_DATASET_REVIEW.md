# Priority 27 Dataset Review

## Scope and decision rules

This is a read-only human-approval packet for exactly 21 P1 rows and 6 P2 rows from `dataset_outputs/manual_review_queue.csv`. The 27 provenance rows are grouped into 14 decisions by normalized Bagobo-Tagabawa source. No recommendation has been applied, and P3/P4/P5 rows are outside this review.

The analysis below uses cross-language consistency and existing project provenance only. It does **not** claim that the agent can determine the correct Bagobo-Tagabawa meaning. Resource counts are evidence, not votes. `human_decision` and `human_notes` remain blank in the CSV; the human should record one decision per review ID, not one decision per provenance row.

Current runtime order is bundled JSON, cleaned corpus, then validated exports; earlier rows win collisions. For every source below, the cleaned corpus and review-candidate file contain no normalized-source match, and no validated CSV exports are present.

## Text-encoding verification

The accented strings that appeared as replacement glyphs in terminal output were a terminal/display issue, not stored Phase 2 corruption. `manual_review_queue.csv`, `high_priority_conflicts.csv`, `cleaned_dataset_staging.csv`, the runtime JSON, and all three Phase 3 artifacts decode as valid UTF-8 and contain zero U+FFFD replacement characters. For all 27 selected rows, the Phase 2 queue and this review CSV match the cited cleaned-staging source row exactly across Bagobo-Tagabawa, English, Filipino, and Cebuano. No text was guessed or silently repaired. `encoding_review_required`: **0**.

## Decision summary

| Measure | Count |
| --- | ---: |
| Priority rows | 27 |
| Unique decisions | 14 |
| KEEP_OLD | 1 |
| KEEP_NEW | 0 |
| KEEP_BOTH | 4 |
| MANUAL_LINGUISTIC_REVIEW | 9 |
| HIGH confidence | 4 |
| MEDIUM confidence | 5 |
| LOW confidence | 5 |

## Governance finding applying to all matching PhrasebookEntry rows

All 25 matching PhrasebookEntry records are active imports from `translation_data.json`, but none is governed as verified: validation is `pending`, SME verification is false, runtime approval is false, `needs_review` is true, license is `unrecorded`, access is `pending_review`, cultural-sensitivity status is `unreviewed`, and revision number is 1. The database contains zero `LanguageEntryReview` records, so none of these matches has formal review history. Consequently, PhrasebookEntry provenance does not provide stronger verified authority than the file copies.

---

## REVIEW ID: P1-001

**Bagobo-Tagabawa:** géna  
**Conflict type:** C SAME SOURCE - DIFFERENT CONTEXT

### OLD

- English: a while ago
- Filipino: kanina
- Cebuano: ganiha

### NEW provenance rows

| New row | Exact source | English | Filipino | Cebuano |
| ---: | --- | --- | --- | --- |
| 1200 | géna | a while ago | kanina | ganiha |
| 60 | géna | earlier | kanina | ganiha |
| 89 | géna | last night | kagabi | kagabii |

### Existing evidence

| Resource | Row | Exact source | English / Filipino / Cebuano | Status or governance |
| --- | ---: | --- | --- | --- |
| Runtime JSON | 779 | géna | a while ago / kanina / ganiha | active runtime, development-unverified |
| Legacy archive | 781 | géna | a while ago / kanina / ganiha | legacy-unverified |
| PhrasebookEntry | 778 | géna | a while ago / kanina / ganiha | active; pending; SME no; runtime-approved no; needs-review yes; rev 1; reviews 0 |

Independent existing resources supporting OLD: **3**. Supporting the changed NEW `earlier` or `last night` tuples: **0**. The unchanged new row shares the old three-resource support.

**Problem:** `earlier/a while ago` are compatible temporal expressions, but `last night` is a distinct time. First-wins matching would select one without context.  
**Recommendation:** MANUAL_LINGUISTIC_REVIEW  
**Confidence:** LOW  
**Reason:** The alternatives are internally coherent, but the Bagobo-Tagabawa time sense cannot be resolved structurally.  
**HUMAN DECISION:**

---

## REVIEW ID: P1-002

**Bagobo-Tagabawa:** hay blad  
**Conflict type:** F INSUFFICIENT EVIDENCE

### OLD and NEW provenance rows

| New row | Exact source | English | Filipino | Cebuano |
| ---: | --- | --- | --- | --- |
| 785 | hay blad | high blood pressure | mataas ang dogo | hay blad |
| 786 | hay blad | high blood pressure | high blood | high blood |

Both old fields are identical to their corresponding new rows.

### Existing evidence

| Resource | Row | Exact source | English / Filipino / Cebuano | Status or governance |
| --- | ---: | --- | --- | --- |
| Runtime JSON | 365 | hay blad | high blood pressure / mataas ang dogo / hay blad | active runtime, development-unverified |
| Runtime JSON | 366 | hay blad | high blood pressure / high blood / high blood | active runtime, development-unverified |
| Legacy archive | 366 | hay blad | high blood pressure / mataas ang dogo / hay blad | legacy-unverified |
| Legacy archive | 367 | hay blad | high blood pressure / high blood / high blood | legacy-unverified |
| PhrasebookEntry | 365 | hay blad | high blood pressure / mataas ang dogo / hay blad | active; pending; not runtime-approved; needs-review; rev 1; reviews 0 |
| PhrasebookEntry | 366 | hay blad | high blood pressure / high blood / high blood | active; pending; not runtime-approved; needs-review; rev 1; reviews 0 |

Independent resources supporting each OLD/NEW variant: **3**. The conflict predates the new CSV, so provenance count does not distinguish the forms.

**Problem:** One row uses target-language wording while the other uses `high blood`/loan wording. This may be code-switch usage, but no verified project evidence decides it. The visible spelling `dogo` is preserved exactly.  
**Recommendation:** MANUAL_LINGUISTIC_REVIEW  
**Confidence:** LOW  
**Reason:** A qualified reviewer must choose the appropriate register and determine whether both forms are legitimate.  
**HUMAN DECISION:**

---

## REVIEW ID: P1-003

**Bagobo-Tagabawa:** Madigár / madigár  
**Conflict type:** C SAME SOURCE - DIFFERENT CONTEXT

### OLD and NEW provenance rows

| New row | Exact source | English | Filipino | Cebuano |
| ---: | --- | --- | --- | --- |
| 1148 | Madigár | Good | Magaling | Maayo |
| 1149 | Madigár | Well behaved | Mabuti | Maayo |
| 1150 | Madigár | Good | Mahusay | Maayo |
| 422 | Madigár | Hello | Kamusta | Maayo |
| 633 | madigár | good | mabuti | maayo |

Every old field set is identical to its corresponding new row.

### Existing evidence

| Resource | Rows | Exact source and translations | Status or governance |
| --- | --- | --- | --- |
| Runtime JSON | 2 | Madigár — Hello / Kamusta / Maayo | active runtime, development-unverified |
| Runtime JSON | 213 | madigár — good / mabuti / maayo | active runtime, development-unverified |
| Runtime JSON | 727 | Madigár — Good / Magaling / Maayo | active runtime, development-unverified |
| Runtime JSON | 728 | Madigár — Well behaved / Mabuti / Maayo | active runtime, development-unverified |
| Runtime JSON | 729 | Madigár — Good / Mahusay / Maayo | active runtime, development-unverified |
| Legacy archive | 3 | Madigár — Hello / Kamusta / Maayo | legacy-unverified |
| Legacy archive | 214 | madigár — good / mabuti / maayo | legacy-unverified |
| Legacy archive | 729 | Madigár — Good / Magaling / Maayo | legacy-unverified |
| Legacy archive | 730 | Madigár — Well behaved / Mabuti / Maayo | legacy-unverified |
| Legacy archive | 731 | Madigár — Good / Mahusay / Maayo | legacy-unverified |
| PhrasebookEntry | 2, 213, 726, 727, 728 | Same five exact source/translation variants as above | active; pending; not runtime-approved; needs-review; rev 1 each; reviews 0 |

Independent resources supporting the OLD and NEW variant set: **3**. The same context conflict exists in all three.

**Problem:** The normalized source covers `Hello`, `Good`, and `Well behaved`; those meanings cannot be selected safely by unqualified first-wins lookup.  
**Recommendation:** MANUAL_LINGUISTIC_REVIEW  
**Confidence:** LOW  
**Reason:** The rows may all be contextually valid, but word-sense/context metadata and linguistic authority are required before preserving or reducing them.  
**HUMAN DECISION:**

---

## REVIEW ID: P1-004

**Bagobo-Tagabawa:** mama  
**Conflict type:** B WRONG-LANGUAGE / COLUMN LEGACY ISSUE

### OLD and NEW provenance rows

| New row | English | Filipino | Cebuano |
| ---: | --- | --- | --- |
| 579 | male | lalaki | lalaki |
| 580 | male | mama | lalaki |

Both old field sets are identical to their corresponding new rows.

### Existing evidence

| Resource | Row | Exact source | English / Filipino / Cebuano | Status or governance |
| --- | ---: | --- | --- | --- |
| Runtime JSON | 159 | mama | male / lalaki / lalaki | active runtime, development-unverified |
| Runtime JSON | 160 | mama | male / mama / lalaki | active runtime, development-unverified |
| Legacy archive | 160 | mama | male / lalaki / lalaki | legacy-unverified |
| Legacy archive | 161 | mama | male / mama / lalaki | legacy-unverified |
| PhrasebookEntry | 159 | mama | male / lalaki / lalaki | active; pending; not runtime-approved; needs-review; rev 1; reviews 0 |
| PhrasebookEntry | 160 | mama | male / mama / lalaki | active; pending; not runtime-approved; needs-review; rev 1; reviews 0 |

Independent resources supporting each OLD/NEW variant: **3**. The outlier is legacy as well as new.

**Problem:** English `male` and Cebuano `lalaki` align with Filipino `lalaki`; Filipino `mama` is the cross-language outlier and repeats the source text.  
**Recommendation:** MANUAL_LINGUISTIC_REVIEW  
**Confidence:** HIGH  
**Reason:** Mechanical evidence strongly favors retaining the aligned variant, but the outlier must be classified by a human as wrong-column, source echo, or another intended usage.  
**HUMAN DECISION:**

---

## REVIEW ID: P1-005

**Bagobo-Tagabawa:** Pakawanan tut duwán ágsuwéyan  
**Conflict type:** A DIRECT CONTRADICTION

### OLD and NEW provenance rows

| New row | English | Filipino | Cebuano |
| ---: | --- | --- | --- |
| 1091 | Turn right at the corner | Pakanan tayo sa kanto | Patoo sa naay eskina |
| 1092 | Turn right at the corner | Pakanan tayo sa kanto | kanto |

Both old field sets are identical to their corresponding new rows.

### Existing evidence

| Resource | Rows | Exact source and translations | Status or governance |
| --- | --- | --- | --- |
| Runtime JSON | 670 | Pakawanan tut duwán ágsuwéyan — Turn right at the corner / Pakanan tayo sa kanto / Patoo sa naay eskina | active runtime, development-unverified |
| Runtime JSON | 671 | Pakawanan tut duwán ágsuwéyan — Turn right at the corner / Pakanan tayo sa kanto / kanto | active runtime, development-unverified |
| Legacy archive | 672, 673 | Same two exact variants | legacy-unverified |
| PhrasebookEntry | 669, 670 | Same two exact variants | active; pending; not runtime-approved; needs-review; rev 1 each; reviews 0 |

Independent resources supporting each OLD/NEW variant: **3**. The incomplete target already exists in all old resource classes.

**Problem:** Cebuano `kanto` is a bare location noun while English and Filipino express a complete turn-right instruction.  
**Recommendation:** MANUAL_LINGUISTIC_REVIEW  
**Confidence:** HIGH  
**Reason:** The structural defect is strong, but KEEP_OLD/KEEP_NEW is not meaningful because both versions contain it. Human approval should retain the complete variant and remove or repair the fragment only after confirmation.  
**HUMAN DECISION:**

---

## REVIEW ID: P1-006

**Bagobo-Tagabawa:** Sumódô tut duwán ágsuwéyan  
**Conflict type:** A DIRECT CONTRADICTION

### OLD and NEW provenance rows

| New row | English | Filipino | Cebuano |
| ---: | --- | --- | --- |
| 1094 | Stop at the corner | Huminto ka sa kanto | Hunong sa eskina |
| 1095 | Stop at the corner | Huminto ka sa kanto | kanto |

Both old field sets are identical to their corresponding new rows.

### Existing evidence

| Resource | Rows | Exact source and translations | Status or governance |
| --- | --- | --- | --- |
| Runtime JSON | 673 | Sumódô tut duwán ágsuwéyan — Stop at the corner / Huminto ka sa kanto / Hunong sa eskina | active runtime, development-unverified |
| Runtime JSON | 674 | Sumódô tut duwán ágsuwéyan — Stop at the corner / Huminto ka sa kanto / kanto | active runtime, development-unverified |
| Legacy archive | 675, 676 | Same two exact variants | legacy-unverified |
| PhrasebookEntry | 672, 673 | Same two exact variants | active; pending; not runtime-approved; needs-review; rev 1 each; reviews 0 |

Independent resources supporting each OLD/NEW variant: **3**. The conflict is inherited, not newly introduced.

**Problem:** Cebuano `kanto` is only a location noun while English and Filipino contain a complete stop instruction.  
**Recommendation:** MANUAL_LINGUISTIC_REVIEW  
**Confidence:** HIGH  
**Reason:** The fragment is structurally inconsistent, but a human must approve removal or repair because both old and new sets contain it.  
**HUMAN DECISION:**

---

## REVIEW ID: P1-007

**Bagobo-Tagabawa:** Unsad kó  
**Conflict type:** A DIRECT CONTRADICTION

### OLD and NEW provenance rows

| New row | OLD English / Filipino / Cebuano | NEW English / Filipino / Cebuano |
| ---: | --- | --- |
| 1144 | Sit down / Maupo kayo / Lingkod mo | Stand up / Maupo kayo / Maglingkod mo |
| 427 | Sit down / Maupo kayo / Lingkod mo | Sit down / Maupo kayo / Lingkod mo |
| 428 | Have a seat / Maupo kayo / Lingkod mo | Have a seat / Maupo kayo / Lingkod mo |

### Existing evidence

| Resource | Row | Exact source | English / Filipino / Cebuano | Status or governance |
| --- | ---: | --- | --- | --- |
| Runtime JSON | 7 | Unsad kó | Sit down / Maupo kayo / Lingkod mo | active runtime, development-unverified |
| Runtime JSON | 8 | Unsad kó | Have a seat / Maupo kayo / Lingkod mo | active runtime, development-unverified |
| Legacy archive | 8 | Unsad kó | Sit down / Maupo kayo / Lingkod mo | legacy-unverified |
| Legacy archive | 9 | Unsad kó | Have a seat / Maupo kayo / Lingkod mo | legacy-unverified |
| PhrasebookEntry | 7 | Unsad kó | Sit down / Maupo kayo / Lingkod mo | active; pending; not runtime-approved; needs-review; rev 1; reviews 0 |
| PhrasebookEntry | 8 | Unsad kó | Have a seat / Maupo kayo / Lingkod mo | active; pending; not runtime-approved; needs-review; rev 1; reviews 0 |

Independent resources supporting OLD sitting variants: **3**. Supporting the changed NEW `Stand up / Maupo kayo / Maglingkod mo` tuple: **0**.

**Problem:** `Stand up` directly contradicts Filipino `Maupo kayo`, Cebuano sitting language, and both old English variants.  
**Recommendation:** KEEP_OLD  
**Confidence:** HIGH  
**Reason:** This is the strongest mechanical case: old targets agree semantically across three languages and three resource classes, while the changed new row is internally inconsistent. Human approval is still required.  
**HUMAN DECISION:**

---

## REVIEW ID: P1-008

**Bagobo-Tagabawa:** Ánda tô kasilyas?  
**Conflict type:** A DIRECT CONTRADICTION

### OLD and NEW provenance rows

| New row | English | Filipino | Cebuano |
| ---: | --- | --- | --- |
| 1126 | Where is the comfort room? | Nasaan ang kasilyas | Asa ang kasilyas? |
| 1127 | Where is the comfort room? | kobeta? | Asa ang kasilyas? |

Both old field sets are identical to their corresponding new rows.

### Existing evidence

| Resource | Rows | Exact source and translations | Status or governance |
| --- | --- | --- | --- |
| Runtime JSON | 705 | Ánda tô kasilyas? — Where is the comfort room? / Nasaan ang kasilyas / Asa ang kasilyas? | active runtime, development-unverified |
| Runtime JSON | 706 | Ánda tô kasilyas? — Where is the comfort room? / kobeta? / Asa ang kasilyas? | active runtime, development-unverified |
| Legacy archive | 707, 708 | Same two exact variants | legacy-unverified |
| PhrasebookEntry | 704, 705 | Same two exact variants | active; pending; not runtime-approved; needs-review; rev 1 each; reviews 0 |

Independent resources supporting each OLD/NEW variant: **3**. Age and replication do not resolve the question-versus-fragment issue.

**Problem:** `Nasaan ang kasilyas` visibly aligns with the full English and Cebuano questions; `kobeta?` appears abbreviated or lexical.  
**Recommendation:** MANUAL_LINGUISTIC_REVIEW  
**Confidence:** MEDIUM  
**Reason:** Cross-language structure favors the full-question variant, but verified evidence is absent and `kobeta?` could require contextual interpretation.  
**HUMAN DECISION:**

---

## REVIEW ID: P2-001

**Bagobo-Tagabawa:** Lagénut yu dád kag basa kó  
**Conflict type:** C SAME SOURCE - DIFFERENT CONTEXT

### OLD

- English: Read silently
- Filipino: Basahin (ninyo) ng tahimik
- Cebuano: Hinaya lang ninyo'g basa

### NEW

- English: Read silently
- Filipino: Basahin ninyo ng tahimik
- Cebuano: Hinaya lang ninyo'g basa
- New row: 1138

### Existing evidence

| Resource | Row | Exact source | English / Filipino / Cebuano | Status or governance |
| --- | ---: | --- | --- | --- |
| Runtime JSON | 717 | Lagénut yu dád kag basa kó | Read silently / Basahin (ninyo) ng tahimik / Hinaya lang ninyo'g basa | active runtime, development-unverified |
| Legacy archive | 719 | Lagénut yu dád kag basa kó | same old tuple | legacy-unverified |
| PhrasebookEntry | 716 | Lagénut yu dád kag basa kó | same old tuple | active; pending; not runtime-approved; needs-review; rev 1; reviews 0 |

Independent resources supporting OLD: **3**. Supporting the exact NEW tuple: **0**.

**Problem:** Parenthesized optional `ninyo` becomes explicit, which is not guaranteed to be formatting-only.  
**Recommendation:** MANUAL_LINGUISTIC_REVIEW  
**Confidence:** MEDIUM  
**Reason:** Both are plausible, but usage/context confirmation is required before changing grammatical scope.  
**HUMAN DECISION:**

---

## REVIEW ID: P2-002

**Bagobo-Tagabawa:** magánnó  
**Conflict type:** C SAME SOURCE - DIFFERENT CONTEXT

### OLD

- English: It's cold
- Filipino: Maginaw
- Cebuano: Tugnaw

### NEW

- English: cold
- Filipino: malamig
- Cebuano: tugnaw
- New row: 156

### Existing evidence

| Resource | Row | Exact source | English / Filipino / Cebuano | Status or governance |
| --- | ---: | --- | --- | --- |
| Runtime JSON | 679 | Magánnó | It's cold / Maginaw / Tugnaw | active runtime, development-unverified |
| Legacy archive | 681 | Magánnó | same old tuple | legacy-unverified |
| PhrasebookEntry | 678 | Magánnó | same old tuple | active; pending; not runtime-approved; needs-review; rev 1; reviews 0 |

Independent resources supporting OLD: **3**. Supporting the exact NEW tuple: **0**.

**Problem:** The versions may be sentence-level versus lexical renderings rather than contradictions.  
**Recommendation:** KEEP_BOTH  
**Confidence:** MEDIUM  
**Reason:** Meanings are compatible, but both should be preserved only with usage metadata so first-wins matching does not erase the distinction.  
**HUMAN DECISION:**

---

## REVIEW ID: P2-003

**Bagobo-Tagabawa:** salamat  
**Conflict type:** C SAME SOURCE - DIFFERENT CONTEXT

### OLD

- English: Thank you
- Filipino: Salamat po
- Cebuano: Salamat

### NEW

- English: thank you
- Filipino: salamat
- Cebuano: salamat
- New row: 144

### Existing evidence

| Resource | Row | Exact source | English / Filipino / Cebuano | Status or governance |
| --- | ---: | --- | --- | --- |
| Runtime JSON | 710 | Salamat | Thank you / Salamat po / Salamat | active runtime, development-unverified |
| Legacy archive | 712 | Salamat | same old tuple | legacy-unverified |
| PhrasebookEntry | 709 | Salamat | same old tuple | active; pending; not runtime-approved; needs-review; rev 1; reviews 0 |

Independent resources supporting OLD: **3**. Supporting the exact NEW tuple: **0**.

**Problem:** Filipino changes politeness level through removal of `po`; other visible changes are case.  
**Recommendation:** KEEP_BOTH  
**Confidence:** MEDIUM  
**Reason:** Both are semantically compatible at different registers, provided the approved data records politeness context.  
**HUMAN DECISION:**

---

## REVIEW ID: P2-004

**Bagobo-Tagabawa:** ágkataláng  
**Conflict type:** C SAME SOURCE - DIFFERENT CONTEXT

### OLD

- English: confused
- Filipino: nalilito
- Cebuano: nalibug

### NEW

- English: confused
- Filipino: nalito
- Cebuano: nalibug
- New row: 124

### Existing evidence

| Resource | Row | Exact source | English / Filipino / Cebuano | Status or governance |
| --- | ---: | --- | --- | --- |
| Runtime JSON | 294 | ágkataláng | confused / nalilito / nalibug | active runtime, development-unverified |
| Legacy archive | 295 | ágkataláng | same old tuple | legacy-unverified |
| PhrasebookEntry | 294 | ágkataláng | same old tuple | active; pending; not runtime-approved; needs-review; rev 1; reviews 0 |

Independent resources supporting OLD: **3**. Supporting the exact NEW tuple: **0**.

**Problem:** Filipino `nalilito` versus `nalito` may encode aspect or tense while other targets stay fixed.  
**Recommendation:** KEEP_BOTH  
**Confidence:** MEDIUM  
**Reason:** The alternatives are compatible but contextual; preserve them only with human confirmation and usage metadata.  
**HUMAN DECISION:**

---

## REVIEW ID: P2-005

**Bagobo-Tagabawa:** Ágriyun  
**Conflict type:** C SAME SOURCE - DIFFERENT CONTEXT

### OLD

- English: Feeling / Sensing
- Filipino: Damdamin
- Cebuano: Gibati

### NEW

- English: Feeling
- Filipino: Damdamin
- Cebuano: Gibati
- New row: 723

### Existing evidence

| Resource | Row | Exact source | English / Filipino / Cebuano | Status or governance |
| --- | ---: | --- | --- | --- |
| Runtime JSON | 303 | Ágriyun | Feeling / Sensing / Damdamin / Gibati | active runtime, development-unverified |
| Legacy archive | 304 | Ágriyun | same old tuple | legacy-unverified |
| PhrasebookEntry | 303 | Ágriyun | same old tuple | active; pending; not runtime-approved; needs-review; rev 1; reviews 0 |

Independent resources supporting OLD: **3**. Supporting the exact NEW tuple: **0**.

**Problem:** The new English narrows a combined `Feeling / Sensing` gloss to `Feeling`; Filipino and Cebuano do not resolve whether the broader sense is valid.  
**Recommendation:** KEEP_BOTH  
**Confidence:** LOW  
**Reason:** The senses are compatible, but they should be separated and labeled pending linguistic validation rather than treated as interchangeable first-wins rows.  
**HUMAN DECISION:**

---

## REVIEW ID: P2-006

**Bagobo-Tagabawa:** Ándin urasi tumigkané tô miting?  
**Conflict type:** C SAME SOURCE - DIFFERENT CONTEXT

### OLD

- English: What time does the meeting start?
- Filipino: Anong oras magsisimula ang pulong
- Cebuano: Unsang orasa mosugod ang miting?

### NEW

- English: What time does the meeting start?
- Filipino: Anong oras magsisimula ang meeting
- Cebuano: Unsang orasa mosugod ang miting?
- New row: 1158

### Existing evidence

| Resource | Row | Exact source | English / Filipino / Cebuano | Status or governance |
| --- | ---: | --- | --- | --- |
| Runtime JSON | 736 | Ándin urasi tumigkané tô miting? | What time does the meeting start? / Anong oras magsisimula ang pulong / Unsang orasa mosugod ang miting? | active runtime, development-unverified |
| Runtime JSON | 737 | Ándin urasi tumigkané tô miting? | What time does the meeting start? / miting? / Unsang orasa mosugod ang miting? | active runtime, development-unverified; additional fragmentary variant |
| Legacy archive | 738, 739 | Same two old variants | legacy-unverified |
| PhrasebookEntry | 735, 736 | Same two old variants | active; pending; not runtime-approved; needs-review; rev 1 each; reviews 0 |

Independent resources supporting the full OLD `pulong` tuple: **3**. Supporting the exact NEW `meeting` tuple: **0**. A separate fragmentary `miting?` variant has three-resource replication but does not exactly support the new full Filipino sentence.

**Problem:** `pulong` versus code-switched `meeting` is a register/governance choice, and existing resources also preserve a fragmentary target.  
**Recommendation:** MANUAL_LINGUISTIC_REVIEW  
**Confidence:** LOW  
**Reason:** Both full sentences are plausible; verified evidence is absent, and the legacy fragment should be resolved in the same human decision.  
**HUMAN DECISION:**

---

## Human next action

Record exactly one decision and note for each of the 14 review IDs. A qualified Bagobo-Tagabawa reviewer should address the LOW-confidence contextual decisions first, while a data steward can confirm the HIGH-confidence cross-language defects. Do not apply those decisions to either candidate until a later, separately approved phase produces a new candidate and dry-run.
