#!/usr/bin/env bash
# Render the story page to docs/conversion-story.pdf.
#
# index.html is a screen document: it follows the reader's dark mode and it has two
# boxes that scroll sideways. Paper does neither. So this prints a patched copy that
# is pinned to the light palette, unfolds the scrolling boxes, and keeps the small
# blocks from splitting across a page break.
#
# Run it after src/build_index.py, so the PDF matches the page.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/index.html"
TMP="$ROOT/.print-tmp.html"
OUT="$ROOT/docs/conversion-story.pdf"

CHROME="${CHROME:-google-chrome}"
if ! command -v "$CHROME" >/dev/null 2>&1; then
    echo "make_story_pdf: no Chrome on PATH. Set CHROME=/path/to/chrome and retry." >&2
    exit 1
fi

[ -f "$SRC" ] || { echo "make_story_pdf: $SRC is missing. Run src/build_index.py first." >&2; exit 1; }

mkdir -p "$ROOT/docs"
trap 'rm -f "$TMP"' EXIT

python3 - "$SRC" "$TMP" <<'PY'
import sys

src_path, tmp_path = sys.argv[1], sys.argv[2]
html = open(src_path, encoding="utf-8").read()

# The dark rules are guarded by :not([data-theme="light"]), so this pins the light palette.
patched = html.replace('<html lang="en">', '<html lang="en" data-theme="light">', 1)
if patched == html:
    raise SystemExit("make_story_pdf: could not find the <html> tag to patch")

# The tab title becomes the PDF's Title field.
patched = patched.replace(
    "<title>Reflowing ISLP</title>",
    "<title>ISLP PDF to EPUB - how the conversion works</title>",
    1,
)

PRINT_CSS = """
<style>
@media print {
  @page { size: A4; margin: 15mm 13mm 16mm 13mm; }
  html, body { background: #fff !important; }
  .wrap { max-width: none !important; padding: 0 !important; }
  header { padding: 0 0 14px !important; }
  footer { margin-top: 34px !important; }
  h1 { font-size: 25px !important; }
  h2 { font-size: 17px !important; }
  h2, h3 { break-after: avoid; page-break-after: avoid; }
  /* Hold the small blocks together. A whole attempt card is too big to keep whole: doing
     that left the bottom third of several pages empty, so it is allowed to split. */
  figure, table, pre, .tile, .svg-step, .shot, .check, .why, .disclaimer {
    break-inside: avoid; page-break-inside: avoid;
  }
  .attempt { orphans: 3; widows: 3; }
  .attempt-head { break-inside: avoid; break-after: avoid; }
  /* Paper cannot scroll: show every sideways-scrolling box in full. The wide diagram is
     hidden for print and the wrapped one shown, so neither needs a width override. */
  .pipeline { overflow: visible !important; }
  pre { overflow: visible !important; white-space: pre-wrap !important; word-break: break-word; }
  img, svg { max-width: 100% !important; height: auto !important; }
  a { text-decoration: none; color: inherit !important; }
  a[href^="http"]::after { content: " (" attr(href) ")"; font-size: 9px; color: #5a5a5a; }
  /* The rights block names three files in this repository. Printing all three URLs inside
     it breaks the line four times over; the footer prints the same URLs in full anyway. */
  .disclaimer .links a[href^="http"]::after { content: none; }
}
</style>
</head>"""

patched = patched.replace("</head>", PRINT_CSS, 1)
open(tmp_path, "w", encoding="utf-8").write(patched)
PY

"$CHROME" --headless --disable-gpu --no-sandbox \
    --force-color-profile=srgb \
    --no-pdf-header-footer \
    --virtual-time-budget=15000 \
    --print-to-pdf="$OUT" \
    "file://$TMP" >/dev/null 2>&1

[ -s "$OUT" ] || { echo "make_story_pdf: Chrome wrote nothing to $OUT" >&2; exit 1; }

# Headless Chrome only prints page numbers through its own header and footer, which stamps
# the temporary file:// path across the top. So they are written afterwards instead.
uv run python - "$OUT" <<'NUMBERS'
import sys

import pymupdf

doc = pymupdf.open(sys.argv[1])
for number, page in enumerate(doc, start=1):
    label = f"{number} / {doc.page_count}"
    width = pymupdf.get_text_length(label, fontname="helv", fontsize=8)
    page.insert_text(
        (page.rect.width / 2 - width / 2, page.rect.height - 24),
        label,
        fontname="helv",
        fontsize=8,
        color=(0.42, 0.42, 0.42),
    )
doc.saveIncr()
NUMBERS

echo "wrote $OUT ($(du -h "$OUT" | cut -f1), $(pdfinfo "$OUT" | awk '/^Pages/ {print $2}') pages)"
