"""
Translation dataset loader for LingoKatutubo phrasebook / translation memory.
Supports cross-lingual lookup between:
  English, Filipino, Cebuano, and Bagobo-Tagabawa.

This dataset is intentionally used as a phrasebook first. It is not large
enough to claim high-accuracy neural translation by itself.

Loads from (in priority order):
  1. translation_data.json  (utf-8-sig to handle BOM)
  2. datasets/cleaned/cross_lingual_cleaned_v1.csv for the default runtime
     dataset only
  3. Any .csv file in the same directory if JSON is unavailable
  4. Any .xlsx file in the same directory if JSON/CSV is unavailable
"""

import csv as _csv
import difflib
import glob as _glob
import json
import os
import re
import unicodedata
from typing import Dict, List, Optional

from .display_utils import clean_invisible_unicode, safe_print
from .translation_result import make_result

SUPPORTED_LANGS = ["english", "tagabawa", "filipino", "cebuano"]
UNKNOWN_FOR_REVIEW = "[UNKNOWN_FOR_REVIEW]"

_LANG_ALIASES = {
    "bagobo": "tagabawa",
    "tagabawa": "tagabawa",
    "bagobo-tagabawa": "tagabawa",
    "bagobo_tagabawa": "tagabawa",
    "bagobo tagabawa": "tagabawa",
    "bgs": "tagabawa",
    "english": "english",
    "en": "english",
    "eng": "english",
    "filipino": "filipino",
    "tagalog": "filipino",
    "fil": "filipino",
    "tgl": "filipino",
    "cebuano": "cebuano",
    "ceb": "cebuano",
    "bisaya": "cebuano",
    "visayan": "cebuano",
}

# --- Column normalization for CSV/Excel loaders ---
_COL_ALIASES = {
    "tagalog": "filipino_source",
    "tagalog text": "filipino_source",
    "tagalog source": "filipino_source",
    "bagobo": "tagabawa_source",
    "bagobo text": "tagabawa_source",
    "bagobo source": "tagabawa_source",
    "bagobo-tagabawa": "tagabawa_source",
    "bagobo_tagabawa": "tagabawa_source",
    "bagobo tagabawa": "tagabawa_source",
    "bagobo tagabawa text": "tagabawa_source",
    "bgs": "tagabawa_source",
    "en": "english_source",
    "eng": "english_source",
    "english text": "english_source",
    "english source": "english_source",
    "fil": "filipino_source",
    "tgl": "filipino_source",
    "ceb": "cebuano_source",
    "cebuano text": "cebuano_source",
    "cebuano source": "cebuano_source",
    "bisaya": "cebuano_source",
    "visayan": "cebuano_source",
}


def _normalize_column(header: str) -> Optional[str]:
    """Map a raw CSV/Excel column header to its canonical {lang}_source key."""
    raw = str(header or "").strip().lower()
    if raw in (f"{l}_source" for l in SUPPORTED_LANGS):
        return raw

    h = _normalize_alias_key(header)
    if h in _COL_ALIASES:
        return _COL_ALIASES[h]
    canonical_lang = _normalize_lang(h)
    if canonical_lang in SUPPORTED_LANGS:
        return f"{canonical_lang}_source"
    return None


def _normalize_alias_key(value: str) -> str:
    return re.sub(r"\s+", " ", clean_invisible_unicode(value).strip().lower().replace("_", " "))


def _strip_diacritics(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def _normalize_lookup_text(value: str, *, strip_diacritics: bool = False) -> str:
    text = clean_invisible_unicode(value).strip().lower()
    if strip_diacritics:
        text = _strip_diacritics(text)
    # Underscore runs are fill-in-the-blank filler from worksheets/forms
    # ("Kahibalo ka ba magsulti ug Tagalog? ____________"), not language.
    # Underscores count as \w so the punctuation strip below keeps them;
    # convert them to spaces first so normalized variants can match the
    # dataset phrase. Index keys are built with this same function, so
    # lookup and index stay consistent.
    text = re.sub(r"_+", " ", text)
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _lookup_variants(value: str) -> List[str]:
    raw = clean_invisible_unicode(value).strip().lower()
    variants = [
        raw,
        _normalize_lookup_text(value),
        _normalize_lookup_text(value, strip_diacritics=True),
    ]
    output: List[str] = []
    for variant in variants:
        if variant and variant not in output:
            output.append(variant)
    return output


# Straight and curly quote characters that extraction may glue onto phrases.

SUPPORTED_LANGS = ["english", "tagabawa", "filipino", "cebuano"]
UNKNOWN_FOR_REVIEW = "[UNKNOWN_FOR_REVIEW]"

_LANG_ALIASES = {
    "bagobo": "tagabawa",
    "tagabawa": "tagabawa",
    "bagobo-tagabawa": "tagabawa",
    "bagobo_tagabawa": "tagabawa",
    "bagobo tagabawa": "tagabawa",
    "bgs": "tagabawa",
    "english": "english",
    "en": "english",
    "eng": "english",
    "filipino": "filipino",
    "tagalog": "filipino",
    "fil": "filipino",
    "tgl": "filipino",
    "cebuano": "cebuano",
    "ceb": "cebuano",
    "bisaya": "cebuano",
    "visayan": "cebuano",
}

# --- Column normalization for CSV/Excel loaders ---
_COL_ALIASES = {
    "tagalog": "filipino_source",
    "tagalog text": "filipino_source",
    "tagalog source": "filipino_source",
    "bagobo": "tagabawa_source",
    "bagobo text": "tagabawa_source",
    "bagobo source": "tagabawa_source",
    "bagobo-tagabawa": "tagabawa_source",
    "bagobo_tagabawa": "tagabawa_source",
    "bagobo tagabawa": "tagabawa_source",
    "bagobo tagabawa text": "tagabawa_source",
    "bgs": "tagabawa_source",
    "en": "english_source",
    "eng": "english_source",
    "english text": "english_source",
    "english source": "english_source",
    "fil": "filipino_source",
    "tgl": "filipino_source",
    "ceb": "cebuano_source",
    "cebuano text": "cebuano_source",
    "cebuano source": "cebuano_source",
    "bisaya": "cebuano_source",
    "visayan": "cebuano_source",
}


def _normalize_column(header: str) -> Optional[str]:
    """Map a raw CSV/Excel column header to its canonical {lang}_source key."""
    raw = str(header or "").strip().lower()
    if raw in (f"{l}_source" for l in SUPPORTED_LANGS):
        return raw

    h = _normalize_alias_key(header)
    if h in _COL_ALIASES:
        return _COL_ALIASES[h]
    canonical_lang = _normalize_lang(h)
    if canonical_lang in SUPPORTED_LANGS:
        return f"{canonical_lang}_source"
    return None


def _normalize_alias_key(value: str) -> str:
    return re.sub(r"\s+", " ", clean_invisible_unicode(value).strip().lower().replace("_", " "))


def _strip_diacritics(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def _normalize_lookup_text(value: str, *, strip_diacritics: bool = False) -> str:
    text = clean_invisible_unicode(value).strip().lower()
    if strip_diacritics:
        text = _strip_diacritics(text)
    # Underscore runs are fill-in-the-blank filler from worksheets/forms
    # ("Kahibalo ka ba magsulti ug Tagalog? ____________"), not language.
    # Underscores count as \w so the punctuation strip below keeps them;
    # convert them to spaces first so normalized variants can match the
    # dataset phrase. Index keys are built with this same function, so
    # lookup and index stay consistent.
    text = re.sub(r"_+", " ", text)
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _lookup_variants(value: str) -> List[str]:
    raw = clean_invisible_unicode(value).strip().lower()
    variants = [
        raw,
        _normalize_lookup_text(value),
        _normalize_lookup_text(value, strip_diacritics=True),
    ]
    output: List[str] = []
    for variant in variants:
        if variant and variant not in output:
            output.append(variant)
    return output


# Straight and curly quote characters that extraction may glue onto phrases.
_QUOTE_CHARS = "\"'“”‘’"

# Sentence boundary for safe re-segmentation of extracted lines: after a
# terminal mark, before whitespace, a quote character, or an uppercase letter
# (extraction sometimes drops the space entirely: "masabtan.Makasulti").
_SENTENCE_BOUNDARY_RE = re.compile(
    r"(?<=[.?!])(?=[\s\"'“”‘’A-ZÀ-Ý])"
)


def _split_sentence_parts(text: str) -> List[str]:
    """Split an extracted line into sentence-like lookup candidates.

    Surrounding quotes and whitespace are stripped from each part; parts with
    no letters or digits (dangling quotes, underscore blanks) are dropped as
    extraction noise. Returns [] when the line does not split into at least
    two candidate parts.
    """
    cleaned = clean_invisible_unicode(text)
    raw_parts = _SENTENCE_BOUNDARY_RE.split(cleaned)
    if len(raw_parts) < 2 and any(d in cleaned for d in (",", ";")):
        raw_parts = re.split(r"[,;]\s*", cleaned)
    parts = []
    for raw_part in raw_parts:
        candidate = raw_part.strip().strip(_QUOTE_CHARS + " \t").strip()
        # \w includes underscores, so require a real letter or digit.
        if re.search(r"[^\W_]", candidate, flags=re.UNICODE):
            parts.append(candidate)
    return parts if len(parts) >= 2 else []


class TranslationDataset:
    """Manages cross-lingual phrase lookups from the multilingual phrasebook."""

    def __init__(
        self,
        dataset_path: Optional[str] = None,
        include_default_corpus: Optional[bool] = None,
        include_validated_imports: Optional[bool] = None,
        validated_imports_dir: Optional[str] = None,
        data_mode: Optional[str] = None,
    ):
        default_runtime_dataset = dataset_path is None
        # Runtime data policy is deliberately fail-closed.  In verified_only
        # mode there is no fallback to the legacy phrasebook/corpus.
        configured_mode = data_mode or os.environ.get(
            "TRANSLATION_DATA_MODE", "development_unverified"
        )
        self.data_mode = configured_mode.strip().lower()
        if self.data_mode not in {"development_unverified", "development_resources", "verified_only"}:
            raise ValueError(
                "TRANSLATION_DATA_MODE must be development_unverified, development_resources, or verified_only"
            )
        self.fuzzy_threshold = float(os.environ.get("TRANSLATION_FUZZY_THRESHOLD", "0.90"))
        self.fuzzy_short_threshold = float(os.environ.get("TRANSLATION_FUZZY_SHORT_THRESHOLD", "0.97"))
        self.include_default_corpus = (
            default_runtime_dataset
            if include_default_corpus is None
            else bool(include_default_corpus)
        )
        # SME-validated phrasebook exports (datasets/validated/*.csv) join the
        # runtime dataset additively. Isolated datasets (tests, training
        # exports) stay unaffected unless they opt in explicitly.
        self.include_validated_imports = (
            default_runtime_dataset
            if include_validated_imports is None
            else bool(include_validated_imports)
        )
        self.validated_imports_dir = validated_imports_dir

        if dataset_path is None:
            base = os.path.dirname(__file__)
            candidates = [
                os.path.join(base, "translation_data.json"),
                os.path.join(base, "data", "translation_dataset.json"),
                os.path.join(base, "data", "translation_data.json"),
            ]
            dataset_path = next(
                (p for p in candidates if os.path.exists(p)), candidates[0]
            )

        self.dataset_path = dataset_path
        self.data: List[Dict] = []
        self.metadata: Dict = {}

        # Per-language indices: lang -> normalized_text -> [rows]
        self._phrase_indices: Dict[str, Dict[str, List[Dict]]] = {}

        self.is_loaded = False

        self.load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self):
        if self.data_mode == "verified_only":
            self.data = self._load_runtime_approved_entries()
            if self.data:
                self._build_all_indices()
                self.is_loaded = True
            else:
                safe_print("[Translation] verified_only selected; no runtime-approved governed entries are available.")
            return
        if self.data_mode == "development_resources":
            # This mode is deliberately database-only.  It must never silently
            # merge JSON/CSV/corpus rows with active resource records.
            self.data = self._load_active_resource_entries()
            if self.data:
                self._build_all_indices()
                self.is_loaded = True
                safe_print(f"[Translation] development_resources loaded: {len(self.data)} active entries")
            else:
                safe_print("[Translation] development_resources selected; no active resources are available.")
            return
        # --- Attempt 1: JSON (the configured path) ---
        json_loaded = False
        if os.path.exists(self.dataset_path):
            safe_print(f"[Translation] Loading dataset from: {self.dataset_path}")
            try:
                with open(self.dataset_path, "r", encoding="utf-8-sig") as f:
                    raw = json.load(f)

                # Support three formats:
                # 1. Plain list of row dicts
                # 2. Dict with a "rows" / "entries" / "data" key
                # 3. Metadata-only dict (no phrase rows yet)
                if isinstance(raw, list):
                    self.data = raw
                    self.metadata = {}
                elif isinstance(raw, dict):
                    self.metadata = {k: v for k, v in raw.items()
                                     if not isinstance(v, list) or k in
                                     ("languages", "columns", "cleaning_rules_applied")}
                    for key in ("rows", "entries", "data", "phrases"):
                        candidate_rows = raw.get(key)
                        if not (
                            isinstance(candidate_rows, list)
                            and candidate_rows
                            and isinstance(candidate_rows[0], dict)
                        ):
                            continue
                        if any(
                            _normalize_column(str(column_name))
                            for column_name in candidate_rows[0].keys()
                        ):
                            self.data = candidate_rows
                            break

                if self.data:
                    self.data = self._normalize_rows(self.data)
                    json_loaded = True

            except Exception as exc:
                safe_print(f"[Translation] Error loading JSON dataset: {exc}")
        else:
            safe_print(f"[Translation] ERROR: Dataset file not found at {self.dataset_path}")

        # --- Attempt 2: Scan backend directory for CSV/Excel ---
        if not json_loaded:
            base = os.path.dirname(self.dataset_path)
            candidates = self._find_data_files(base)
            for candidate_path in candidates:
                ext = os.path.splitext(candidate_path)[1].lower()
                if ext == ".csv":
                    self.data = self._load_csv(candidate_path)
                elif ext in (".xlsx", ".xls"):
                    self.data = self._load_excel(candidate_path)
                if self.data:
                    self.data = self._normalize_rows(self.data)
                    break

        if self.include_default_corpus:
            self._load_default_text_corpus()

        if self.include_validated_imports:
            self._load_validated_imports()

        # --- Common outcome ---
        if not self.data:
            safe_print(
                "[Translation] Dataset file has no phrase rows yet. "
                "Add a 'rows' array to translation_data.json, or place a "
                "translation_data.csv / phrasebook.csv in the backend folder."
            )
            return

        self._build_all_indices()
        self.is_loaded = True
        safe_print(f"[Translation] Dataset loaded: {len(self.data)} entries")
        sample_lang = next(
            (lang for lang in SUPPORTED_LANGS if self._phrase_indices.get(lang)),
            "",
        )
        sample_key = (
            next(iter(self._phrase_indices[sample_lang]))
            if sample_lang
            else ""
        )
        if sample_key:
            safe_print(
                f"[Translation] Sample normalized key ({sample_lang}): {sample_key!r}"
            )
        safe_print("[Translation] Sample translations (first 5):")
        for i, row in enumerate(self.data[:5]):
            en = row.get("english_source", "")
            tg = row.get("tagabawa_source", "")
            fi = row.get("filipino_source", "")
            safe_print(f"  [{i+1}] en={en!r}  tagabawa={tg!r}  filipino={fi!r}")

    @staticmethod
    def _load_runtime_approved_entries() -> List[Dict]:
        """Load only governed records explicitly eligible for public runtime.

        Importing models lazily keeps the standalone dataset tools usable.  A
        database or Django setup error is treated as an empty approved set,
        never as permission to use unverified data.
        """
        try:
            from translator.models import PhrasebookEntry
            from translator.services.governance import is_runtime_eligible
            rows = []
            for entry in PhrasebookEntry.objects.filter(
                is_active=True, is_approved_for_runtime=True,
                validation_status="verified",
            ):
                if not is_runtime_eligible(entry):
                    continue
                rows.append({
                    "id": str(entry.pk), "english_source": entry.english,
                    "tagabawa_source": entry.tagabawa, "filipino_source": entry.filipino,
                    "cebuano_source": entry.cebuano, "source": "governed_runtime",
                    "validation_status": "verified", "runtime_approval_status": "approved",
                    "revision_number": entry.revision_number,
                    "access_restriction": entry.access_restriction,
                })
            return rows
        except Exception as exc:
            safe_print(f"[Translation] verified_only governed dataset unavailable: {exc}")
            return []

    @staticmethod
    def _load_active_resource_entries() -> List[Dict]:
        """Load active PhrasebookEntry records, without governance filtering.

        This is a distinct development source intended for the Translation
        Resources UI.  It does not fall through to legacy JSON/CSV sources.
        """
        try:
            from translator.models import PhrasebookEntry

            return [
                {
                    "id": str(entry.pk),
                    "english_source": entry.english,
                    "tagabawa_source": entry.tagabawa,
                    "filipino_source": entry.filipino,
                    "cebuano_source": entry.cebuano,
                    "source": "database_resource",
                    "validation_status": entry.validation_status,
                    "runtime_approval_status": "not_approved",
                    "revision_number": entry.revision_number,
                    "access_restriction": entry.access_restriction,
                }
                for entry in PhrasebookEntry.objects.filter(is_active=True)
            ]
        except Exception as exc:
            safe_print(f"[Translation] development_resources database unavailable: {exc}")
            return []

    def _load_default_text_corpus(self) -> None:
        """Append the prepared cleaned text corpus to the runtime phrasebook.

        Explicit dataset_path callers, such as tests and training export
        scripts, stay isolated unless they opt in via include_default_corpus.
        """
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        corpus_path = os.path.join(
            project_root,
            "datasets",
            "cleaned",
            "cross_lingual_cleaned_v1.csv",
        )
        if not os.path.exists(corpus_path):
            safe_print(f"[Translation] Text corpus not found at: {corpus_path}")
            return

        rows = self._normalize_rows(self._load_csv(corpus_path))
        for row in rows:
            row.setdefault("source", "text_corpus")
            row.setdefault("dataset_role", "text_corpus_translation_memory")

        if rows:
            self.data.extend(rows)
        safe_print(
            f"[Translation] Text corpus loaded: {len(rows)} entries from {corpus_path}"
        )

    def _load_validated_imports(self) -> None:
        """Append SME-validated phrasebook exports to the runtime dataset.

        Loads every CSV under datasets/validated/ (or the injected directory).
        Fail-safe by design: a malformed file is logged and skipped so it can
        never break base dataset loading — the base JSON/corpus always wins.
        """
        validated_dir = self.validated_imports_dir
        if not validated_dir:
            project_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..")
            )
            validated_dir = os.path.join(project_root, "datasets", "validated")
        if not os.path.isdir(validated_dir):
            return

        for path in sorted(_glob.glob(os.path.join(validated_dir, "*.csv"))):
            try:
                rows = self._normalize_rows(self._load_csv(path))
            except Exception as exc:
                safe_print(
                    f"[Translation] WARNING: skipping malformed validated CSV "
                    f"{path}: {exc}"
                )
                continue
            for row in rows:
                row.setdefault("source", "validated_import")
                row.setdefault("dataset_role", "validated_import")
            if rows:
                self.data.extend(rows)
                safe_print(
                    f"[Translation] Validated imports loaded: {len(rows)} "
                    f"entries from {path}"
                )

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------

    def _find_data_files(self, directory: str) -> List[str]:
        """Return ordered list of candidate CSV/Excel paths to try."""
        preferred_csv = ["translation_data.csv", "phrasebook.csv", "dataset.csv"]
        preferred_xlsx = ["translation_data.xlsx", "phrasebook.xlsx", "dataset.xlsx"]

        found = []
        for name in preferred_csv:
            p = os.path.join(directory, name)
            if os.path.exists(p):
                found.append(p)

        for p in _glob.glob(os.path.join(directory, "*.csv")):
            if p not in found:
                found.append(p)

        for name in preferred_xlsx:
            p = os.path.join(directory, name)
            if os.path.exists(p):
                found.append(p)

        for p in _glob.glob(os.path.join(directory, "*.xlsx")):
            if p not in found:
                found.append(p)

        return found

    # ------------------------------------------------------------------
    # CSV loader
    # ------------------------------------------------------------------

    def _load_csv(self, path: str) -> List[Dict]:
        """Load phrase rows from a CSV file. Returns list of row dicts or []."""
        rows = []
        safe_print(f"[Translation] Loading dataset from: {path}")
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = _csv.DictReader(f)
                if reader.fieldnames is None:
                    safe_print(f"[Translation] ERROR: CSV has no header row: {path}")
                    return []

                # Build column map: csv_header -> canonical_key
                col_map = {}
                for h in reader.fieldnames:
                    canonical = _normalize_column(h)
                    if canonical:
                        col_map[h] = canonical

                if not col_map:
                    safe_print(f"[Translation] ERROR: No recognized language columns in CSV: {path}")
                    safe_print(f"[Translation] Found headers: {list(reader.fieldnames)}")
                    safe_print("[Translation] Expected headers like: tagabawa, english, filipino, cebuano")
                    return []

                for raw_row in reader:
                    row = {}
                    for csv_col, raw_value in raw_row.items():
                        val = (raw_value or "").strip()
                        canonical_key = col_map.get(csv_col)
                        if canonical_key:
                            row[canonical_key] = val
                            continue
                        meta_key = _normalize_alias_key(csv_col).replace(" ", "_")
                        if meta_key in {"id", "record_id", "topic", "source", "notes"}:
                            row[meta_key] = val
                    if any(row.values()):
                        rows.append(row)

        except Exception as exc:
            safe_print(f"[Translation] ERROR loading CSV {path}: {exc}")
        return rows

    # ------------------------------------------------------------------
    # Row normalization
    # ------------------------------------------------------------------

    def _normalize_rows(self, rows: List[Dict]) -> List[Dict]:
        """Ensure every supported language is available as {lang}_source.

        The bundled JSON uses plain language keys such as `english` and
        `tagabawa`, while the lookup indices use canonical keys such as
        `english_source` and `tagabawa_source`. CSV/Excel loading already
        produces canonical keys, but normalizing all loaded rows keeps the
        JSON and CSV paths equivalent.
        """
        normalized_rows: List[Dict] = []
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                continue

            row = dict(raw_row)
            for header, value in raw_row.items():
                canonical_key = _normalize_column(str(header))
                if not canonical_key:
                    continue
                current_value = str(row.get(canonical_key, "") or "").strip()
                if current_value:
                    continue
                row[canonical_key] = str(value or "").strip()

            if any(str(row.get(f"{lang}_source", "") or "").strip() for lang in SUPPORTED_LANGS):
                normalized_rows.append(row)

        return normalized_rows

    # ------------------------------------------------------------------
    # Excel loader
    # ------------------------------------------------------------------

    def _load_excel(self, path: str) -> List[Dict]:
        """Load phrase rows from an .xlsx file. Returns list of row dicts or []."""
        rows = []
        safe_print(f"[Translation] Loading dataset from: {path}")
        try:
            import openpyxl  # type: ignore
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb.active

            raw_headers = [
                str(cell.value or "").strip()
                for cell in next(ws.iter_rows(max_row=1))
            ]

            col_map = {}  # column index -> canonical_key
            for idx, h in enumerate(raw_headers):
                canonical = _normalize_column(h)
                if canonical:
                    col_map[idx] = canonical

            if not col_map:
                safe_print(f"[Translation] ERROR: No recognized language columns in Excel: {path}")
                safe_print(f"[Translation] Found headers: {raw_headers}")
                safe_print("[Translation] Expected headers like: tagabawa, english, filipino, cebuano")
                wb.close()
                return []

            for raw_row in ws.iter_rows(min_row=2, values_only=True):
                row = {}
                for idx, canonical_key in col_map.items():
                    val = str(raw_row[idx] or "").strip() if idx < len(raw_row) else ""
                    row[canonical_key] = val
                if any(row.values()):
                    rows.append(row)

            wb.close()
        except ImportError:
            safe_print("[Translation] ERROR: openpyxl not installed. Run: pip install openpyxl>=3.1.0")
        except Exception as exc:
            safe_print(f"[Translation] ERROR loading Excel {path}: {exc}")
        return rows

    # ------------------------------------------------------------------
    # Index building
    # ------------------------------------------------------------------

    def _build_all_indices(self):
        self._phrase_indices = {lang: {} for lang in SUPPORTED_LANGS}

        for row in self.data:
            for lang in SUPPORTED_LANGS:
                text = row.get(f"{lang}_source", "").strip()
                if not text:
                    continue

                # Phrase index
                for norm in _lookup_variants(text):
                    self._phrase_indices[lang].setdefault(norm, []).append(row)

    # ------------------------------------------------------------------
    # Translation
    # ------------------------------------------------------------------

    def translate_phrase(
        self,
        text: str,
        source_lang: str = "english",
        target_lang: str = "tagabawa",
    ) -> str:
        """
        Translate text using exact/normalized dataset matches only.
        Returns original text if no translation is found.
        """
        return self.translate_phrase_with_metadata(
            text,
            source_lang=source_lang,
            target_lang=target_lang,
        )["translated"]

    def translate_phrase_with_metadata(
        self,
        text: str,
        source_lang: str = "english",
        target_lang: str = "tagabawa",
        *,
        _allow_segmentation: bool = True,
    ) -> Dict:
        """
        Translate text and return frontend/API metadata.

        Returns:
            {
              translated,
              method,
              cascade_stage,
              confidence,
              needs_review
            }
        """
        original = clean_invisible_unicode(text).strip()
        if not self.is_loaded or not original:
            self._log_lookup("unknown_for_review", source_lang, target_lang, False)
            return _translation_result(original, "unknown_for_review", 0.0, True, source_text=original,
                                       source_lang=source_lang, target_lang=target_lang,
                                       unknown_tokens=_unknown_tokens(original))

        # Normalize language aliases
        source_lang = _normalize_lang(source_lang)
        target_lang = _normalize_lang(target_lang)

        if source_lang == target_lang:
            self._log_lookup("identity", source_lang, target_lang, True)
            return _translation_result(text, "source_retained", 1.0, source_text=text,
                                       source_lang=source_lang, target_lang=target_lang,
                                       validation_status="not_applicable",
                                       runtime_approval_status="not_applicable")

        target_key = f"{target_lang}_source"
        src_index = self._phrase_indices.get(source_lang, {})

        # Safe terminal punctuation (. ? ! ,) is set aside purely for
        # re-attachment to the translated result below. Lookup itself still
        # runs against the untouched original text -- the normalized/diacritic
        # variants already ignore punctuation for matching purposes, and
        # leaving the raw/exact variant untouched preserves exact_phrase
        # matches for dataset rows that legitimately carry the same trailing
        # punctuation as the query (e.g. a corpus sentence stored with its
        # own period).
        _, trailing_punctuation = _split_trailing_punctuation(original)

        # 1. Exact/normalized dataset match. The first variant is the cleaned
        # raw text; later variants are punctuation/case/diacritic tolerant.
        for variant_index, norm in enumerate(_lookup_variants(original)):
            match = _first_result(src_index.get(norm, []), target_key)
            if match:
                result, row = match
                method = "exact_phrase" if variant_index == 0 else "normalized_phrase"
                self._log_lookup(method, source_lang, target_lang, True, key=norm)
                translated = _reattach_trailing_punctuation(
                    _preserve_case(original, result), trailing_punctuation
                )
                return _translation_result(
                    translated,
                    method,
                    1.0,
                    source_text=original,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    row=row,
                    matched_term=norm,
                )

        # 2. Whole-line lookup missed: extraction sometimes fuses two dataset
        # sentences into one line ("masabtan.Makasulti...") or merges a
        # question with its quoted answer. Split on sentence boundaries and
        # translate the parts — but only claim a translation when EVERY
        # linguistic part matches the dataset. A line with any unmatched part
        # stays original and flagged, so segmentation can never invent text.
        if _allow_segmentation:
            segmented = self._translate_segmented(original, source_lang, target_lang)
            if segmented is not None:
                return segmented

        fuzzy = self._translate_fuzzy(original, source_lang, target_lang, src_index, target_key)
        if fuzzy is not None:
            return fuzzy

        self._log_lookup("unknown_for_review", source_lang, target_lang, False)
        return _translation_result(original, "unknown_for_review", 0.0, True, source_text=original,
                                   source_lang=source_lang, target_lang=target_lang,
                                   unknown_tokens=_unknown_tokens(original))

    def _translate_fuzzy(self, original: str, source_lang: str, target_lang: str,
                         src_index: Dict[str, List[Dict]], target_key: str) -> Optional[Dict]:
        """Conservative final lookup stage; punctuation/numbers never fuzzy-match."""
        key = _normalize_lookup_text(original, strip_diacritics=True)
        if not key or not re.search(r"[^\W_]", key, re.UNICODE) or not re.search(r"[A-Za-zÀ-ſ]", key):
            return None
        if re.fullmatch(r"[\d\W_]+", original, re.UNICODE):
            return None
        threshold = self.fuzzy_short_threshold if len(key) < 5 else self.fuzzy_threshold
        candidate_key = None
        score = 0.0
        # get_close_matches does not disclose the score, so calculate it and
        # retain both the matched term and score as review evidence.
        for indexed_key in src_index:
            if not indexed_key or abs(len(indexed_key) - len(key)) > max(3, len(key) // 3):
                continue
            candidate_score = difflib.SequenceMatcher(None, key, indexed_key).ratio()
            if candidate_score > score:
                candidate_key, score = indexed_key, candidate_score
        if candidate_key is None or score < threshold:
            return None
        match = _first_result(src_index.get(candidate_key, []), target_key)
        if not match:
            return None
        translated, row = match
        self._log_lookup("fuzzy_match", source_lang, target_lang, True, key=candidate_key)
        verified = str(row.get("validation_status", "")).lower() == "verified"
        return _translation_result(
            _preserve_case(original, translated), "fuzzy_match", score,
            # Fuzzy suggestions remain review-required unless a later policy
            # explicitly permits verified automatic fuzzy use.
            True, source_text=original, source_lang=source_lang, target_lang=target_lang, row=row,
            matched_term=candidate_key, match_score=score,
            extra_warnings=["Fuzzy match requires validation before linguistic use."],
        )

    def candidate_matches(self, text: str, source_lang: str, target_lang: str, limit: int = 3) -> List[Dict]:
        """Return diagnostic candidates using the same normalized index as matching.

        This does not affect the translation cascade.  It is only exposed by
        the administrator Match Tester so a resource manager can inspect why
        a fuzzy result was (or was not) available.
        """
        source_lang, target_lang = _normalize_lang(source_lang), _normalize_lang(target_lang)
        key = _normalize_lookup_text(text, strip_diacritics=True)
        target_key = f"{target_lang}_source"
        if not key or source_lang == target_lang:
            return []
        candidates = []
        for indexed_key, rows in self._phrase_indices.get(source_lang, {}).items():
            match = _first_result(rows, target_key)
            if not match:
                continue
            translated, row = match
            candidates.append({
                "source": indexed_key,
                "translation": translated,
                "score": round(difflib.SequenceMatcher(None, key, indexed_key).ratio(), 3),
                "entry_id": row.get("id", ""),
            })
        return sorted(candidates, key=lambda candidate: candidate["score"], reverse=True)[:limit]

    def _translate_segmented(
        self,
        original: str,
        source_lang: str,
        target_lang: str,
    ) -> Optional[Dict]:
        """Translate a fused multi-sentence line part by part, or None.

        Returns a segmented_phrase result only when every part resolves via
        exact_phrase/normalized_phrase. Any unknown part means the caller
        keeps the whole-line unknown_for_review marker — partial hybrid
        output is deliberately not produced, so unknown text always remains
        original and review-flagged.
        """
        parts = _split_sentence_parts(original)
        if not parts:
            return None

        translated_parts: List[str] = []
        for part in parts:
            result = self.translate_phrase_with_metadata(
                part,
                source_lang=source_lang,
                target_lang=target_lang,
                _allow_segmentation=False,
            )
            if result["method"] not in {"exact_phrase", "normalized_phrase"}:
                return None
            translated_parts.append(result["translated"])

        self._log_lookup(
            "segmented_phrase",
            source_lang,
            target_lang,
            True,
            key=" / ".join(parts)[:80],
        )
        sep = ", " if "," in original else "; " if ";" in original else " "
        return _translation_result(
            sep.join(translated_parts),
            "segmented_phrase",
            1.0,
            False,
            source_text=original,
            source_lang=source_lang,
            target_lang=target_lang,
        )

    @staticmethod
    def _log_lookup(
        stage: str,
        source_lang: str,
        target_lang: str,
        matched: bool,
        *,
        key: str = "",
    ) -> None:
        status = "matched" if matched else "missed"
        suffix = f" key={key!r}" if key else ""
        safe_print(
            f"[Translation] Lookup {status}: source={source_lang} "
            f"target={target_lang} stage={stage}{suffix}"
        )

    # ------------------------------------------------------------------
    # Quick helpers used by the API
    # ------------------------------------------------------------------

    def translate_quick(
        self, text: str, source_lang: str = "english", target_lang: str = "tagabawa"
    ) -> Dict:
        result = self.translate_phrase_with_metadata(text, source_lang, target_lang)
        return {
            "original": text,
            "translated": result["translated"],
            "source_language": source_lang,
            "target_language": target_lang,
            "dataset_loaded": self.is_loaded,
            "method": result["method"],
            "confidence": result["confidence"],
            "needs_review": result.get("needs_review", False),
        }


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _normalize_lang(lang: str) -> str:
    normalized = _normalize_alias_key(lang)
    hyphenated = normalized.replace(" ", "-")
    underscored = normalized.replace(" ", "_")
    return (
        _LANG_ALIASES.get(normalized)
        or _LANG_ALIASES.get(hyphenated)
        or _LANG_ALIASES.get(underscored)
        or normalized
    )


def _first_result(rows: List[Dict], key: str) -> Optional[tuple[str, Dict]]:
    for row in rows:
        val = row.get(key, "").strip()
        if val:
            return val, row
    return None


def _translation_result(
    translated: str,
    method: str,
    confidence: float,
    needs_review: Optional[bool] = None,
    *,
    source_text: Optional[str] = None,
    source_lang: str = "",
    target_lang: str = "",
    row: Optional[Dict] = None,
    unknown_tokens: Optional[List[str]] = None,
    matched_term: Optional[str] = None,
    match_score: Optional[float] = None,
    extra_warnings: Optional[List[str]] = None,
) -> Dict:
    if needs_review is None:
        needs_review = method in {"unknown_for_review", "untranslated_needs_review"}
    row = row or {}
    provenance = str(row.get("source") or "legacy_development")
    validation_status = str(row.get("validation_status") or "unverified")
    approval = str(row.get("runtime_approval_status") or "not_approved")
    warnings = list(extra_warnings or [])
    if provenance != "governed_runtime":
        warnings.append("Development resource is unverified; linguistic validation is still required.")
    return make_result(
        source_text=source_text if source_text is not None else translated,
        displayed_text=translated, source_language=source_lang, target_language=target_lang,
        match_method=method, confidence=confidence, review_required=bool(needs_review),
        validation_status=validation_status, runtime_approval_status=approval,
        matched_entry_id=str(row.get("id") or row.get("record_id") or "") or None,
        matched_entry_revision=row.get("revision_number"), unknown_tokens=unknown_tokens,
        warnings=list(dict.fromkeys(warnings)), provenance_status=provenance,
        restriction_status=str(row.get("access_restriction") or "unrestricted"),
        matched_term=matched_term, match_score=match_score,
    )


def _unknown_tokens(text: str) -> List[str]:
    return re.findall(r"[^\W_]+", clean_invisible_unicode(text), flags=re.UNICODE)


def _preserve_case(original: str, translated: str) -> str:
    if not translated:
        return translated
    if original and original[0].isupper():
        return translated[0].upper() + translated[1:]
    return translated


# Terminal punctuation safe to carry across languages unchanged. Internal
# punctuation (e.g. the apostrophe in "I'll") is never touched, since only a
# trailing run of these exact characters is ever captured or re-attached.
_SAFE_TERMINAL_PUNCTUATION = ".?!,"
_TRAILING_PUNCTUATION_RE = re.compile(r"[.?!,]+$")


def _split_trailing_punctuation(text: str) -> "tuple[str, str]":
    """Split safe terminal punctuation from the end of text.

    Returns (core, trailing). `trailing` is the longest trailing run of
    `_SAFE_TERMINAL_PUNCTUATION` found at the end of `text`, to be re-attached
    to the translated output by `_reattach_trailing_punctuation`. `core` is
    `text` with that run (and the whitespace immediately before it) removed;
    callers that only need `trailing` for re-attachment (lookup itself is
    left punctuation-sensitive on its raw/exact variant -- see the call site
    in translate_phrase_with_metadata) can discard it.
    """
    match = _TRAILING_PUNCTUATION_RE.search(text)
    if not match:
        return text, ""
    return text[: match.start()].rstrip(), match.group(0)


def _reattach_trailing_punctuation(translated: str, trailing: str) -> str:
    """Re-attach punctuation captured by `_split_trailing_punctuation`.

    Skips re-attaching if there was nothing captured, if the translation is
    empty, or if the translation already ends in one of the safe terminal
    marks (avoids doubling, e.g. "...mapun..").
    """
    if not trailing or not translated:
        return translated
    if translated[-1] in _SAFE_TERMINAL_PUNCTUATION:
        return translated
    return translated + trailing


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_dataset: Optional[TranslationDataset] = None


def get_translation_dataset() -> TranslationDataset:
    global _dataset
    if _dataset is None:
        _dataset = TranslationDataset()
    return _dataset


def reset_translation_dataset() -> None:
    """Discard the process cache after a deliberate resource management save."""
    global _dataset
    _dataset = None


def translate(text: str, target_lang: str = "tagabawa") -> str:
    return get_translation_dataset().translate_phrase(
        text, source_lang="english", target_lang=target_lang
    )
