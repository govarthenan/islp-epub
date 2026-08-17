"""Font classification for the ISLP PDF.

The book is typeset with Latin Modern for prose and code, and Computer Modern for
mathematics. Because the two families never overlap, a span's font name alone tells us
whether it is text or mathematics.
"""

from enum import Enum


class Role(str, Enum):
    """What a span of characters is."""

    PROSE = "prose"
    PROSE_ITALIC = "prose_italic"
    PROSE_BOLD = "prose_bold"
    MONO = "mono"
    MATH_VAR = "math_var"  # Computer Modern Math Italic: variables
    MATH_UP = "math_up"  # Computer Modern Roman/Symbol/Extension: digits, operators
    GRAPHIC = "graphic"  # text drawn inside a figure (Arial, Helvetica, ...)
    OTHER = "other"


MATH_UPRIGHT_PREFIXES = ("CMR", "CMSY", "CMEX", "CMBX", "CMTT", "CMSS", "MSBM", "MSAM", "CMB", "CMU")
MATH_ITALIC_PREFIXES = ("CMMI", "CMTI", "CMITT")
GRAPHIC_PREFIXES = ("ARIAL", "HELVETICA", "CALIBRI", "MYRIADPRO", "TIMESNEWROMAN", "ADOBEPISTD", "SYMBOL")


def family(font_name: str) -> str:
    """Drop the six-letter PDF subset prefix: 'AAAABD+CMSY10' -> 'CMSY10'."""
    return font_name.split("+", 1)[-1]


def classify(font_name: str) -> Role:
    fam = family(font_name).upper()
    if fam.startswith("LMMONO"):
        return Role.MONO
    if fam.startswith("LMROMAN") or fam.startswith("LMSANS"):
        if "ITALIC" in fam or "OBLIQUE" in fam:
            return Role.PROSE_ITALIC
        if "BOLD" in fam:
            return Role.PROSE_BOLD
        return Role.PROSE
    if any(fam.startswith(p) for p in MATH_ITALIC_PREFIXES):
        return Role.MATH_VAR
    if any(fam.startswith(p) for p in MATH_UPRIGHT_PREFIXES):
        return Role.MATH_UP
    if any(fam.startswith(p) for p in GRAPHIC_PREFIXES):
        return Role.GRAPHIC
    return Role.OTHER


def is_math(role: Role) -> bool:
    return role in (Role.MATH_VAR, Role.MATH_UP)


def is_extension_font(font_name: str) -> bool:
    """CMEX holds the large operators and large delimiters (sum, product, integral,
    big parentheses, radicals). Its presence means the expression has real two-dimensional
    structure that flat text cannot carry."""
    return family(font_name).upper().startswith("CMEX")


def nominal_size_family(font_name: str) -> int:
    """The design size baked into the font name, e.g. CMMI7 -> 7. Returns 0 if absent."""
    fam = family(font_name)
    digits = ""
    for char in reversed(fam):
        if char.isdigit():
            digits = char + digits
        else:
            break
    return int(digits) if digits else 0
