"""Presentation-only download names; never change uploads or stored output paths."""

import math
from pathlib import PureWindowsPath
import re
import unicodedata


_LANGUAGE_CODES = {
    'english': 'EN', 'en': 'EN',
    'tagabawa': 'TBW', 'bagobo-tagabawa': 'TBW', 'bagobo tagabawa': 'TBW', 'tbw': 'TBW',
    'filipino': 'FIL', 'tagalog': 'FIL', 'fil': 'FIL', 'tl': 'FIL',
    'cebuano': 'CEB', 'bisaya': 'CEB', 'ceb': 'CEB',
}


def _language_code(value):
    return _LANGUAGE_CODES.get(str(value or '').strip().casefold())


def _source_code(job):
    source = str(job.source_language or '').strip().casefold()
    if source not in {'', 'auto', 'automatic'}:
        return _language_code(source) or 'UNKNOWN'
    metadata = job.metadata if isinstance(job.metadata, dict) else {}
    confidence = metadata.get('detection_confidence')
    try:
        score = float(confidence) if not isinstance(confidence, bool) else float('nan')
    except (TypeError, ValueError, OverflowError):
        score = float('nan')
    # Mirror the detector's existing document-confidence floor for naming only.
    # Mixed/zero-confidence fallback labels must not become asserted languages.
    if math.isfinite(score) and 0.5 <= score <= 1 and not metadata.get('is_mixed_language'):
        return _language_code(metadata.get('detected_language')) or 'AUTO'
    return 'AUTO'


def _safe_stem(filename):
    name = unicodedata.normalize('NFC', str(filename or '')).replace('\\', '/').rsplit('/', 1)[-1]
    name = re.sub(r'(?:\.(?:pdf|docx))+$', '', name, flags=re.IGNORECASE)
    name = ''.join('-' if unicodedata.category(c).startswith('C') or c in '<>:"/\\|?*' else c for c in name)
    name = re.sub(r'\s+', ' ', name).strip(' .-')
    # Leave room for language suffixes, encoding, and common filesystem limits.
    name = name[:180]
    while len(name.encode('utf-8')) > 180:
        name = name[:-1]
    name = name.rstrip(' .-') or 'document'
    if PureWindowsPath(name).is_reserved():
        name = '_' + name
    return name


def translated_download_filename(job, *, bilingual=False):
    stem = _safe_stem(job.original_filename)
    source = _source_code(job)
    target = _language_code(job.target_language) or 'UNKNOWN'
    variant = '_bilingual' if bilingual else ''
    return f'{stem}_{source}_to_{target}{variant}.pdf'
