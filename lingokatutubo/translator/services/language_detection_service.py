"""
Language Detection Service for LingoKatutubo
Detects Bagobo-Tagabawa, Filipino, English, and Cebuano
"""

import re
from typing import Dict, List, Optional
from collections import Counter

from .display_utils import clean_invisible_unicode


SUPPORTED_LANGUAGES = ["english", "tagabawa", "filipino", "cebuano"]

# Maps langdetect codes -> our internal names
_LANGDETECT_MAP = {
    "en": "english",
    "tl": "filipino",
    "fil": "filipino",
    "ceb": "cebuano",
}

# langdetect ships no Cebuano profile, so Cebuano text is otherwise reported
# as Tagalog/Filipino. These marker words separate Cebuano from Filipino.
# STRONG markers are distinctively Cebuano (their Filipino equivalents differ:
# unsa/ano, kaayo/napaka-, karon/ngayon, buntag/umaga, ...). WEAK markers also
# occur in Filipino, so they only ever *support* a strong match and never
# trigger Cebuano detection on their own.
_CEBUANO_STRONG_MARKERS = {
    "unsa", "unsaon", "kinsa", "ngano", "diin",
    "kaayo", "ug", "og", "nimo", "nako", "kanimo", "kanako",
    "dili", "kini", "karon", "unya", "gyud", "jud", "bitaw", "naa",
    "maayong", "buntag", "gabii", "kaninyong",
    "pinulungan", "kahibalo", "magsulti", "mananap",
}
_CEBUANO_WEAK_MARKERS = {"nga", "man", "mo", "inyong", "ba", "ta"}


class LanguageDetectionService:
    """
    Multi-language detection supporting Bagobo-Tagabawa, Filipino, English, Cebuano.
    Uses dictionary matching for Tagabawa (not in langdetect) and langdetect
    for the other three.
    """

    def __init__(self, translation_dataset=None):
        self.dataset = translation_dataset
        self.tagabawa_words: set = self._load_tagabawa_dictionary()

    # ------------------------------------------------------------------
    # Dictionary loading
    # ------------------------------------------------------------------

    def _load_tagabawa_dictionary(self) -> set:
        if not self.dataset or not self.dataset.is_loaded:
            return set()
        words: set = set()
        for entry in self.dataset.data:
            text = entry.get("tagabawa_source", "").lower()
            if text:
                words.update(re.findall(r"\b\w+\b", text))
        return words

    def reload_dictionary(self):
        """Call after dataset is loaded to refresh the Tagabawa word list."""
        self.tagabawa_words = self._load_tagabawa_dictionary()

    # ------------------------------------------------------------------
    # Core detection
    # ------------------------------------------------------------------

    def detect_language(
        self,
        text: str,
        fallback: str = "english",
    ) -> Dict:
        """
        Detect the language of a single text block.

        Returns:
            {
              "language": str,
              "confidence": float,
              "method": "dictionary" | "cebuano_markers" | "langdetect" | "fallback",
              "alternatives": list
            }
        """
        text = clean_invisible_unicode(text)
        if not text or not text.strip():
            return {"language": fallback, "confidence": 0.0,
                    "method": "fallback", "alternatives": []}

        text_clean = text.strip()

        # 1. Dictionary/marker checks for the two languages langdetect cannot
        # identify. Both are evaluated so shared cognates cannot short-circuit
        # one before the other is considered; the stronger signal wins, and
        # ties keep the dataset-driven Tagabawa result.
        tagabawa = self._check_tagabawa(text_clean)
        cebuano = self._check_cebuano(text_clean)

        if tagabawa["is_match"] and not (
            cebuano["is_match"] and cebuano["confidence"] > tagabawa["confidence"]
        ):
            return {
                "language": "tagabawa",
                "confidence": tagabawa["confidence"],
                "method": "dictionary",
                "alternatives": [],
            }
        if cebuano["is_match"]:
            return {
                "language": "cebuano",
                "confidence": cebuano["confidence"],
                "method": "cebuano_markers",
                "alternatives": [],
            }

        # 2. Use langdetect for the other three
        try:
            from langdetect import detect_langs, LangDetectException  # type: ignore
            probs = detect_langs(text_clean)
            if not probs:
                raise LangDetectException(0, "empty")

            primary = probs[0]
            lang = _LANGDETECT_MAP.get(primary.lang, "unknown")

            if lang == "unknown":
                return {"language": fallback, "confidence": 0.3,
                        "method": "fallback", "alternatives": []}

            alternatives = []
            for p in probs[1:3]:
                alt = _LANGDETECT_MAP.get(p.lang, "")
                if alt and alt != "unknown":
                    alternatives.append({"language": alt, "confidence": p.prob})

            return {
                "language": lang,
                "confidence": primary.prob,
                "method": "langdetect",
                "alternatives": alternatives,
            }

        except Exception:
            return {"language": fallback, "confidence": 0.0,
                    "method": "fallback", "alternatives": []}

    def _check_tagabawa(self, text: str) -> Dict:
        if not self.tagabawa_words:
            return {"is_match": False, "confidence": 0.0, "matched_words": 0}

        text_words = set(re.findall(r"\b\w+\b", text.lower()))
        if not text_words:
            return {"is_match": False, "confidence": 0.0, "matched_words": 0}

        matched = text_words & self.tagabawa_words
        ratio = len(matched) / len(text_words)
        # The Tagabawa word set is built from whole dataset phrases, so it
        # contains particles shared with Filipino/Cebuano. A single common
        # word must never classify a short caption as Tagabawa: require
        # either broad evidence (>= 4 matched words) or, for short text,
        # a majority of matched words (>= 2 matched at >= 50% coverage).
        is_match = (len(matched) >= 4 and ratio > 0.30) or (
            len(matched) >= 2 and ratio >= 0.50
        )
        return {
            "is_match": is_match,
            "confidence": min(ratio * 1.5, 1.0),
            "matched_words": len(matched),
        }

    def _check_cebuano(self, text: str) -> Dict:
        """Marker-word heuristic for Cebuano, which langdetect cannot detect.

        Fires only with at least one distinctively Cebuano (strong) marker:
        two strong markers always match; a single strong marker needs either
        a supporting weak marker or a high marker density (short captions).
        Weak markers alone never match, because Filipino shares them.
        """
        text_words = set(re.findall(r"\b\w+\b", text.lower()))
        if not text_words:
            return {"is_match": False, "confidence": 0.0, "strong_matches": 0}

        strong = len(text_words & _CEBUANO_STRONG_MARKERS)
        weak = len(text_words & _CEBUANO_WEAK_MARKERS)
        marker_ratio = (strong + weak) / len(text_words)

        is_match = strong >= 2 or (
            strong == 1 and (weak >= 1 or marker_ratio >= 0.25)
        )
        return {
            "is_match": is_match,
            "confidence": min(1.0, 0.6 + 0.1 * strong) if is_match else 0.0,
            "strong_matches": strong,
        }

    # ------------------------------------------------------------------
    # Document-level detection
    # ------------------------------------------------------------------

    def detect_document_language(
        self,
        text_blocks: List[str],
        min_confidence: float = 0.5,
    ) -> Dict:
        """
        Determine the primary language of a document from multiple text samples.

        Returns:
            {
              "primary_language": str,
              "confidence": float,
              "is_mixed": bool,
              "language_distribution": dict
            }
        """
        if not text_blocks:
            return {
                "primary_language": "english",
                "confidence": 0.0,
                "is_mixed": False,
                "language_distribution": {},
            }

        detected = [
            r["language"]
            for block in text_blocks
            if block.strip()
            for r in [self.detect_language(block)]
            if r["confidence"] >= min_confidence
        ]

        if not detected:
            return {
                "primary_language": "english",
                "confidence": 0.0,
                "is_mixed": True,
                "language_distribution": {},
            }

        counts = Counter(detected)
        primary, count = counts.most_common(1)[0]
        consensus = count / len(detected)
        is_mixed = sum(
            1 for c in counts.values() if c / len(detected) > 0.20
        ) > 1

        return {
            "primary_language": primary,
            "confidence": consensus,
            "is_mixed": is_mixed,
            "language_distribution": dict(counts),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_dataset_key(self, language: str) -> str:
        return f"{language}_source"


# Singleton
_service: Optional[LanguageDetectionService] = None


def get_language_detection_service(
    translation_dataset=None,
) -> LanguageDetectionService:
    global _service
    if _service is None:
        _service = LanguageDetectionService(translation_dataset)
    elif translation_dataset is not None and not _service.tagabawa_words:
        _service.dataset = translation_dataset
        _service.reload_dictionary()
    return _service

