"""Rebuild inline content (prose plus mathematics) from character data.

Sub- and superscripts are recovered geometrically: a character typeset smaller than the line
and sitting below its baseline is a subscript, above it a superscript. This was verified
against the PDF (base 'x' at size 10 origin y=368.0, subscript 'ij' at size 7 origin y=369.5).

Each math run is graded into one of three tiers:

  TEXT     plain HTML with <i>, <sub>, <sup> and Unicode. Reflows, scales, searchable.
  LATEX    LaTeX generated here from the character data, rendered later to SVG.
           Used when the run has accents or script letters that HTML cannot show honestly.
  VLM      the run has a large operator, a radical or a fraction bar, so its two-dimensional
           structure is not in the character stream at all. It is cropped to an image and
           read by a vision model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from .fonts import Role, family, is_extension_font
from .pagemodel import Char
from .symbols import (
    ACCENTS,
    LATEX_ACCENT,
    NEGATED,
    NEGATED_LATEX,
    SYMBOL_LATEX,
    escape_html,
    fix_unicode,
)

SCRIPT_SIZE_RATIO = 0.92
SCRIPT_SHIFT = 0.45


class Tier(str, Enum):
    TEXT = "text"
    LATEX = "latex"
    VLM = "vlm"


@dataclass
class MathRun:
    """One contiguous stretch of mathematics inside a line."""

    chars: list[Char]
    tier: Tier
    html: str = ""
    latex: str = ""
    reason: str = ""
    key: str = ""  # dedup key
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)

    @property
    def raw_text(self) -> str:
        return "".join(c.c for c in self.chars)


@dataclass
class InlineResult:
    html: str
    math_runs: list[MathRun] = field(default_factory=list)


def _script_of(char: Char, base_size: float, baseline: float) -> int:
    """-1 subscript, 0 normal, +1 superscript."""
    if char.size >= base_size * SCRIPT_SIZE_RATIO:
        return 0
    delta = char.oy - baseline
    if delta > SCRIPT_SHIFT:
        return -1
    if delta < -SCRIPT_SHIFT:
        return 1
    return 0


def _x_overlaps(accent: Char, base: Char) -> bool:
    return accent.x0 < base.x1 + 1.2 and accent.x1 > base.x0 - 1.2


def attach_accents(chars: list[Char]) -> tuple[list[Char], dict[int, str], bool]:
    """Pull accent glyphs out of the stream and bind each to the character it sits over.

    The extractor emits the base letter first and the accent second (measured: 'f' then 'ˆ'),
    so an accent normally belongs to the character before it. Returns the character list
    without accents, a map from index to accent name, and a flag that is True when an accent
    spans more than one character (an \\overline or \\widehat, which needs a vision model)."""
    filtered: list[Char] = []
    accents: dict[int, str] = {}
    wide = False
    index = 0
    while index < len(chars):
        char = chars[index]
        if char.c in ACCENTS and char.role in (Role.MATH_UP, Role.MATH_VAR):
            previous = next((j for j in range(len(filtered) - 1, -1, -1) if not filtered[j].is_space), None)
            following = next((k for k in range(index + 1, len(chars)) if not chars[k].is_space), None)
            target_char: Char | None = None
            target_index: int | None = None
            if previous is not None and _x_overlaps(char, filtered[previous]):
                target_char, target_index = filtered[previous], previous
            elif following is not None and _x_overlaps(char, chars[following]):
                filtered.append(chars[following])
                target_char, target_index = chars[following], len(filtered) - 1
                chars = chars[:following] + chars[following + 1:]
            if target_char is not None and target_index is not None:
                if (char.x1 - char.x0) > 1.6 * max(target_char.x1 - target_char.x0, 0.1):
                    wide = True
                accents[target_index] = ACCENTS[char.c]
                index += 1
                continue
        filtered.append(char)
        index += 1
    return filtered, accents, wide


def _dominant(chars: list[Char]) -> tuple[float, float]:
    """Base size and baseline of a character list: the largest size present wins."""
    solid = [c for c in chars if not c.is_space]
    if not solid:
        return (10.0, chars[0].oy if chars else 0.0)
    size = max(c.size for c in solid)
    same = [c for c in solid if abs(c.size - size) < 0.3]
    same.sort(key=lambda c: c.oy)
    return size, same[len(same) // 2].oy


def _horizontal_rules(rules: list[tuple[float, float, float, float]],
                      bbox: tuple[float, float, float, float]) -> bool:
    """True if a thin horizontal rule (a fraction bar or a radical bar) crosses this run."""
    x0, y0, x1, y1 = bbox
    for rx0, ry0, rx1, ry1 in rules:
        if ry1 - ry0 > 1.6 or rx1 - rx0 > 160:
            continue
        if rx0 >= x0 - 2 and rx1 <= x1 + 2 and y0 - 3 <= ry0 <= y1 + 3:
            return True
    return False


# --------------------------------------------------------------------------------------
# LaTeX generation from character data
# --------------------------------------------------------------------------------------

def _latex_atom(char: Char) -> str | None:
    text = fix_unicode(char.c)
    if text in SYMBOL_LATEX:
        return SYMBOL_LATEX[text]
    if text.isalnum() or text in ".,;:!?()[]|/+=<>-'*":
        return text
    if text == " ":
        return " "
    return None


def _script_style(char: Char) -> str:
    fam = family(char.font).upper()
    if fam.startswith("MSBM"):
        return "mathbb"
    if fam.startswith("CMSY") and char.c.isalpha():
        return "mathcal"
    if fam.startswith("CMBX"):
        return "mathbf"
    if fam.startswith("CMSS"):
        return "mathsf"
    if fam.startswith("CMTT"):
        return "mathtt"
    if fam.startswith("CMR"):
        return "mathrm"
    return ""


def chars_to_latex(
    chars: list[Char],
    base_size: float,
    baseline: float,
    accents: dict[int, str] | None = None,
) -> str | None:
    """Best-effort LaTeX for a math run. Returns None when the run needs a vision model."""
    accents = accents or {}
    out: list[str] = []
    index = 0
    pending_style: str | None = None
    style_buffer: list[str] = []

    def flush_style() -> None:
        nonlocal pending_style, style_buffer
        if style_buffer:
            body = "".join(style_buffer)
            out.append(f"\\{pending_style}{{{body}}}" if pending_style else body)
        pending_style, style_buffer = None, []

    while index < len(chars):
        char = chars[index]
        if is_extension_font(char.font) or char.c == "�":
            return None
        if char.is_space:
            flush_style()
            out.append(" ")
            index += 1
            continue

        # combining "not" attaches to the following relation
        if char.c == "̸" and index + 1 < len(chars):
            following = fix_unicode(chars[index + 1].c)
            if following in NEGATED_LATEX:
                flush_style()
                out.append(NEGATED_LATEX[following])
                index += 2
                continue
            return None

        if _script_of(char, base_size, baseline) != 0:
            # A base can carry a subscript, then a superscript, then more subscript, because
            # the characters are read left to right. LaTeX allows only one of each, so the
            # pieces are collected and emitted once: _{j,\lambda}^{R}, not _{j}^{R}_{,\lambda}.
            subscripts: list[str] = []
            superscripts: list[str] = []
            while index < len(chars):
                script = _script_of(chars[index], base_size, baseline)
                if script == 0:
                    break
                run_indices = []
                while index < len(chars) and _script_of(chars[index], base_size, baseline) == script:
                    run_indices.append(index)
                    index += 1
                run = [chars[i] for i in run_indices]
                inner_size, inner_baseline = _dominant(run)
                inner_accents = {position: accents[i]
                                 for position, i in enumerate(run_indices) if i in accents}
                inner = chars_to_latex(run, inner_size, inner_baseline, inner_accents)
                if inner is None:
                    return None
                (superscripts if script == 1 else subscripts).append(inner.strip())
            flush_style()
            if subscripts:
                out.append("_{" + "".join(subscripts) + "}")
            if superscripts:
                out.append("^{" + "".join(superscripts) + "}")
            continue

        atom = _latex_atom(char)
        if atom is None:
            return None
        style = _script_style(char)
        accent = accents.get(index)
        if accent:
            flush_style()
            body = f"\\{style}{{{atom}}}" if style in ("mathbb", "mathcal", "mathbf") else atom
            out.append(f"{LATEX_ACCENT[accent]}{{{body}}}")
        elif style in ("mathrm", "mathsf", "mathtt", "mathbf", "mathbb", "mathcal") and char.c.isalpha():
            if pending_style != style:
                flush_style()
                pending_style = style
            style_buffer.append(atom)
        else:
            flush_style()
            out.append(atom)
        index += 1

    flush_style()
    latex = _join_tokens(out).strip()
    return latex or None


_COMMAND_TAIL = re.compile(r"\\[a-zA-Z]+$")


def _join_tokens(tokens: list[str]) -> str:
    """Join LaTeX tokens, inserting a space where a control word would otherwise swallow the
    next letter: '\\times' + 's' must become '\\times s', not '\\timess'."""
    out: list[str] = []
    for token in tokens:
        if out and token[:1].isalpha() and _COMMAND_TAIL.search(out[-1]):
            out.append(" ")
        out.append(token)
    return "".join(out)


# --------------------------------------------------------------------------------------
# HTML generation
# --------------------------------------------------------------------------------------

def _math_html(chars: list[Char], base_size: float, baseline: float) -> str:
    out: list[str] = []
    index = 0
    while index < len(chars):
        char = chars[index]
        if char.is_space:
            out.append(" ")
            index += 1
            continue
        if char.c == "̸" and index + 1 < len(chars):
            following = fix_unicode(chars[index + 1].c)
            if following in NEGATED:
                out.append(escape_html(NEGATED[following]))
                index += 2
                continue
        if _script_of(char, base_size, baseline) != 0:
            subscript_parts: list[str] = []
            superscript_parts: list[str] = []
            while index < len(chars):
                script = _script_of(chars[index], base_size, baseline)
                if script == 0:
                    break
                run = []
                while index < len(chars) and _script_of(chars[index], base_size, baseline) == script:
                    run.append(chars[index])
                    index += 1
                inner_size, inner_baseline = _dominant(run)
                rendered = _math_html(run, inner_size, inner_baseline)
                (superscript_parts if script == 1 else subscript_parts).append(rendered)
            if subscript_parts:
                out.append("<sub>" + "".join(subscript_parts) + "</sub>")
            if superscript_parts:
                out.append("<sup>" + "".join(superscript_parts) + "</sup>")
            continue
        text = escape_html(fix_unicode(char.c))
        if char.role == Role.MATH_VAR and char.c.isalpha():
            out.append(f"<i>{text}</i>")
        else:
            out.append(text)
        index += 1
    # collapse the italic runs that sit next to each other
    return "".join(out).replace("</i><i>", "")


def _prose_html(chars: list[Char], base_size: float, baseline: float) -> str:
    """Prose with emphasis, code, sub/superscripts and cross-reference links.

    A link may span emphasised text, so the anchor is the outer element and the style tag is
    closed and reopened around it."""
    out: list[str] = []
    index = 0
    open_tag: str | None = None
    open_link: str = ""

    def tag_for(char: Char) -> str | None:
        if char.role == Role.PROSE_ITALIC:
            return "em"
        if char.role == Role.PROSE_BOLD:
            return "strong"
        if char.role == Role.MONO:
            return "code"
        return None

    def close_style() -> None:
        nonlocal open_tag
        if open_tag:
            out.append(f"</{open_tag}>")
            open_tag = None

    def set_link(target: str) -> None:
        nonlocal open_link
        if target == open_link:
            return
        close_style()
        if open_link:
            out.append("</a>")
        if target:
            out.append(f'<a href="{link_href(target)}">')
        open_link = target

    while index < len(chars):
        char = chars[index]
        script = _script_of(char, base_size, baseline)
        if script != 0 and not char.is_space:
            run = [char]
            index += 1
            while index < len(chars) and _script_of(chars[index], base_size, baseline) == script:
                run.append(chars[index])
                index += 1
            inner_size, inner_baseline = _dominant(run)
            tag = "sup" if script == 1 else "sub"
            close_style()
            out.append(f"<{tag}>{_prose_html(run, inner_size, inner_baseline)}</{tag}>")
            continue
        if not char.is_space:
            set_link(char.link)
        wanted = tag_for(char) if not char.is_space else open_tag
        if wanted != open_tag:
            close_style()
            if wanted:
                out.append(f"<{wanted}>")
            open_tag = wanted
        out.append(escape_html(fix_unicode(char.c)))
        index += 1
    close_style()
    if open_link:
        out.append("</a>")
    return "".join(out)


def link_href(target: str) -> str:
    """Links are written as tokens and resolved once every block has an anchor."""
    if target.startswith("uri:"):
        return escape_html(target[4:])
    return "{{LINK:" + target + "}}"


def _run_key(chars: list[Char], latex: str | None) -> str:
    if latex:
        return latex
    return "".join(f"{family(c.font)}:{c.c}:{round(c.size, 1)}:{round(c.oy - chars[0].oy, 1)}"
                   for c in chars)


def insert_gap_spaces(chars: list[Char]) -> list[Char]:
    """The extractor emits no space where two spans merely sit apart on the page, which glues
    words together ("2.1.2How"). Insert a space wherever the horizontal gap is wide enough to
    be one."""
    if not chars:
        return chars
    out: list[Char] = [chars[0]]
    for char in chars[1:]:
        previous = out[-1]
        if not previous.is_space and not char.is_space:
            threshold = max(1.2, 0.2 * min(previous.size, char.size))
            if char.x0 - previous.x1 > threshold and abs(char.oy - previous.oy) < 2.5:
                out.append(Char(" ", previous.x1, previous.y0, char.x0, previous.y1,
                                previous.x1, previous.oy, previous.font, previous.size,
                                previous.colour, previous.role))
        out.append(char)
    return out


def build_inline(
    chars: list[Char],
    rules: list[tuple[float, float, float, float]] | None = None,
    force_math_tier: Tier | None = None,
) -> InlineResult:
    """Convert one line's characters into HTML, collecting the math runs that need rendering."""
    rules = rules or []
    if not chars:
        return InlineResult("")
    chars = insert_gap_spaces(chars)
    base_size, baseline = _dominant(chars)

    segments: list[tuple[bool, list[Char]]] = []
    for char in chars:
        math = char.role in (Role.MATH_VAR, Role.MATH_UP)
        if segments and segments[-1][0] == math:
            segments[-1][1].append(char)
        elif char.is_space and segments:
            segments[-1][1].append(char)
        else:
            segments.append((math, [char]))

    html_parts: list[str] = []
    runs: list[MathRun] = []
    for math, group in segments:
        if not math:
            html_parts.append(_prose_html(group, base_size, baseline))
            continue
        # trim leading/trailing spaces out of the math run itself
        lead = "".join(c.c for c in group[: len(group) - len(_lstrip(group))])
        core = _strip(group)
        trail_count = len(group) - len(lead) - len(core)
        trail = "".join(c.c for c in group[len(group) - trail_count:]) if trail_count > 0 else ""
        if not core:
            html_parts.append(escape_html("".join(c.c for c in group)))
            continue
        bbox = (
            min(c.x0 for c in core),
            min(c.y0 for c in core),
            max(c.x1 for c in core),
            max(c.y1 for c in core),
        )
        core, accent_map, wide_accent = attach_accents(core)
        if not core:
            html_parts.append(escape_html("".join(c.c for c in group)))
            continue
        latex = chars_to_latex(core, base_size, baseline, accent_map)
        has_extension = any(is_extension_font(c.font) or c.c == "�" for c in core)
        has_rule = _horizontal_rules(rules, bbox)
        has_accent = bool(accent_map)
        has_script_letter = any(_script_style(c) in ("mathcal", "mathbb") and c.c.isalpha() for c in core)

        if force_math_tier is not None:
            tier = force_math_tier
            reason = "forced"
        elif has_extension or has_rule or wide_accent or latex is None:
            tier = Tier.VLM
            if has_extension:
                reason = "extension-font"
            elif has_rule:
                reason = "fraction-or-radical-rule"
            elif wide_accent:
                reason = "wide-accent"
            else:
                reason = "unmapped-glyph"
        elif has_accent or has_script_letter:
            tier = Tier.LATEX
            reason = "accent" if has_accent else "script-letter"
        else:
            tier = Tier.TEXT
            reason = ""

        run = MathRun(
            chars=core,
            tier=tier,
            latex=latex or "",
            reason=reason,
            bbox=bbox,
        )
        run.key = _run_key(core, latex)
        if tier == Tier.TEXT:
            run.html = _math_html(core, base_size, baseline)
            links = {c.link for c in core if not c.is_space}
            if len(links) == 1 and (target := links.pop()):
                run.html = f'<a href="{link_href(target)}">{run.html}</a>'
            html_parts.append(lead + run.html + trail)
        else:
            html_parts.append(lead + f"\x00MATH{len(runs)}\x00" + trail)
            runs.append(run)
    return InlineResult("".join(html_parts), runs)


def _lstrip(chars: list[Char]) -> list[Char]:
    index = 0
    while index < len(chars) and chars[index].is_space:
        index += 1
    return chars[index:]


def _strip(chars: list[Char]) -> list[Char]:
    chars = _lstrip(chars)
    end = len(chars)
    while end > 0 and chars[end - 1].is_space:
        end -= 1
    return chars[:end]
