"""
PDF reconstruction service - rebuilds PDF with translated text while preserving layout
"""

import fitz  # PyMuPDF
import math
import os
import unicodedata
from typing import List, Dict, Any, Optional, Tuple

from .display_utils import clean_invisible_unicode, safe_print
from .translation_display import get_display_translation_text, is_display_fallback_translation


class ReconstructionService:
    """Rebuilds PDFs with translated text while preserving original layout"""

    READABLE_MIN_FONT_SIZE = 9.0
    MIN_FONT_SIZE = 7.0
    LINE_HEIGHT_FACTOR = 1.12
    HEAVY_SHRINK_RATIO = 0.80
    FALLBACK_REVIEW_TEXT = ""
    BASE14_FONT_ALIASES = {
        "helv": "helv",
        "helvetica": "helv",
        "arial": "helv",
        "arialmt": "helv",
        "calibri": "helv",
        "segoeui": "helv",
        "times": "tiro",
        "timesroman": "tiro",
        "times-roman": "tiro",
        "timesnewroman": "tiro",
        "timesnewromanpsmt": "tiro",
        "tiro": "tiro",
        "cour": "cour",
        "courier": "cour",
        "couriernew": "cour",
        "couriernewpsmt": "cour",
    }
    _unicode_fontfile_checked = False
    _unicode_fontfile_path: Optional[str] = None

    @staticmethod
    def _append_warning(warnings: Optional[List[str]], message: str) -> None:
        if warnings is not None and message and message not in warnings:
            warnings.append(message)

    @classmethod
    def _coerce_translation_value(cls, value: Any, fallback: str) -> str:
        """Support both legacy string translations and dict translation records."""
        fallback = clean_invisible_unicode(fallback)
        if value is None:
            return str(fallback or "")
        if isinstance(value, dict):
            return get_display_translation_text(
                fallback,
                value.get("translated") or value.get("translated_text"),
                value.get("method") or value.get("translation_method"),
                value.get("cascade_stage"),
            )
        return get_display_translation_text(fallback, clean_invisible_unicode(value))

    @classmethod
    def _translation_record_for_line(
        cls,
        translations: Dict[str, Any],
        lookup_key: str,
        original_text: str,
    ) -> Any:
        """Return the raw translation record for a line (dict, str, or None)."""
        candidate_keys = [lookup_key, original_text, original_text.strip()]
        for key in candidate_keys:
            if key and key in translations:
                return translations.get(key)
        return None

    @classmethod
    def _translated_text_for_line(
        cls,
        translations: Dict[str, Any],
        lookup_key: str,
        original_text: str,
    ) -> str:
        """Resolve translated text by layout key first, then by original source text."""
        record = cls._translation_record_for_line(translations, lookup_key, original_text)
        if record is None:
            return str(original_text or "")
        return cls._coerce_translation_value(record, original_text)

    @staticmethod
    def _rect_from_bbox(
        bbox: Any,
        page_rect: fitz.Rect,
        padding: float = 0.0,
    ) -> Optional[fitz.Rect]:
        if not bbox:
            return None
        try:
            x0, y0, x1, y1 = [float(value) for value in list(bbox)[:4]]
        except Exception:
            return None

        # Padding must not turn missing source geometry into a drawable region.
        if not all(math.isfinite(value) for value in (x0, y0, x1, y1)) or x0 == x1 or y0 == y1:
            return None

        left = min(x0, x1) - padding
        right = max(x0, x1) + padding
        top = min(y0, y1) - padding
        bottom = max(y0, y1) + padding

        left = max(page_rect.x0, min(page_rect.x1, left))
        right = max(page_rect.x0, min(page_rect.x1, right))
        top = max(page_rect.y0, min(page_rect.y1, top))
        bottom = max(page_rect.y0, min(page_rect.y1, bottom))

        if right <= left or bottom <= top:
            return None
        return fitz.Rect(left, top, right, bottom)

    @staticmethod
    def _rgb_tuple(value: Any, default: Tuple[float, float, float]) -> Tuple[float, float, float]:
        if value is None:
            return default
        try:
            if isinstance(value, int):
                return (
                    ((value >> 16) & 255) / 255.0,
                    ((value >> 8) & 255) / 255.0,
                    (value & 255) / 255.0,
                )
            values = [float(item) for item in list(value)[:3]]
            if len(values) != 3:
                return default
            if any(item > 1.0 for item in values):
                values = [max(0.0, min(255.0, item)) / 255.0 for item in values]
            return tuple(max(0.0, min(1.0, item)) for item in values)  # type: ignore[return-value]
        except Exception:
            return default

    @classmethod
    def _line_color(cls, line: Dict[str, Any]) -> Tuple[float, float, float]:
        color = line.get("color")
        if color is None:
            spans = line.get("spans") or []
            if spans:
                color = spans[0].get("color")
        return cls._rgb_tuple(color, (0.0, 0.0, 0.0))

    @classmethod
    def _visible_text_color(
        cls,
        line: Dict[str, Any],
        warnings: Optional[List[str]],
        page_number: int,
        block_number: int,
        line_number: int,
    ) -> Tuple[float, float, float]:
        color = cls._line_color(line)
        luminance = (0.2126 * color[0]) + (0.7152 * color[1]) + (0.0722 * color[2])
        if luminance > 0.88:
            cls._append_warning(
                warnings,
                f"Page {page_number}, block {block_number}, line {line_number}: "
                "translated text color was too light for the white mask; using black.",
            )
            return (0.0, 0.0, 0.0)
        return color

    @staticmethod
    def _first_text_span(line: Dict[str, Any]) -> Dict[str, Any]:
        spans = line.get("spans") or []
        return next(
            (
                span
                for span in spans
                if clean_invisible_unicode(span.get("text", "")).strip()
            ),
            spans[0] if spans else {},
        )

    @staticmethod
    def _font_label_for_line(line: Dict[str, Any]) -> str:
        span = ReconstructionService._first_text_span(line)
        return str(line.get("font") or span.get("font") or "")

    @staticmethod
    def _font_flags_for_line(line: Dict[str, Any]) -> int:
        span = ReconstructionService._first_text_span(line)
        flags = line.get("flags")
        if flags is None:
            flags = span.get("flags", 0)
        try:
            return int(flags or 0)
        except Exception:
            return 0

    @staticmethod
    def _font_label_key(font_label: str) -> str:
        if "+" in font_label and font_label.split("+", 1)[0].isupper():
            font_label = font_label.split("+", 1)[1]
        return (
            font_label.lower()
            .replace(" ", "")
            .replace("_", "")
            .replace(",", "")
            .replace(".", "")
        )

    @classmethod
    def _font_style_for_line(cls, line: Dict[str, Any]) -> Dict[str, Any]:
        font_label = cls._font_label_for_line(line)
        font_key = cls._font_label_key(font_label)
        flags = cls._font_flags_for_line(line)

        is_bold = (
            "bold" in font_key
            or "black" in font_key
            or "heavy" in font_key
            or bool(flags & 16)
        )
        is_italic = (
            "italic" in font_key
            or "oblique" in font_key
            or bool(flags & 2)
        )
        is_mono = (
            "mono" in font_key
            or "courier" in font_key
            or "consolas" in font_key
            or bool(flags & 8)
        )
        is_serif = (
            "times" in font_key
            or "serif" in font_key
            or "cambria" in font_key
            or "georgia" in font_key
            or "garamond" in font_key
            or "palatino" in font_key
            or bool(flags & 4)
        )

        return {
            "font_label": font_label,
            "font_key": font_key,
            "family": "mono" if is_mono else "serif" if is_serif else "sans",
            "bold": is_bold,
            "italic": is_italic,
        }

    @classmethod
    def _fallback_fontname_for_style(cls, style: Dict[str, Any]) -> str:
        is_bold = bool(style.get("bold"))
        is_italic = bool(style.get("italic"))
        family = style.get("family")

        if family == "mono":
            if is_bold and is_italic:
                return "cobi"
            if is_bold:
                return "cobo"
            if is_italic:
                return "coit"
            return "cour"

        if family == "serif":
            if is_bold and is_italic:
                return "tibi"
            if is_bold:
                return "tibo"
            if is_italic:
                return "tiit"
            return "tiro"

        if is_bold and is_italic:
            return "hebi"
        if is_bold:
            return "hebo"
        if is_italic:
            return "heit"
        return "helv"

    @classmethod
    def _fontname_for_line(cls, line: Dict[str, Any]) -> str:
        return cls._fallback_fontname_for_style(cls._font_style_for_line(line))

    @classmethod
    def _fontfile_for_style(cls, style: Dict[str, Any]) -> Optional[str]:
        family = style.get("family")
        is_bold = bool(style.get("bold"))
        is_italic = bool(style.get("italic"))

        if family == "serif":
            if is_bold and is_italic:
                names = ["timesbi.ttf", "georgiaz.ttf"]
            elif is_bold:
                names = ["timesbd.ttf", "georgiab.ttf"]
            elif is_italic:
                names = ["timesi.ttf", "georgiai.ttf"]
            else:
                names = ["times.ttf", "georgia.ttf"]
        elif family == "mono":
            if is_bold and is_italic:
                names = ["courbi.ttf"]
            elif is_bold:
                names = ["courbd.ttf"]
            elif is_italic:
                names = ["couri.ttf"]
            else:
                names = ["cour.ttf"]
        else:
            if is_bold and is_italic:
                names = ["arialbi.ttf", "calibriz.ttf", "segoeuiz.ttf"]
            elif is_bold:
                names = ["arialbd.ttf", "calibrib.ttf", "segoeuib.ttf"]
            elif is_italic:
                names = ["ariali.ttf", "calibrii.ttf", "segoeuii.ttf"]
            else:
                names = ["arial.ttf", "calibri.ttf", "segoeui.ttf"]

        dirs = [
            r"C:\Windows\Fonts",
            "/usr/share/fonts/truetype",
            "/usr/share/fonts",
            "/Library/Fonts",
            "/System/Library/Fonts",
        ]
        for font_name in names:
            for d in dirs:
                full_path = os.path.join(d, font_name)
                if os.path.isfile(full_path):
                    return full_path
        return None

    @classmethod
    def _font_candidates_for_line(
        cls,
        line: Dict[str, Any],
        unicode_fontfile: Optional[str] = None,
    ) -> List[Tuple[str, Optional[str]]]:
        style = cls._font_style_for_line(line)
        fallback = cls._fallback_fontname_for_style(style)
        candidates: List[Tuple[str, Optional[str]]] = []

        if unicode_fontfile:
            style_fontfile = cls._fontfile_for_style(style) or unicode_fontfile
            candidates.append(("LinguaStyle", style_fontfile))

        alias = cls.BASE14_FONT_ALIASES.get(str(style.get("font_key") or ""))
        if alias:
            candidates.append((alias, None))

        font_label = clean_invisible_unicode(style.get("font_label", "")).strip()
        if font_label:
            if "+" in font_label and font_label.split("+", 1)[0].isupper():
                font_label = font_label.split("+", 1)[1]
            candidates.append((font_label, None))

        candidates.extend([(fallback, None), ("helv", None)])

        unique: List[Tuple[str, Optional[str]]] = []
        seen = set()
        for fontname, fontfile in candidates:
            key = (fontname, fontfile)
            if fontname and key not in seen:
                unique.append(key)
                seen.add(key)
        return unique

    @classmethod
    def _text_alignment_for_line(
        cls,
        line: Dict[str, Any],
        rect: fitz.Rect,
        page_rect: fitz.Rect,
    ) -> int:
        explicit = str(
            line.get("align") or line.get("alignment") or line.get("text_align") or ""
        ).strip().lower()
        if explicit in {"center", "middle", "centre"}:
            return fitz.TEXT_ALIGN_CENTER
        if explicit in {"right", "end"}:
            return fitz.TEXT_ALIGN_RIGHT

        block_rect = cls._rect_from_bbox(line.get("block_bbox"), page_rect)
        if not block_rect or block_rect.width <= rect.width + 4:
            return fitz.TEXT_ALIGN_LEFT

        tolerance = max(6.0, block_rect.width * 0.08)
        left_margin = rect.x0 - block_rect.x0
        right_margin = block_rect.x1 - rect.x1

        # If aligned to the left edge of the text block, preserve left alignment
        if left_margin <= tolerance and right_margin > tolerance:
            return fitz.TEXT_ALIGN_LEFT

        if abs(right_margin) <= tolerance:
            return fitz.TEXT_ALIGN_RIGHT

        rect_center = (rect.x0 + rect.x1) / 2.0
        block_center = (block_rect.x0 + block_rect.x1) / 2.0
        if (
            abs(rect_center - block_center) <= tolerance
            and left_margin > tolerance
            and right_margin > tolerance
        ):
            return fitz.TEXT_ALIGN_CENTER
        return fitz.TEXT_ALIGN_LEFT

    @classmethod
    def _unicode_fontfile(cls) -> Optional[str]:
        if cls._unicode_fontfile_checked:
            return cls._unicode_fontfile_path

        candidates = []
        env_font = os.environ.get("LINGOKATUTUBO_PDF_FONT")
        if env_font:
            candidates.append(env_font)
        # Noto Sans / DejaVu Sans first: both fully cover Philippine/Latin
        # diacritics (including combining marks) with clean, consistent
        # rendering. System UI fonts follow as fallbacks.
        candidates.extend([
            r"C:\Windows\Fonts\NotoSans-Regular.ttf",
            r"C:\Windows\Fonts\DejaVuSans.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\calibri.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        ])

        cls._unicode_fontfile_path = next(
            (path for path in candidates if path and os.path.exists(path)),
            None,
        )
        cls._unicode_fontfile_checked = True
        return cls._unicode_fontfile_path

    @staticmethod
    def _needs_unicode_font(text: str) -> bool:
        # Any non-ASCII character (Bagobo-Tagabawa diacritics like á/ô/é are
        # Latin-1, curly quotes and combining marks are beyond it) switches
        # the line to the embedded Unicode font. Base-14 viewer fonts can
        # render Latin-1, but routing every diacritic line through one
        # embedded TTF keeps accents correct in every PDF viewer and stops
        # lines within the same document from rendering in different fonts.
        return any(ord(char) > 127 for char in text)

    # Typographic characters that degrade to a readable ASCII equivalent when
    # no Unicode font file is available; everything else beyond Latin-1
    # becomes "?" rather than an invisible/tofu glyph.
    _ASCII_DEGRADE_MAP = {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "-",
        "…": "...",
    }

    @classmethod
    def _pdf_safe_text(cls, text: str) -> str:
        text = clean_invisible_unicode(text)
        out = []
        for char in text:
            if ord(char) <= 255:
                out.append(char)
            elif char in cls._ASCII_DEGRADE_MAP:
                out.append(cls._ASCII_DEGRADE_MAP[char])
            elif unicodedata.combining(char):
                # A combining mark with no font to shape it is better
                # dropped than shown as a stray "?" after its base letter.
                continue
            else:
                out.append("?")
        return "".join(out)

    @staticmethod
    def _font(fontname: str, fontfile: Optional[str] = None) -> fitz.Font:
        if fontfile:
            try:
                return fitz.Font(fontfile=fontfile)
            except Exception:
                pass
        try:
            return fitz.Font(fontname=fontname)
        except Exception:
            return fitz.Font(fontname="helv")

    @staticmethod
    def _text_width(font: fitz.Font, text: str, fontsize: float) -> float:
        try:
            return float(font.text_length(text, fontsize=fontsize))
        except Exception:
            return len(text) * fontsize * 0.55

    @classmethod
    def _split_word(
        cls,
        word: str,
        font: fitz.Font,
        fontsize: float,
        max_width: float,
    ) -> List[str]:
        chunks: List[str] = []
        current = ""
        for char in word:
            candidate = current + char
            if current and cls._text_width(font, candidate, fontsize) > max_width:
                chunks.append(current)
                current = char
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks or [word]

    @classmethod
    def _wrap_text(
        cls,
        text: str,
        font: fitz.Font,
        fontsize: float,
        max_width: float,
    ) -> List[str]:
        wrapped: List[str] = []
        paragraphs = text.splitlines() or [text]
        for paragraph in paragraphs:
            words = paragraph.split()
            if not words:
                wrapped.append("")
                continue

            current = ""
            for word in words:
                word_chunks = (
                    [word]
                    if cls._text_width(font, word, fontsize) <= max_width
                    else cls._split_word(word, font, fontsize, max_width)
                )
                for chunk in word_chunks:
                    candidate = chunk if not current else f"{current} {chunk}"
                    if (
                        current
                        and cls._text_width(font, candidate, fontsize) > max_width
                    ):
                        wrapped.append(current)
                        current = chunk
                    else:
                        current = candidate
            if current:
                wrapped.append(current)
        return wrapped

    @staticmethod
    def _line_height(fontsize: float) -> float:
        return fontsize * ReconstructionService.LINE_HEIGHT_FACTOR

    @classmethod
    def _effective_min_font_size(cls, rect: fitz.Rect) -> float:
        """Prefer readable text, but allow smaller text when the bbox is tiny."""
        usable_single_line_size = max(
            cls.MIN_FONT_SIZE,
            (max(1.0, rect.height) - 0.25) / cls.LINE_HEIGHT_FACTOR,
        )
        return max(
            cls.MIN_FONT_SIZE,
            min(cls.READABLE_MIN_FONT_SIZE, usable_single_line_size),
        )

    @classmethod
    def _base_font_size(cls, line: Dict[str, Any], rect: fitz.Rect) -> float:
        min_font_size = cls._effective_min_font_size(rect)
        size = line.get("size")
        if size is None:
            spans = line.get("spans") or []
            if spans:
                size = spans[0].get("size")
        try:
            size = float(size)
        except Exception:
            size = max(min_font_size, rect.height * 0.78)

        # Do not artificially shrink the font size below its extracted value
        return max(min_font_size, size)

    @classmethod
    def _fit_text_to_rect(
        cls, text: str, rect: fitz.Rect, fontname: str, base_font_size: float,
        fontfile: Optional[str] = None,
    ) -> Tuple[str, float, bool, bool]:
        """Keep all text; the fourth legacy flag means overflow, never truncation."""
        font = cls._font(fontname, fontfile=fontfile)
        initial = max(float(base_font_size), cls.MIN_FONT_SIZE)
        floor = min(initial, cls._effective_min_font_size(rect))
        def evaluate(size):
            lines = cls._wrap_text(text, font, size, max(1.0, rect.width))
            height = max(
                font.ascender + max(0, len(lines) - 1) * cls.LINE_HEIGHT_FACTOR,
                len(lines) * cls.LINE_HEIGHT_FACTOR - font.descender,
            ) * size + 0.01
            overflow = height > rect.height + 0.01 or any(
                cls._text_width(font, part, size) > rect.width + 0.01 for part in lines
            )
            return "\n".join(lines), size, size < initial - 0.01, overflow
        result = evaluate(initial)
        if not result[3] or initial <= floor:
            return result
        minimum = evaluate(floor)
        if minimum[3]:
            return minimum
        size = initial
        while size > floor:
            size = max(floor, size - 0.5)
            result = evaluate(size)
            if not result[3]:
                return result
        return minimum

    @classmethod
    def _insert_text_in_rect(
        cls, page: fitz.Page, rect: fitz.Rect, text: str, line: Dict[str, Any],
        warnings: Optional[List[str]], page_number: int, block_number: int,
        line_number: int, fallback_text: Optional[str] = None,
    ) -> bool:
        """Commit only a complete, readable insertion inside available page space."""
        text = unicodedata.normalize("NFC", clean_invisible_unicode(text))
        prefix = f"Page {page_number}, block {block_number}, line {line_number}: "
        if not text.strip():
            cls._append_warning(warnings, prefix + "no translated text was available.")
            return False
        unicode_fontfile = cls._unicode_fontfile() if cls._needs_unicode_font(text) else None
        if cls._needs_unicode_font(text) and not unicode_fontfile:
            if any(ord(char) > 255 and char not in cls._ASCII_DEGRADE_MAP for char in text):
                cls._append_warning(warnings, prefix + "no Unicode PDF font can preserve the translated characters; output was not completed.")
                return False
            text = cls._pdf_safe_text(text)
            cls._append_warning(warnings, prefix + "no Unicode PDF font was found; base-14 Latin text and normalized typography were used.")

        base = cls._base_font_size(line, rect)
        color = cls._visible_text_color(line, warnings, page_number, block_number, line_number)
        available = cls._rect_from_bbox(line.get("available_bbox"), page.rect)
        if available is None:
            available = fitz.Rect(rect.x0, rect.y0, page.rect.x1 - 18, page.rect.y1 - 18)
        candidates = cls._font_candidates_for_line(line, unicode_fontfile)
        original_overflow = False
        attempted_fonts = set()
        for candidate_font, candidate_file in candidates:
            font = cls._font(candidate_font, candidate_file)
            if font.name in attempted_fonts:
                continue
            attempted_fonts.add(font.name)
            if any(not font.has_glyph(ord(char)) for char in text if not char.isspace()):
                continue
            for target in [rect, available]:
                fitted, size, shrunk, overflow = cls._fit_text_to_rect(
                    text, target, candidate_font, base, fontfile=candidate_file,
                )
                if target == rect:
                    original_overflow = original_overflow or overflow
                if overflow:
                    continue
                # The shape is a dry run until the entire textbox fits.
                # Never paint expanded white rectangles over neighboring content.
                shape = page.new_shape()
                kwargs = {"fontsize": size, "fontname": candidate_font,
                          "color": color, "align": cls._text_alignment_for_line(line, rect, page.rect),
                          "lineheight": cls.LINE_HEIGHT_FACTOR}
                if candidate_file:
                    kwargs["fontfile"] = candidate_file
                try:
                    remaining = shape.insert_textbox(target, fitted, **kwargs)
                    if remaining < -0.01:
                        continue
                    shape.commit(overlay=True)
                    if shrunk:
                        cls._append_warning(warnings, prefix + f"translated text shrunk from {base:g}pt to {size:g}pt.")
                    if target != rect:
                        cls._append_warning(warnings, prefix + "translated text was too long for its bbox; overflowed into available page space without covering neighboring content.")
                    expected = "".join(text.split())
                    actual = "".join(unicodedata.normalize("NFC", page.get_text()).split())
                    if expected not in actual:
                        cls._append_warning(warnings, prefix + "inserted text failed output text validation; output was not completed.")
                        return False
                    return True
                except Exception:
                    continue
        cls._append_warning(warnings, prefix + (
            "translated text exceeds its bbox and available page space; full text could not be preserved, so output was not completed."
            if original_overflow else
            "translated text could not be inserted with a supported font; output was not completed."
        ))
        return False

    @classmethod
    def _available_rect(cls, rect: fitz.Rect, page: fitz.Page, obstacles: List[fitz.Rect]) -> fitz.Rect:
        """Allow expansion only into unoccupied space to the right and below."""
        right, bottom = max(rect.x1, page.rect.x1 - 18), max(rect.y1, page.rect.y1 - 18)
        for other in obstacles:
            if other == rect:
                continue
            if other.y0 < rect.y1 and other.y1 > rect.y0 and other.x0 > rect.x0:
                right = min(right, other.x0 - 1)
        for other in obstacles:
            if other == rect:
                continue
            if other.x0 < right and other.x1 > rect.x0 and other.y0 > rect.y0:
                bottom = min(bottom, other.y0 - 1)
        return fitz.Rect(rect.x0, rect.y0, max(rect.x1, right), max(rect.y1, bottom))

    @classmethod
    def _add_review_indicator(cls, page, rect, record, source_text, warnings, page_number):
        method = record.get("method") or record.get("translation_method") if isinstance(record, dict) else ""
        flagged = isinstance(record, dict) and (record.get("needs_review") or record.get("review_required"))
        if method == "source_preview" or (method in {"identity", "source_retained"} and not flagged):
            return
        raw = record.get("translated") or record.get("translated_text") if isinstance(record, dict) else record
        retained = is_display_fallback_translation(raw, method)
        review = flagged or retained or method == "unknown"
        if not review:
            return
        message = ("Original text retained; translation requires validation." if retained or method == "unknown"
                   else "Suggested translation requires language-expert validation.")
        annot = page.add_text_annot(
            (max(0, page.rect.x1 - 20), min(max(0, rect.y0), page.rect.y1 - 20)), message,
        )
        annot.set_info(title="Translation review")
        # Retain the note for inspection without painting icons in learner
        # output or printed copies. Review flags / provenance remain unchanged.
        annot.set_flags(
            (annot.flags | fitz.PDF_ANNOT_IS_HIDDEN | fitz.PDF_ANNOT_IS_NO_VIEW)
            & ~fitz.PDF_ANNOT_IS_PRINT
        )
        annot.update()
        cls._append_warning(warnings, f"Page {page_number}: " + message)

    @classmethod
    def create_docx_pdf(cls, layout_data, translations, output_path, warnings=None):
        """Render DOCX body content completely, with explicit simplified-layout warnings."""
        import base64
        doc = fitz.open()
        expected = []
        try:
            for page_index, data in enumerate(layout_data):
                for warning in data.get("warnings", []):
                    cls._append_warning(warnings, warning)
                page = doc.new_page(width=612, height=792)
                y = 72.0
                for block_index, block in enumerate(data.get("blocks", [])):
                    if block.get("type") == "image":
                        bbox = fitz.Rect(block["bbox"])
                        if y + bbox.height > 720:
                            page = doc.new_page(width=612, height=792)
                            y = 72.0
                        page.insert_image(fitz.Rect(72, y, 72 + bbox.width, y + bbox.height),
                                          stream=base64.b64decode(block["image_base64"]))
                        y += bbox.height + 12
                        continue
                    if block.get("type") != "text":
                        continue
                    for line_index, line in enumerate(block.get("lines", [])):
                        source = line.get("text", "")
                        record = cls._translation_record_for_line(
                            translations, f"{page_index}_{block_index}_{line_index}", source)
                        text = unicodedata.normalize("NFC", cls._coerce_translation_value(record, source))
                        if not text:
                            continue
                        expected.append("".join(text.split()))
                        fontfile = cls._unicode_fontfile() if cls._needs_unicode_font(text) else None
                        font = cls._font("helv", fontfile)
                        rows = cls._wrap_text(text, font, 12, 468)
                        reviewed_page = None
                        for row in rows:
                            if y + 20 > 720:
                                page = doc.new_page(width=612, height=792)
                                y = 72.0
                            rect = fitz.Rect(72, y, 540, y + 20)
                            if not cls._insert_text_in_rect(
                                page, rect, row, {**line, "size": 12, "available_bbox": list(rect)},
                                warnings, page.number + 1, block_index + 1, line_index + 1,
                            ):
                                return False
                            if reviewed_page != page.number:
                                cls._add_review_indicator(page, rect, record, source, warnings, page.number + 1)
                                reviewed_page = page.number
                            y += 20
            actual = "".join("".join(unicodedata.normalize("NFC", p.get_text()).split()) for p in doc)
            if any(text not in actual for text in expected):
                cls._append_warning(warnings, "DOCX output text validation failed; output was not completed.")
                return False
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            doc.save(output_path)
            return True
        except Exception as exc:
            safe_print(f"[Reconstruction] DOCX output failed: {exc}")
            cls._append_warning(warnings, "DOCX content could not be rendered completely; output was not completed.")
            return False
        finally:
            doc.close()

    @staticmethod
    def reconstruct_pdf(
        input_pdf_path: str,
        layout_data: List[Dict[str, Any]],
        translations: Dict[str, Any],
        output_path: str,
        is_scanned: bool = False,
        layout_warnings: Optional[List[str]] = None,
    ) -> bool:
        """
        Reconstruct a PDF with translated text
        
        Args:
            input_pdf_path: Path to original PDF
            layout_data: Layout information from extraction
            translations: Dict mapping block_id -> {"original", "translated"}
            output_path: Path to save new PDF
            is_scanned: Whether layout came from OCR over scanned pages
            layout_warnings: Optional list populated with fit/overflow warnings
        
        Returns:
            True if successful
        """
        doc = None
        try:
            doc = fitz.open(input_pdf_path)
            layout_page_count = len(layout_data or [])
            if layout_page_count != doc.page_count:
                ReconstructionService._append_warning(
                    layout_warnings,
                    "Source PDF has "
                    f"{doc.page_count} page(s), but extracted layout has "
                    f"{layout_page_count} page(s); exact reconstruction was "
                    "skipped because not every page can be translated safely.",
                )
                return False

            # Process each page
            for page_num, page_layout in enumerate(layout_data):
                if page_num >= doc.page_count:
                    break

                page = doc[page_num]
                blocks = page_layout.get("blocks", [])

                layout_width = page_layout.get("width")
                layout_height = page_layout.get("height")
                if layout_width and abs(float(layout_width) - page.rect.width) > 1:
                    ReconstructionService._append_warning(
                        layout_warnings,
                        f"Page {page_num + 1}: layout width differs from source PDF page width.",
                    )
                if layout_height and abs(float(layout_height) - page.rect.height) > 1:
                    ReconstructionService._append_warning(
                        layout_warnings,
                        f"Page {page_num + 1}: layout height differs from source PDF page height.",
                    )

                # Two-pass approach per page:
                #   (1) Collect every (rect, translated_text, line, indices)
                #       task and queue redactions for digital PDFs.
                #   (2) Apply redactions to erase the source glyphs from the
                #       text layer (images / lines / shapes outside the rect
                #       are preserved).
                #   (3) Draw the translated text into each rect on top of the
                #       cleaned page.
                # Unknown segments resolve to display-safe source text; known
                # translations replace the source glyphs without flattening the
                # page or destroying non-text layout.
                tasks: List[Dict[str, Any]] = []
                for block_idx, block in enumerate(blocks, start=1):
                    if block.get("type") != "text":
                        continue

                    lines = block.get("lines", [])

                    for line_idx, line in enumerate(lines, start=1):
                        original_text = clean_invisible_unicode(line.get("text", ""))
                        lookup_key = f"{page_num}_{block_idx - 1}_{line_idx - 1}"
                        translation_record = ReconstructionService._translation_record_for_line(
                            translations,
                            lookup_key,
                            original_text,
                        )
                        translated_text = ReconstructionService._coerce_translation_value(
                            translation_record,
                            original_text,
                        )
                        translation_method = (
                            str(translation_record.get("method") or "").lower()
                            if isinstance(translation_record, dict)
                            else ""
                        )
                        line_bbox = line.get("bbox")

                        if not original_text.strip():
                            continue
                        if not line_bbox or not translated_text:
                            ReconstructionService._append_warning(
                                layout_warnings, f"Page {page_num + 1}: text has no usable bounds or output; reconstruction was not completed.")
                            return False

                        # Identity translations (same source/target language)
                        # are the only safe case for skipping. Never skip when
                        # the dataset gave us an exact/normalized translation,
                        # even if its rendered form happens to coincide with
                        # the source text.
                        if (
                            translation_method == "identity"
                            and translated_text.strip() == original_text.strip()
                        ):
                            continue

                        rect = ReconstructionService._rect_from_bbox(
                            line_bbox,
                            page.rect,
                            # Widen the mask slightly so digital-PDF glyph
                            # descenders never bleed through the overlay.
                            padding=1.5 if is_scanned else 1.25,
                        )
                        if rect is None:
                            ReconstructionService._append_warning(
                                layout_warnings,
                                f"Page {page_num + 1}, block {block_idx}, line {line_idx}: "
                                "invalid text bbox; reconstruction was not completed.",
                            )
                            return False

                        line_for_insert = dict(line)
                        line_for_insert.setdefault("block_bbox", block.get("bbox"))
                        tasks.append({
                            "rect": rect,
                            "translated_text": translated_text,
                            "source_text": original_text,
                            "line": line_for_insert,
                            "block_idx": block_idx,
                            "line_idx": line_idx,
                            "record": translation_record,
                        })

                obstacles = [task["rect"] for task in tasks]
                for block in blocks:
                    if block.get("type") == "image":
                        image_rect = ReconstructionService._rect_from_bbox(block.get("bbox"), page.rect)
                        if image_rect:
                            obstacles.append(image_rect)
                for drawing in page.get_drawings():
                    for item in drawing.get("items", []):
                        if item[0] == "l":
                            a, b = item[1:3]
                            obstacles.append(fitz.Rect(min(a.x, b.x), min(a.y, b.y),
                                                       max(a.x, b.x), max(a.y, b.y)))
                for task in tasks:
                    task["line"]["available_bbox"] = list(ReconstructionService._available_rect(task["rect"], page, obstacles))

                # Pass 2: erase the source text layer in every queued rect
                # before drawing translations on top. For scanned PDFs we have
                # nothing to redact, so a plain white rect is enough.
                if not is_scanned and tasks:
                    try:
                        for task in tasks:
                            page.add_redact_annot(
                                task["rect"],
                                fill=(1.0, 1.0, 1.0),
                                cross_out=False,
                            )
                        apply_kwargs = {"images": 0, "graphics": 0}
                        try:
                            page.apply_redactions(**apply_kwargs)
                        except TypeError:
                            # Older PyMuPDF builds do not accept the kw flags;
                            # fall back to the default redaction which still
                            # preserves images by default.
                            page.apply_redactions()
                    except Exception as e:
                        ReconstructionService._append_warning(
                            layout_warnings,
                            f"Page {page_num + 1}: failed to redact source text "
                            f"({e}); falling back to white-mask overlay.",
                        )
                        for task in tasks:
                            try:
                                page.draw_rect(
                                    task["rect"],
                                    color=(1, 1, 1),
                                    fill=(1, 1, 1),
                                    width=0,
                                    overlay=True,
                                )
                            except Exception:
                                pass
                elif is_scanned:
                    for task in tasks:
                        try:
                            page.draw_rect(
                                task["rect"],
                                color=(1, 1, 1),
                                fill=(1, 1, 1),
                                width=0,
                                overlay=True,
                            )
                        except Exception:
                            pass

                # Pass 3: draw the translated text into each (now-cleaned) rect.
                for task in tasks:
                    rect = task["rect"]
                    translated_text = clean_invisible_unicode(task["translated_text"])
                    line = task["line"]
                    block_idx = task["block_idx"]
                    line_idx = task["line_idx"]
                    try:
                        inserted = ReconstructionService._insert_text_in_rect(
                            page,
                            rect,
                            translated_text,
                            line,
                            layout_warnings,
                            page_num + 1,
                            block_idx,
                            line_idx,
                            fallback_text=task.get("source_text") or translated_text,
                        )
                        if not inserted:
                            ReconstructionService._append_warning(
                                layout_warnings,
                                f"Page {page_num + 1}, block {block_idx}, line {line_idx}: "
                                "source text was removed but neither translated text nor "
                                "display-safe fallback text could be inserted."
                            )
                            return False
                        ReconstructionService._add_review_indicator(
                            page, rect, task["record"], task["source_text"], layout_warnings, page_num + 1,
                        )
                    except Exception as e:
                        safe_print(f"[Reconstruction] Error inserting text: {e}")
                        ReconstructionService._append_warning(
                            layout_warnings,
                            f"Page {page_num + 1}, block {block_idx}, line {line_idx}: "
                            f"failed to draw translated text: {e}",
                        )
                        return False
            
            # Save output PDF
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            doc.save(output_path)
            doc.close()
            
            return True
        
        except Exception as e:
            safe_print(f"[Reconstruction] Error reconstructing PDF: {e}")
            return False
        finally:
            if doc is not None and not getattr(doc, "is_closed", False):
                doc.close()
    
    @staticmethod
    def create_bilingual_pdf(
        original_pdf_path: str,
        translated_pdf_path: str,
        output_path: str
    ) -> bool:
        """
        Create a bilingual PDF with original and translated pages side-by-side or alternating
        
        Args:
            original_pdf_path: Path to original PDF
            translated_pdf_path: Path to translated PDF
            output_path: Path to save combined PDF
        
        Returns:
            True if successful
        """
        original_doc = None
        translated_doc = None
        output_doc = None
        try:
            original_doc = fitz.open(original_pdf_path)
            translated_doc = fitz.open(translated_pdf_path)
            output_doc = fitz.open()

            if original_doc.page_count != translated_doc.page_count:
                safe_print(
                    "[Reconstruction] Bilingual PDF skipped: original has "
                    f"{original_doc.page_count} page(s), translated has "
                    f"{translated_doc.page_count} page(s)"
                )
                return False

            page_count = original_doc.page_count
            
            # Alternate pages: original, translated, original, translated...
            for i in range(page_count):
                output_doc.insert_pdf(original_doc, from_page=i, to_page=i)
                output_doc.insert_pdf(translated_doc, from_page=i, to_page=i)
            
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            output_doc.save(output_path)
            output_doc.close()
            original_doc.close()
            translated_doc.close()
            
            return True
        
        except Exception as e:
            safe_print(f"[Reconstruction] Error creating bilingual PDF: {e}")
            return False
        finally:
            for pdf_doc in (output_doc, translated_doc, original_doc):
                if pdf_doc is not None and not getattr(pdf_doc, "is_closed", False):
                    pdf_doc.close()
    
    @staticmethod
    def create_preview_images(
        pdf_path: str,
        output_dir: str,
        max_pages: int = 3,
        dpi: int = 150,
        prefix: str = "preview",
    ) -> List[str]:
        """
        Create preview images from PDF pages
        
        Args:
            pdf_path: Path to PDF
            output_dir: Directory to save preview images
            max_pages: Maximum pages to preview
            dpi: DPI for rendering
            prefix: Filename prefix, used to avoid original/translated collisions
        
        Returns:
            List of image file paths
        """
        image_paths = []
        
        try:
            doc = fitz.open(pdf_path)
            os.makedirs(output_dir, exist_ok=True)
            
            for page_num in range(min(max_pages, doc.page_count)):
                page = doc[page_num]
                
                # Render to image
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                
                safe_prefix = "".join(
                    char if char.isalnum() or char in ("-", "_") else "_"
                    for char in prefix
                ) or "preview"
                image_path = os.path.join(output_dir, f"{safe_prefix}_page_{page_num}.png")
                pix.save(image_path)
                image_paths.append(image_path)
            
            doc.close()
        
        except Exception as e:
            safe_print(f"[Reconstruction] Error creating preview images: {e}")
        
        return image_paths


# Global instance
_reconstruction_service = ReconstructionService()


def get_reconstruction_service() -> ReconstructionService:
    """Get the reconstruction service"""
    return _reconstruction_service
