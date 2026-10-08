# Phase 3 operation notes

## Translation data policy

Set `TRANSLATION_DATA_MODE=verified_only` for a release. This mode loads only
governed entries that are verified, approved for runtime, public, licensed,
and culturally eligible. It fails closed when no such entries exist.

`development_unverified` is the default for local development. Its outputs
include unverified provenance and must not be represented as linguistic
approval. Pending governed imports are never loaded as approved runtime data.

Fuzzy matching is a suggestion only. Configure `TRANSLATION_FUZZY_THRESHOLD`
and `TRANSLATION_FUZZY_SHORT_THRESHOLD`; the latter defaults to a stricter
value. Fuzzy results require review and preserve the candidate term and score.

## Evaluation

Use only authorized or synthetic fixtures:

```powershell
python manage.py evaluate_translation_pipeline --dataset path\to\fixture.json --source-language english --target-language tagabawa --output docs\phase3\evaluation.json --include-ocr --include-layout
```

Fixture JSON may be `{"cases": [...]}`. A case can include `source_text`,
`source_language`, `target_language`, `expected_text`, and
`human_reviewed: true`. The command separates technical match measurements
from the subset with human-validated expectations. It never reports one
combined translation-accuracy score.

## OCR and review

OCR corrections are append-only `OCRCorrection` records; they do not alter
the original OCR output or upload. Unknown segments remain visible as source
text and have a private `UnknownTranslationRecord`. Review manifests are only
available to the job owner. The `?review=1` preview is available to staff or
validators and shows segment identifiers and accessible † markers.

Bagobo-Tagabawa does not have a validated Tesseract language pack in this
application. An English OCR fallback is warned about and must not be called
native Bagobo-Tagabawa OCR.

## Rollback

1. Deploy the previous application revision.
2. Reverse migration `translator 0011` only after exporting any required OCR
   corrections and unknown-review records: `python manage.py migrate translator 0010`.
3. Keep uploaded originals and generated artifacts; this migration does not
   modify or delete them.
4. Set `TRANSLATION_DATA_MODE=development_unverified` only for a controlled
   development rollback. Do not use it as a production fallback for
   `verified_only`.
