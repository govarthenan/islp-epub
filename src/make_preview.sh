#!/usr/bin/env bash
# Unpack an EPUB into work/preview and add a browser-only stylesheet that mimics the
# Kobo Libra 2 reading conditions (1264 px wide, ~19 px serif body).
set -euo pipefail
cd "$(dirname "$0")/.."
EPUB="${1:-output/ISLP.epub}"
rm -rf work/preview && mkdir -p work/preview
( cd work/preview && unzip -q "../../$EPUB" )
python3 - <<'PY'
import pathlib
extra = ('<link rel="stylesheet" type="text/css" href="../css/style.css"/>'
         '<style>html{font-size:19px;font-family:Georgia,"Times New Roman",serif;}</style>')
for path in pathlib.Path("work/preview/OEBPS/text").glob("*.xhtml"):
    text = path.read_text()
    path.write_text(text.replace(
        '<link rel="stylesheet" type="text/css" href="../css/style.css"/>', extra))
print("preview ready in work/preview")
PY
