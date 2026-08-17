"""Glyph tables for the Computer Modern math fonts used by this book.

The inventory was measured from the PDF itself (`work/math_glyph_inventory.json`):
272 distinct (font family, character) pairs. Every one of them is covered here except the
CMEX extension font, whose glyphs carry no usable Unicode and always signal a large operator
or a large delimiter.
"""

# Characters that come out of the extractor slightly wrong and need repair.
UNICODE_FIXES = {
    "µ": "μ",  # MICRO SIGN -> GREEK SMALL LETTER MU
    "−": "−",  # keep the real minus sign
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}

# Accent glyphs that LaTeX draws over the following base character.
ACCENTS = {
    "ˆ": "hat",  # MODIFIER LETTER CIRCUMFLEX
    "^": "hat",
    "¯": "bar",  # MACRON
    "‾": "bar",
    "˜": "tilde",  # SMALL TILDE
    "~": "tilde",
    "˙": "dot",
    "ˇ": "check",
    "ˊ": "acute",
    "ˋ": "grave",
}

LATEX_ACCENT = {
    "hat": r"\hat",
    "bar": r"\bar",
    "tilde": r"\tilde",
    "dot": r"\dot",
    "check": r"\check",
    "acute": r"\acute",
    "grave": r"\grave",
}

# Unicode -> LaTeX for symbols found in CMSY / CMR / CMMI.
SYMBOL_LATEX = {
    "−": "-",
    "·": r"\cdot",
    "×": r"\times",
    "′": "'",
    "∗": "*",
    "•": r"\bullet",
    "≤": r"\leq",
    "≥": r"\geq",
    "∥": r"\|",
    "∈": r"\in",
    "≈": r"\approx",
    "∼": r"\sim",
    "√": r"\sqrt",
    "∞": r"\infty",
    "→": r"\to",
    "←": r"\leftarrow",
    "⟨": r"\langle",
    "⟩": r"\rangle",
    "±": r"\pm",
    "∩": r"\cap",
    "∪": r"\cup",
    "≡": r"\equiv",
    "≫": r"\gg",
    "≪": r"\ll",
    "∀": r"\forall",
    "∇": r"\nabla",
    "∝": r"\propto",
    "⊂": r"\subset",
    "∅": r"\emptyset",
    "∂": r"\partial",
    "ℓ": r"\ell",
    "Δ": r"\Delta",
    "Σ": r"\Sigma",
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ϵ": r"\epsilon",
    "ε": r"\varepsilon",
    "η": r"\eta",
    "θ": r"\theta",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ξ": r"\xi",
    "π": r"\pi",
    "ρ": r"\rho",
    "σ": r"\sigma",
    "φ": r"\phi",
    "χ": r"\chi",
    "∣": "|",
    "{": r"\{",
    "}": r"\}",
    "%": r"\%",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "_": r"\_",
}

# Combining "not" plus a relation collapses to a single negated relation.
NEGATED = {
    "=": "≠",
    "∈": "∉",
    "≤": "≰",
    "≥": "≱",
    "⊂": "⊄",
}

NEGATED_LATEX = {
    "=": r"\neq",
    "∈": r"\notin",
    "≤": r"\nleq",
    "≥": r"\ngeq",
    "⊂": r"\not\subset",
}

# Multi-letter upright runs in CMR that are standard operator names.
OPERATOR_NAMES = {
    "log",
    "exp",
    "min",
    "max",
    "sin",
    "cos",
    "tan",
    "lim",
    "sup",
    "inf",
    "det",
    "arg",
    "argmin",
    "argmax",
    "Pr",
    "Var",
    "Cov",
    "Corr",
    "Bias",
    "MSE",
    "RSS",
    "TSS",
    "ESS",
    "SE",
    "se",
    "df",
    "AIC",
    "BIC",
    "RSE",
    "logit",
    "sd",
    "E",
}

# Text that reads better as an entity in XHTML.
HTML_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}


def escape_html(text: str) -> str:
    out = []
    for char in text:
        out.append(HTML_ESCAPES.get(char, char))
    return "".join(out)


def fix_unicode(char: str) -> str:
    return UNICODE_FIXES.get(char, char)
