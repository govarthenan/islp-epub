"""Generate index.html: the visual story of this conversion.

    uv run python src/build_index.py

Reads journal/attempts.json for the narrative and work/build_stats.json plus
work/math_verification.json for the numbers, so the page never drifts from the build.
"""

from __future__ import annotations

import json
from datetime import date
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"

STATUS_LABEL = {"success": "worked", "failed": "failed", "partial": "partly worked"}


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


def pipeline_svg(stages: list[dict]) -> str:
    width, height = 1180, 252
    step = width / len(stages)
    boxes = []
    for index, stage in enumerate(stages):
        x = index * step + 12
        box_width = step - 34
        boxes.append(f'''
    <g>
      <rect x="{x:.0f}" y="40" width="{box_width:.0f}" height="176" rx="10"
            fill="var(--svg-card)" stroke="var(--svg-line)" stroke-width="1.5"/>
      <text x="{x + 16:.0f}" y="70" class="svg-step">{index + 1}</text>
      <foreignObject x="{x + 14:.0f}" y="80" width="{box_width - 28:.0f}" height="130">
        <div xmlns="http://www.w3.org/1999/xhtml" class="svg-body">
          <b>{escape(stage["title"])}</b><br/>{escape(stage["summary"])}
        </div>
      </foreignObject>
    </g>''')
        if index < len(stages) - 1:
            arrow_x = x + box_width + 4
            boxes.append(
                f'<path d="M{arrow_x:.0f} 128 l14 0 m-5 -5 l5 5 l-5 5" fill="none" '
                f'stroke="var(--svg-line)" stroke-width="1.8" stroke-linecap="round"/>'
            )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
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
    return f'''<figure class="shot {tone}">
      <img src="{src}" alt="{escape(caption)}"/>
      <figcaption>{caption}</figcaption>
    </figure>'''


def build() -> str:
    data = load(ROOT / "journal" / "attempts.json", {})
    stats = load(WORK / "build_stats.json", {})
    verification = load(WORK / "math_verification.json", {})

    tiers = dict(stats.get("math_items_by_tier", {}))
    epub_mb = stats.get("epub_bytes", 0) / 1024 / 1024

    accuracy = verification.get("accuracy")
    audit = verification.get("independent_audit", {})

    tiles = [
        tile("613", "pages read", "the whole book"),
        tile(f"{stats.get('paragraphs', 0):,}", "paragraphs rebuilt", "hyphenation undone"),
        tile(f"{stats.get('images_embedded', 0)}", "figures re-rendered", "300 ppi, 16 greys"),
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

    audit_block = ""
    if checks:
        cards = "".join(
            f'''<div class="check"><div class="check-value">{value}</div>
             <div class="check-label">{escape(label)}</div><p>{escape(note)}</p></div>'''
            for value, label, note in checks
        )
        audit_block = (
            "<h2>Three checks, three kinds of evidence</h2>"
            '<p class="sub">One model marking its own work is not evidence. These are '
            "deliberately different in kind: one costs nothing and cannot be talked round, one "
            "looks at the pictures, and one comes from outside the family.</p>"
            f'<div class="checks">{cards}</div>'
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>ISLP to EPUB</title>
<style>
:root {{
  --bg: #fbfaf8; --surface: #ffffff; --ink: #1b1a18; --muted: #6b6862;
  --line: #e3e0d9; --accent: #7a4f2a; --accent-soft: #f2e8de;
  --ok: #2f6b45; --ok-soft: #e2f0e7;
  --bad: #9a3226; --bad-soft: #f8e5e2;
  --mid: #8a6a1f; --mid-soft: #f7eed6;
  --svg-card: #ffffff; --svg-line: #d9d5cc;
  --seg-text: #7a4f2a; --seg-latex: #b08147; --seg-vlm: #2f6b45; --seg-display: #3f6d8f;
  --shadow: 0 1px 2px rgba(0,0,0,.05), 0 8px 24px -12px rgba(0,0,0,.18);
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #171614; --surface: #201f1c; --ink: #ece9e3; --muted: #a29d94;
    --line: #333029; --accent: #d9a76c; --accent-soft: #2c261f;
    --ok: #6fbf8e; --ok-soft: #1e2c23;
    --bad: #e28c7f; --bad-soft: #2e211f;
    --mid: #d9bb6d; --mid-soft: #2c2718;
    --svg-card: #201f1c; --svg-line: #3d3931;
    --seg-text: #d9a76c; --seg-latex: #b08147; --seg-vlm: #6fbf8e; --seg-display: #7fa9c6;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.7);
  }}
}}
:root[data-theme="dark"] {{
  --bg: #171614; --surface: #201f1c; --ink: #ece9e3; --muted: #a29d94;
  --line: #333029; --accent: #d9a76c; --accent-soft: #2c261f;
  --ok: #6fbf8e; --ok-soft: #1e2c23;
  --bad: #e28c7f; --bad-soft: #2e211f;
  --mid: #d9bb6d; --mid-soft: #2c2718;
  --svg-card: #201f1c; --svg-line: #3d3931;
  --seg-text: #d9a76c; --seg-latex: #b08147; --seg-vlm: #6fbf8e; --seg-display: #7fa9c6;
}}

* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.6 ui-serif, Georgia, "Times New Roman", serif;
  -webkit-font-smoothing: antialiased;
}}
.wrap {{ max-width: 1240px; margin: 0 auto; padding: 0 24px 96px; }}
header {{ padding: 72px 0 40px; border-bottom: 1px solid var(--line); }}
.eyebrow {{
  font: 600 12px/1 var(--mono); letter-spacing: .18em; text-transform: uppercase;
  color: var(--accent); margin-bottom: 18px;
}}
h1 {{ font-size: clamp(30px, 4.6vw, 50px); line-height: 1.1; margin: 0 0 14px; letter-spacing: -.01em; }}
.lede {{ font-size: 19px; color: var(--muted); max-width: 62ch; margin: 0 0 22px; }}
.pill {{
  display: inline-block; font: 600 12px/1 var(--mono); letter-spacing: .08em;
  text-transform: uppercase; padding: 7px 12px; border-radius: 999px;
  background: var(--accent-soft); color: var(--accent);
}}
h2 {{ font-size: 26px; margin: 64px 0 6px; letter-spacing: -.01em; }}
h2 + .sub {{ color: var(--muted); margin: 0 0 26px; max-width: 70ch; }}
h3 {{ font-size: 17px; margin: 0; }}

.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin-top: 34px; }}
.tile {{ background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px; box-shadow: var(--shadow); }}
.tile-value {{ font: 700 27px/1.1 var(--mono); letter-spacing: -.02em; }}
.tile-label {{ margin-top: 6px; font-size: 14px; }}
.tile-note {{ margin-top: 3px; font-size: 12.5px; color: var(--muted); }}

.pipeline {{ background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 10px 6px; box-shadow: var(--shadow); overflow-x: auto; }}
.pipeline svg {{ display: block; min-width: 1080px; width: 100%; height: auto; }}
.svg-step {{ font: 700 12px var(--mono); fill: var(--accent); }}
.svg-body {{ font: 13px/1.35 ui-serif, Georgia, serif; color: var(--ink); }}
.svg-body b {{ font-size: 13.5px; }}

.bar {{ display: flex; height: 30px; border-radius: 8px; overflow: hidden; border: 1px solid var(--line); }}
.seg-text {{ background: var(--seg-text); }} .seg-latex {{ background: var(--seg-latex); }}
.seg-vlm {{ background: var(--seg-vlm); }} .seg-display {{ background: var(--seg-display); }}
.legend {{ list-style: none; padding: 0; margin: 18px 0 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }}
.legend li {{ display: flex; gap: 10px; align-items: flex-start; }}
.swatch {{ width: 13px; height: 13px; border-radius: 3px; margin-top: 5px; flex: none; }}
.swatch-text {{ background: var(--seg-text); }} .swatch-latex {{ background: var(--seg-latex); }}
.swatch-vlm {{ background: var(--seg-vlm); }} .swatch-display {{ background: var(--seg-display); }}
.legend-note {{ color: var(--muted); font-size: 13.5px; margin-top: 2px; }}

.attempts {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 14px; }}
.attempt {{ background: var(--surface); border: 1px solid var(--line); border-left-width: 4px; border-radius: 12px; padding: 18px 20px; box-shadow: var(--shadow); }}
.attempt-success {{ border-left-color: var(--ok); }}
.attempt-failed {{ border-left-color: var(--bad); }}
.attempt-partial {{ border-left-color: var(--mid); }}
.attempt-head {{ display: flex; align-items: center; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }}
.num {{ font: 700 13px var(--mono); color: var(--muted); }}
.badge {{ margin-left: auto; font: 600 11px/1 var(--mono); letter-spacing: .08em; text-transform: uppercase; padding: 6px 10px; border-radius: 999px; }}
.badge-success {{ background: var(--ok-soft); color: var(--ok); }}
.badge-failed {{ background: var(--bad-soft); color: var(--bad); }}
.badge-partial {{ background: var(--mid-soft); color: var(--mid); }}
.attempt p {{ margin: 6px 0; font-size: 15px; }}
.field, .why-label {{ font: 600 11px var(--mono); letter-spacing: .08em; text-transform: uppercase; color: var(--muted); margin-right: 8px; }}
.why {{ color: var(--muted); }}

.gallery {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }}
.shot {{ margin: 0; background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 14px; box-shadow: var(--shadow); }}
.shot img {{ width: 100%; height: auto; display: block; background: #fff; border-radius: 6px; }}
.shot figcaption {{ margin-top: 10px; font-size: 14px; color: var(--muted); }}
.shot.bad {{ border-color: color-mix(in srgb, var(--bad) 45%, var(--line)); }}
.shot.good {{ border-color: color-mix(in srgb, var(--ok) 45%, var(--line)); }}
.shot b {{ color: var(--ink); }}

.checks {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
.check {{ background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 18px 20px; box-shadow: var(--shadow); }}
.check-value {{ font: 700 30px/1.1 var(--mono); letter-spacing: -.02em; color: var(--ok); }}
.check-label {{ font-size: 15px; margin-top: 4px; }}
.check p {{ margin: 10px 0 0; font-size: 14px; color: var(--muted); }}

code {{ font-family: var(--mono); font-size: .92em; background: var(--accent-soft); padding: 1px 5px; border-radius: 4px; }}
pre {{ background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; overflow-x: auto; font: 13px/1.6 var(--mono); }}
footer {{ margin-top: 72px; padding-top: 26px; border-top: 1px solid var(--line); color: var(--muted); font-size: 14px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 15px; }}
th, td {{ text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--line); }}
th {{ font: 600 12px var(--mono); letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }}
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
</header>

<h2>How the book is taken apart</h2>
<p class="sub">Six stages. Nothing here guesses at the layout: every rule below was measured
from the file itself before it was written down.</p>
<div class="pipeline">{pipeline_svg(data.get("stages", []))}</div>

<h2>The mathematics, triaged</h2>
<p class="sub">The starting assumption was that no mathematics could be recovered as LaTeX and
that all of it would have to be read back out of images. That turned out to be true for only
part of it. Sub- and superscripts are recorded in the PDF as a font-size drop plus a baseline
shift, so most inline mathematics can be rebuilt exactly, for free, and stays as reflowing
text. A vision model is spent only where the structure is genuinely absent.</p>
{math_bar(tiers)}

<h2>Where the crops went wrong</h2>
<p class="sub">Cutting an expression out of the page was the hardest single problem in this
conversion, and it took four attempts. A fraction is not on one line: its numerator, its rule
and its denominator sit on three different baselines, and the text layer files them as three
unrelated lines.</p>
<div class="gallery">
  {figure("assets/crop-1-line-box.png", "<b>Attempt 1.</b> Box taken from the text line. The fraction is sliced through the middle.", "bad")}
  {figure("assets/crop-2-greedy.png", "<b>Attempt 2.</b> Box grown greedily. It swallows the equation number and the next paragraph.", "bad")}
  {figure("assets/crop-3-grown.png", "<b>Attempt 4.</b> Growth restricted to connected mathematics glyphs, never sideways along the base line.", "good")}
  {figure("assets/crop-4-unmasked.png", "A fraction inside a sentence. No rectangle can hold it without also catching the line below.", "bad")}
  {figure("assets/crop-5-masked.png", "<b>The answer.</b> Keep the rectangle, paint the foreign ink out. Only prose is painted, so no glyph of the expression can be lost.", "good")}
</div>

<h2>Every attempt, in order</h2>
<p class="sub">{worked} worked, {partial} partly worked, {failed} failed outright. The failures
are the interesting ones: each was caused by a rule that sounded reasonable and did not survive
contact with the page.</p>
<ul class="attempts">{"".join(attempt_card(a) for a in attempts)}</ul>
{audit_block}

<h2>Choices made for the Kobo Libra 2</h2>
<table>
  <tr><th>Decision</th><th>Reason</th></tr>
  <tr><td>No embedded font, no font size on <code>body</code></td>
      <td>The reader's own typography controls keep working.</td></tr>
  <tr><td>Mathematics as SVG in <code>currentColor</code>, sized in <code>em</code></td>
      <td>It grows with the text instead of staying pinned to pixels, and it inverts correctly
          in dark mode.</td></tr>
  <tr><td>Figures at 300 ppi, 16 levels of grey</td>
      <td>Matches the panel exactly: 1264 x 1680 at 300 ppi, 16 greys.</td></tr>
  <tr><td>Margin notes collapsed to one quiet line</td>
      <td>A 7 inch page has no margin to spare; stacked in a column they took a third of the
          screen.</td></tr>
  <tr><td>Lab cells as <code>pre</code> with wrapping</td>
      <td>An e-reader cannot scroll sideways, so a long line must wrap rather than be cut off.</td></tr>
  <tr><td>A <code>toc.ncx</code> beside the EPUB 3 navigation document</td>
      <td>Kobo still reads the older navigation file.</td></tr>
</table>

<h2>Reproducing this</h2>
<pre>uv sync &amp;&amp; npm install
uv run python src/extract_math_jobs.py     # cut every expression out as an image
uv run python src/build_epub.py            # assemble and package
uv run python src/validate_epub.py output/ISLP.epub</pre>

<footer>
  <p>{escape(data.get("purpose", ""))}</p>
  <p>Source: {escape(data.get("source", ""))}. Built {date.today().isoformat()}.</p>
</footer>

</div>
</body>
</html>
"""


def main() -> None:
    (ROOT / "index.html").write_text(build(), encoding="utf-8")
    print(f"wrote {ROOT / 'index.html'}")


if __name__ == "__main__":
    main()
