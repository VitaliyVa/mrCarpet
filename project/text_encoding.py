"""Fix common UTF-8↔Windows-1252 mojibake (e.g. «Ð¢ÐµÑÑ‚» → «Тест»)."""

from __future__ import annotations

# Unicode chars that cp1252 maps for bytes 0x80–0x9F (latin-1 leaves them as C1).
_CP1252_REVERSE: dict[int, int] = {
    0x20AC: 0x80,
    0x201A: 0x82,
    0x0192: 0x83,
    0x201E: 0x84,
    0x2026: 0x85,
    0x2020: 0x86,
    0x2021: 0x87,
    0x02C6: 0x88,
    0x2030: 0x89,
    0x0160: 0x8A,
    0x2039: 0x8B,
    0x0152: 0x8C,
    0x017D: 0x8E,
    0x2018: 0x91,
    0x2019: 0x92,
    0x201C: 0x93,
    0x201D: 0x94,
    0x2022: 0x95,
    0x2013: 0x96,
    0x2014: 0x97,
    0x02DC: 0x98,
    0x2122: 0x99,
    0x0161: 0x9A,
    0x203A: 0x9B,
    0x0153: 0x9C,
    0x017E: 0x9E,
    0x0178: 0x9F,
}


def looks_like_utf8_mojibake(text: str) -> bool:
    """Latin Ð/Ñ clusters typical of UTF-8 Cyrillic misread as cp1252/latin-1."""
    if not text:
        return False
    return ("Ð" in text or "Ñ" in text) and any(ord(c) >= 0x80 for c in text)


def fix_utf8_mojibake(text: str) -> str:
    """
    If text looks like mojibake, undo cp1252/latin-1 mis-decode of UTF-8 bytes.
    Returns original text when fix is impossible or not needed.
    """
    if not looks_like_utf8_mojibake(text):
        return text

    raw = bytearray()
    try:
        for ch in text:
            code = ord(ch)
            if code in _CP1252_REVERSE:
                raw.append(_CP1252_REVERSE[code])
            elif code <= 0xFF:
                raw.append(code)
            else:
                return text
        fixed = raw.decode("utf-8")
    except UnicodeDecodeError:
        return text

    # Prefer fix only when we actually recover Cyrillic / lose mojibake markers.
    if looks_like_utf8_mojibake(fixed):
        return text
    if any("\u0400" <= c <= "\u04FF" for c in fixed):
        return fixed
    return fixed if fixed != text else text
