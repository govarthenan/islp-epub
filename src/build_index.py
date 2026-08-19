"""Generate index.html: the visual story of this conversion.

    uv run python src/build_index.py

Reads docs/attempts.json for the narrative and work/build_stats.json plus
work/math_verification.json for the numbers, so the page never drifts from the build.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"

STATUS_LABEL = {"success": "worked", "failed": "failed", "partial": "partly worked"}

# The page counts its own stages and checks, so a heading cannot fall out of step with
# the JSON it is built from.
NUMBER_WORD = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight"}


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def tile(value: str, label: str, note: str = "") -> str:
    extra = f'<div class="tile-note">{escape(note)}</div>' if note else ""
    return (
        f'<div class="tile"><div class="tile-value">{value}</div>'
        f'<div class="tile-label">{escape(label)}</div>{extra}</div>'
    )


def pipeline_svg(stages: list[dict], per_row: int = 0) -> str:
    """The stages as boxes joined by arrows.

    per_row wraps them onto more than one row. A single row of six is right on a screen
    that scrolls sideways; on A4 it squeezes to a third of a millimetre per character, so
    the printed page uses two rows of three. The box pitch is the same either way, so the
    two drawings are the same size on the page.
    """
    per_row = per_row or len(stages)
    rows = -(-len(stages) // per_row)
    step = 1180 / 6  # the box pitch, one row or several
    top, box_height, row_gap, bottom = 40, 176, 30, 36
    width = step * per_row
    height = top + rows * box_height + (rows - 1) * row_gap + bottom
    box_width = step - 34
    boxes = []
    for index, stage in enumerate(stages):
        column, row = index % per_row, index // per_row
        x = column * step + 12
        y = top + row * (box_height + row_gap)
        boxes.append(f'''
    <g>
      <rect x="{x:.0f}" y="{y:.0f}" width="{box_width:.0f}" height="{box_height:.0f}"
            fill="var(--svg-card)" stroke="var(--rule)" stroke-width="1"/>
      <rect x="{x:.0f}" y="{y:.0f}" width="{box_width:.0f}" height="2" fill="var(--link)"
            opacity="0.35"/>
      <text x="{x + 16:.0f}" y="{y + 30:.0f}" class="svg-step">{index + 1}</text>
      <foreignObject x="{x + 14:.0f}" y="{y + 40:.0f}" width="{box_width - 28:.0f}" height="130">
        <div xmlns="http://www.w3.org/1999/xhtml" class="svg-body">
          <b>{escape(stage["title"])}</b><br/>{escape(stage["summary"])}
        </div>
      </foreignObject>
    </g>''')
        # An arrow joins two boxes on one row. At a row break there is none: the numbers
        # carry the order, and an arrow pointing off the edge would mislead.
        if index < len(stages) - 1 and column < per_row - 1:
            boxes.append(
                f'<path d="M{x + box_width + 4:.0f} {y + box_height / 2:.0f} l14 0 m-5 -5 l5 5 l-5 5" fill="none" '
                f'stroke="var(--rule-strong)" stroke-width="1.4" stroke-linecap="square"/>'
            )
    return (
        f'<svg viewBox="0 0 {width:.0f} {height:.0f}" role="img" '
        f'aria-label="Conversion pipeline in {len(stages)} stages">'
        f"<title>Conversion pipeline</title>{''.join(boxes)}</svg>"
    )


def math_bar(counts: dict[str, int]) -> str:
    order = [
        (
            "text",
            "Plain HTML",
            "Sub- and superscripts recovered from glyph geometry. Reflows and scales; costs nothing.",
        ),
        (
            "latex",
            "LaTeX from the character stream",
            "Accents and script letters, generated deterministically, then typeset by MathJax.",
        ),
        (
            "vlm",
            "Read by a vision model",
            "Fractions, radicals and large operators: structure the PDF simply does not record.",
        ),
        (
            "display",
            "Display equations",
            "Every centred equation, read from an image and verified against a re-typeset copy.",
        ),
    ]
    total = sum(counts.get(key, 0) for key, _, _ in order) or 1
    segments, legend = [], []
    for key, label, note in order:
        value = counts.get(key, 0)
        if not value:
            continue
        share = value / total * 100
        segments.append(
            f'<div class="seg seg-{key}" style="width:{share:.2f}%" title="{escape(label)}: {value}"></div>'
        )
        legend.append(f"""<li><span class="swatch swatch-{key}"></span>
          <div><b>{value:,}</b> &middot; {escape(label)}
          <div class="legend-note">{escape(note)}</div></div></li>""")
    return f'<div class="bar">{"".join(segments)}</div><ul class="legend">{"".join(legend)}</ul>'


def attempt_card(attempt: dict) -> str:
    status = attempt["status"]
    why = (
        f'<p class="why"><span class="why-label">Why</span> {escape(attempt["why"])}</p>' if attempt.get("why") else ""
    )
    return f"""
    <li class="attempt attempt-{status}">
      <div class="attempt-head">
        <span class="num">{attempt["n"]:02d}</span>
        <h3>{escape(attempt["title"])}</h3>
        <span class="badge badge-{status}">{STATUS_LABEL[status]}</span>
      </div>
      <p class="what"><span class="field">Tried</span> {escape(attempt["what"])}</p>
      <p class="result"><span class="field">Result</span> {escape(attempt["result"])}</p>
      {why}
    </li>"""


def figure(src: str, caption: str, tone: str = "") -> str:
    """One picture with its caption. The caption may carry markup; the alt text may not,
    so the tags are stripped rather than escaped -- escaping made a reader announce a
    literal "<b>"."""
    alt = re.sub(r"<[^>]+>", "", caption)
    return f'''<figure class="shot {tone}">
      <img src="{src}" alt="{escape(alt)}"/>
      <figcaption>{caption}</figcaption>
    </figure>'''


def input_date(paths: list[Path]) -> str:
    """The date of the newest input file. The footer used today's date, which rewrote
    index.html and the whole PDF on every rebuild even when no input had changed."""
    stamps = [path.stat().st_mtime for path in paths if path.exists()]
    return date.fromtimestamp(max(stamps)).isoformat() if stamps else date.today().isoformat()


def build() -> str:
    inputs = [ROOT / "docs" / "attempts.json", WORK / "build_stats.json", WORK / "math_verification.json"]
    data = load(inputs[0], {})
    stats = load(inputs[1], {})
    verification = load(inputs[2], {})

    tiers = dict(stats.get("math_items_by_tier", {}))
    epub_mb = stats.get("epub_bytes", 0) / 1e6  # decimal MB, as a file manager and GitHub report it

    accuracy = verification.get("accuracy")
    audit = verification.get("independent_audit", {})

    tiles = [
        tile("613", "pages read", "the whole book"),
        tile(f"{stats.get('paragraphs', 0):,}", "paragraphs rebuilt", "hyphenation undone"),
        tile(f"{stats.get('images_embedded', 0)}", "figures re-rendered", "300 ppi, in colour"),
        tile(f"{stats.get('tables_as_markup', 0)}", "tables as markup", "they reflow, not pictures"),
        tile(f"{stats.get('equations_display', 0)}", "display equations", "every one checked"),
        tile(f"{stats.get('code_cells', 0):,}", "lab code cells", "input and output kept apart"),
        tile(f"{stats.get('links_resolved', 0):,}", "cross-references", "all of them resolved"),
        tile(f"{epub_mb:.1f} MB", "finished EPUB", "reflowable, EPUB 3"),
    ]
    if accuracy is not None:
        tiles.append(tile(f"{accuracy:.1f}%", "mathematics agreed", "candidate matched the printed page"))

    status_note = (
        "Verified and packaged." if accuracy is not None else "Built and packaged; verification pass in progress."
    )

    stages = data.get("stages", [])
    attempts = data.get("attempts", [])
    worked = sum(1 for a in attempts if a["status"] == "success")
    failed = sum(1 for a in attempts if a["status"] == "failed")
    partial = len(attempts) - worked - failed

    symbols = verification.get("symbol_check", {})
    checks = []
    if symbols.get("scored"):
        checks.append(
            (
                f"{symbols['no_symbol_lost_share']}%",
                "lose no symbol",
                "Deterministic and free. The PDF's text layer loses structure but not symbols, so "
                "the symbols a transcription claims can be compared against the symbols the page "
                f"holds. {symbols['scored']} expressions had enough symbols to score; mean "
                f"agreement {symbols['mean_agreement']}.",
            )
        )
    if verification.get("checked"):
        counts = verification.get("verdicts", {})
        checks.append(
            (
                f"{verification['accuracy']}%",
                "agree with the page",
                f"Every one of the {verification['checked']} expressions was typeset, put under "
                "the crop from the PDF, and handed to an agent told to find the difference. "
                f"{counts.get('same', 0)} identical, {counts.get('cosmetic', 0)} differing only "
                f"in spacing or delimiter size, {counts.get('wrong', 0)} genuinely wrong and "
                "corrected.",
            )
        )
    if audit:
        checks.append(
            (
                f"{audit.get('agreement', 0):.0f}%",
                "confirmed from outside",
                f"A sample of {audit.get('sampled', 0)} of the same comparisons was re-read by a "
                "different model family entirely, through OpenAI's codex command line tool, with "
                "no sight of the earlier answers. This is the only figure here not produced by "
                "the model that did the work.",
            )
        )

    sections = [
        ("taken-apart", "How the book is taken apart"),
        ("triaged", "The mathematics, triaged"),
        ("crops", "Where the crops went wrong"),
        ("attempts", "Every attempt, in order"),
    ]
    if checks:
        count = NUMBER_WORD[len(checks)]
        sections.append(("checks", f"{count} checks, {count.lower()} kinds of evidence"))
    sections += [("choices", "Choices made for the reader, not for one device"), ("reproducing", "Reproducing this")]
    titles = dict(sections)

    def heading(key: str) -> str:
        return f'<h2 id="{key}">{escape(titles[key])}</h2>'

    contents = "".join(f'<li><a href="#{key}">{escape(title)}</a></li>' for key, title in sections)

    audit_block = ""
    if checks:
        cards = "".join(
            f"""<div class="check"><div class="check-value">{value}</div>
             <div class="check-label">{escape(label)}</div><p>{escape(note)}</p></div>"""
            for value, label, note in checks
        )
        audit_block = (
            heading("checks") + '<p class="sub">One model marking its own work is not evidence. These are '
            "deliberately different in kind: one costs nothing and cannot be talked round, one "
            "looks at the pictures, and one comes from outside the family.</p>"
            f'<div class="checks">{cards}</div>'
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Reflowing ISLP</title>
<style>
/* The palette is the book's own colour table, measured out of the PDF during the conversion:
   #000000 prose, #0068b4 cross-references, #984100 lab code, #595959 margin notes. The ground
   is a cool paper grey rather than cream, because that is what e-ink actually looks like. */
:root {{
  --paper: #fbfbfa; --surface: #ffffff; --ink: #16181b; --muted: #5a5a5a;
  --rule: #dedee0; --rule-strong: #b9babd;
  --link: #0068b4; --link-soft: #e7f0f8;
  --code: #984100; --code-soft: #f6ece4;
  --ok: #1f6f4a; --ok-soft: #e4f0ea;
  --bad: #a3312a; --bad-soft: #f7e7e5;
  --mid: #856214; --mid-soft: #f4eddc;
  --seg-text: #16181b; --seg-latex: #984100; --seg-vlm: #0068b4; --seg-display: #6f8fa6;
  --svg-card: #ffffff;
  --serif: ui-serif, Georgia, "Iowan Old Style", "Times New Roman", serif;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  --shadow: none;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --paper: #131518; --surface: #191c20; --ink: #e8e8e6; --muted: #9a9c9f;
    --rule: #2b2f34; --rule-strong: #454a51;
    --link: #6fb4e8; --link-soft: #17242e;
    --code: #d59258; --code-soft: #241a13;
    --ok: #6cc094; --ok-soft: #15241c;
    --bad: #e08b83; --bad-soft: #2a1a19;
    --mid: #d3b263; --mid-soft: #262014;
    --seg-text: #e8e8e6; --seg-latex: #d59258; --seg-vlm: #6fb4e8; --seg-display: #8fb0c6;
    --svg-card: #191c20;
  }}
}}
:root[data-theme="dark"] {{
  --paper: #131518; --surface: #191c20; --ink: #e8e8e6; --muted: #9a9c9f;
  --rule: #2b2f34; --rule-strong: #454a51;
  --link: #6fb4e8; --link-soft: #17242e;
  --code: #d59258; --code-soft: #241a13;
  --ok: #6cc094; --ok-soft: #15241c;
  --bad: #e08b83; --bad-soft: #2a1a19;
  --mid: #d3b263; --mid-soft: #262014;
  --seg-text: #e8e8e6; --seg-latex: #d59258; --seg-vlm: #6fb4e8; --seg-display: #8fb0c6;
  --svg-card: #191c20;
}}

* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--paper); color: var(--ink);
  font: 16px/1.62 var(--serif);
  -webkit-font-smoothing: antialiased;
}}
.wrap {{ max-width: 1180px; margin: 0 auto; padding: 0 28px 110px; }}

/* A hairline with a tick at its left end: the page's structural motif, borrowed from the
   baselines and bounding boxes the whole project is about. */
.rule {{ border: 0; border-top: 1px solid var(--rule); margin: 0; position: relative; }}
.rule::before {{
  content: ""; position: absolute; left: 0; top: -4px; width: 1px; height: 9px;
  background: var(--rule-strong);
}}

header {{ padding: 84px 0 40px; }}
.eyebrow {{
  font: 600 11.5px/1 var(--mono); letter-spacing: .2em; text-transform: uppercase;
  color: var(--link); margin-bottom: 22px;
}}
h1 {{ font-size: clamp(33px, 5vw, 54px); line-height: 1.06; margin: 0 0 16px; letter-spacing: -.015em; text-wrap: balance; }}
.lede {{ font-size: 19.5px; color: var(--muted); max-width: 60ch; margin: 0 0 24px; }}
.pill {{
  display: inline-block; font: 600 11px/1 var(--mono); letter-spacing: .12em;
  text-transform: uppercase; padding: 7px 12px; border: 1px solid var(--rule-strong);
  color: var(--muted);
}}
h2 {{
  font-size: 27px; margin: 76px 0 6px; letter-spacing: -.012em; text-wrap: balance;
  padding-top: 16px; border-top: 1px solid var(--rule); position: relative;
}}
h2::before {{
  content: ""; position: absolute; left: 0; top: -4px; width: 1px; height: 9px;
  background: var(--link);
}}
h2 + .sub {{ color: var(--muted); margin: 0 0 28px; max-width: 68ch; font-size: 16.5px; }}
h3 {{ font-size: 17px; margin: 0; }}

.contents {{ margin-top: 34px; padding-top: 18px; border-top: 1px solid var(--rule); }}
.contents-label {{
  font: 600 10.5px/1 var(--mono); letter-spacing: .12em; text-transform: uppercase;
  color: var(--muted); margin-bottom: 12px;
}}
.contents ol {{
  list-style: none; padding: 0; margin: 0; counter-reset: toc;
  display: grid; grid-template-columns: repeat(auto-fit, minmax(252px, 1fr)); gap: 5px 26px;
}}
.contents li {{ counter-increment: toc; font-size: 15px; }}
.contents li::before {{
  content: counter(toc, decimal-leading-zero) "  ";
  font: 600 11.5px var(--mono); color: var(--muted);
}}
.contents a {{ text-decoration: none; }}
.contents a:hover {{ text-decoration: underline; }}

.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(158px, 1fr)); gap: 0; margin-top: 40px; border-top: 1px solid var(--rule); }}
.tile {{ padding: 18px 20px 20px 0; border-bottom: 1px solid var(--rule); }}
.tile-value {{ font: 600 27px/1.05 var(--mono); letter-spacing: -.03em; font-variant-numeric: tabular-nums; }}
.tile-label {{ margin-top: 7px; font-size: 14.5px; }}
.tile-note {{ margin-top: 2px; font-size: 12.5px; color: var(--muted); }}

.pipeline {{ border: 1px solid var(--rule); padding: 8px 4px; overflow-x: auto; }}
.pipeline svg {{ display: block; width: 100%; height: auto; }}
/* Six across needs a scroll bar on a narrow screen; two rows of three fit A4. */
.pipeline-wide svg {{ min-width: 1060px; }}
.pipeline-tall {{ display: none; }}
@media print {{
  .pipeline-wide {{ display: none; }}
  .pipeline-tall {{ display: block; }}
}}
.svg-step {{ font: 600 11px var(--mono); fill: var(--link); }}
.svg-body {{ font: 13px/1.36 var(--serif); color: var(--ink); }}
.svg-body b {{ font-size: 13.5px; }}

.bar {{ display: flex; height: 26px; overflow: hidden; border: 1px solid var(--rule); }}
.seg-text {{ background: var(--seg-text); }} .seg-latex {{ background: var(--seg-latex); }}
.seg-vlm {{ background: var(--seg-vlm); }} .seg-display {{ background: var(--seg-display); }}
.legend {{ list-style: none; padding: 0; margin: 20px 0 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 18px; }}
.legend li {{ display: flex; gap: 10px; align-items: flex-start; }}
.swatch {{ width: 11px; height: 11px; margin-top: 6px; flex: none; }}
.swatch-text {{ background: var(--seg-text); }} .swatch-latex {{ background: var(--seg-latex); }}
.swatch-vlm {{ background: var(--seg-vlm); }} .swatch-display {{ background: var(--seg-display); }}
.legend b {{ font-family: var(--mono); font-variant-numeric: tabular-nums; }}
.legend-note {{ color: var(--muted); font-size: 13.5px; margin-top: 3px; }}

.attempts {{ list-style: none; padding: 0; margin: 0; }}
.attempt {{ padding: 20px 0 22px 22px; border-top: 1px solid var(--rule); border-left: 2px solid var(--rule); }}
.attempt-success {{ border-left-color: var(--ok); }}
.attempt-failed {{ border-left-color: var(--bad); }}
.attempt-partial {{ border-left-color: var(--mid); }}
.attempt-head {{ display: flex; align-items: baseline; gap: 13px; margin-bottom: 9px; flex-wrap: wrap; }}
.num {{ font: 600 12.5px var(--mono); color: var(--muted); font-variant-numeric: tabular-nums; }}
.badge {{ margin-left: auto; font: 600 10.5px/1 var(--mono); letter-spacing: .12em; text-transform: uppercase; padding: 5px 9px; }}
.badge-success {{ background: var(--ok-soft); color: var(--ok); }}
.badge-failed {{ background: var(--bad-soft); color: var(--bad); }}
.badge-partial {{ background: var(--mid-soft); color: var(--mid); }}
.attempt p {{ margin: 5px 0; font-size: 15.5px; max-width: 84ch; }}
.field, .why-label {{ font: 600 10.5px var(--mono); letter-spacing: .12em; text-transform: uppercase; color: var(--muted); margin-right: 9px; }}
.why {{ color: var(--muted); }}

.gallery {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(268px, 1fr)); gap: 20px; }}
.shot {{ margin: 0; border: 1px solid var(--rule); padding: 0; }}
.shot img {{ width: 100%; height: auto; display: block; background: #fff; padding: 12px; }}
.shot figcaption {{ margin: 0; padding: 12px 14px 14px; font-size: 14px; color: var(--muted); border-top: 1px solid var(--rule); }}
.shot.bad {{ border-color: color-mix(in srgb, var(--bad) 40%, var(--rule)); }}
.shot.good {{ border-color: color-mix(in srgb, var(--ok) 40%, var(--rule)); }}
.shot b {{ color: var(--ink); }}

.checks {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(272px, 1fr)); gap: 0; border-top: 1px solid var(--rule); }}
.check {{ padding: 20px 24px 24px 0; border-bottom: 1px solid var(--rule); }}
.check-value {{ font: 600 32px/1.05 var(--mono); letter-spacing: -.03em; color: var(--ok); font-variant-numeric: tabular-nums; }}
.check-label {{ font-size: 15px; margin-top: 5px; }}
.check p {{ margin: 11px 0 0; font-size: 14px; color: var(--muted); max-width: 46ch; }}

code {{ font-family: var(--mono); font-size: .9em; color: var(--code); }}
pre {{ border: 1px solid var(--rule); padding: 15px 17px; overflow-x: auto; font: 13px/1.65 var(--mono); }}
footer {{ margin-top: 84px; padding-top: 26px; border-top: 1px solid var(--rule); color: var(--muted); font-size: 14px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 15.5px; }}
th, td {{ text-align: left; padding: 11px 14px 11px 0; border-bottom: 1px solid var(--rule); vertical-align: top; }}
th {{ font: 600 10.5px var(--mono); letter-spacing: .12em; text-transform: uppercase; color: var(--muted); }}
a {{ color: var(--link); }}
</style>
</head>
<body>
<div class="wrap">

<header>
  <div class="eyebrow">PDF &rarr; EPUB &middot; build log</div>
  <h1>{escape(data.get("project", "PDF to EPUB"))}</h1>
  <p class="lede">{escape(data.get("subtitle", ""))}</p>
  <span class="pill">{escape(status_note)}</span>
  <div class="tiles">{"".join(tiles)}</div>
  <nav class="contents" aria-label="Contents">
    <div class="contents-label">Contents</div>
    <ol>{contents}</ol>
  </nav>
</header>

{heading("taken-apart")}
<p class="sub">{NUMBER_WORD[len(stages)]} stages. Nothing here guesses at the layout: every rule
below was measured from the file itself before it was written down.</p>
<div class="pipeline pipeline-wide">{pipeline_svg(stages)}</div>
<div class="pipeline pipeline-tall">{pipeline_svg(stages, per_row=3)}</div>

{heading("triaged")}
<p class="sub">The starting assumption was that no mathematics could be recovered as LaTeX and
that all of it would have to be read back out of images. That turned out to be true for only
part of it. Sub- and superscripts are recorded in the PDF as a font-size drop plus a baseline
shift, so most inline mathematics can be rebuilt exactly, for free, and stays as reflowing
text. A vision model is spent only where the structure is genuinely absent.</p>
{math_bar(tiers)}

{heading("crops")}
<p class="sub">Cutting an expression out of the page was the hardest single problem in this
conversion, and it took four attempts. A fraction is not on one line: its numerator, its rule
and its denominator sit on three different baselines, and the text layer files them as three
unrelated lines.</p>
<div class="gallery">
  {figure("assets/crop-1-line-box.png", "<b>Attempt 1.</b> Box taken from the text line. The fraction is sliced through the middle.", "bad")}
  {figure("assets/crop-2-greedy.png", "<b>Attempt 2.</b> Box grown greedily. It swallows the equation number and the next paragraph.", "bad")}
  {figure("assets/crop-3-clamped.png", "<b>Attempt 3.</b> Box clamped to the baselines above and below. The clamp lands inside the expression: here it cuts the numerator off.", "bad")}
  {figure("assets/crop-4-grown.png", "<b>Attempt 4.</b> Growth restricted to connected mathematics glyphs, never sideways along the base line.", "good")}
  {figure("assets/crop-5-unmasked.png", "A fraction inside a sentence. No rectangle can hold it without also catching the line below.", "bad")}
  {figure("assets/crop-6-masked.png", "<b>The answer.</b> Keep the rectangle, paint the foreign ink out. Only prose is painted, so no glyph of the expression can be lost.", "good")}
</div>

{heading("attempts")}
<p class="sub">{worked} worked, {partial} partly worked, {failed} failed outright. The failures
are the interesting ones: each was caused by a rule that sounded reasonable and did not survive
contact with the page.</p>
<ul class="attempts">{"".join(attempt_card(a) for a in attempts)}</ul>
{audit_block}

{heading("choices")}
<table>
  <tr><th>Decision</th><th>Reason</th></tr>
  <tr><td>No embedded font, no font size on <code>body</code></td>
      <td>The reader's own typography controls keep working.</td></tr>
  <tr><td>Mathematics as SVG sized in <code>em</code>, each file carrying its own
          colour scheme</td>
      <td>It grows with the text instead of staying pinned to pixels. An <code>&lt;img&gt;</code>
          is a separate document, so <code>currentColor</code> alone always painted the
          mathematics black; the two rules inside each file let it follow a dark theme.</td></tr>
  <tr><td>Figures at 300 ppi, in colour</td>
      <td>The book draws one series in orange and the next in blue, and the two have almost the
          same luminance. A grey rendering painted them the same shade, and the series could not
          be told apart. A grey screen converts the colour itself.</td></tr>
  <tr><td>No colour set without its partner, and a dark-scheme block</td>
      <td>A reader that repaints the page with its own colours cannot then leave dark text on a
          light block.</td></tr>
  <tr><td>Margin notes collapsed to one quiet line</td>
      <td>A 7 inch page has no margin to spare; stacked in a column they took a third of the
          screen.</td></tr>
  <tr><td>Lab cells as <code>pre</code> with wrapping</td>
      <td>An e-reader cannot scroll sideways, so a long line must wrap rather than be cut off.</td></tr>
  <tr><td>A <code>toc.ncx</code> beside the EPUB 3 navigation document</td>
      <td>Kobo still reads the older navigation file.</td></tr>
</table>

{heading("reproducing")}
<pre>uv sync &amp;&amp; npm install

uv run python src/probe_structure.py     # chapters, index, page zones
uv run python src/extract_math_jobs.py   # crop every expression to read
# transcription and verification write work/math_final.json
uv run python src/build_epub.py --out ISLP.epub
uv run python src/validate_epub.py output/ISLP.epub
uv run python src/build_index.py         # regenerate this page
./src/make_story_pdf.sh                  # and its PDF</pre>

<footer>
  <p>{escape(data.get("purpose", ""))}</p>
  <p>Source: {escape(data.get("source", ""))}. Built {input_date(inputs)}.</p>
</footer>

</div>
</body>
</html>
"""


def inline_assets(html: str) -> str:
    """Fold the pictures into the page as data URIs, for publishing somewhere that has no
    access to the repository's assets directory."""
    import base64
    import re as regex

    def replace(match: regex.Match) -> str:
        path = ROOT / match.group(1)
        if not path.exists():
            return match.group(0)
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f'src="data:image/png;base64,{encoded}"'

    return regex.sub(r'src="(assets/[^"]+)"', replace, html)


def main() -> None:
    html = build()
    (ROOT / "index.html").write_text(html, encoding="utf-8")
    print(f"wrote {ROOT / 'index.html'}")
    if "--inline" in sys.argv:
        target = ROOT / "work" / "reflowing-islp.html"
        target.write_text(inline_assets(html), encoding="utf-8")
        print(f"wrote {target} ({target.stat().st_size // 1024} KB, self-contained)")


if __name__ == "__main__":
    main()
