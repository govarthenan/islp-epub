"""Check that generated table markup parses as XML and is rectangular.

    uv run python src/check_table_html.py work/table_parts/000.json

EPUB documents are parsed as XML, so an unclosed tag or an unquoted attribute breaks the whole
file. This also counts the cells in each row, because a table with a short row renders as a
ragged mess on a narrow screen.
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

WRAPPER = "<root xmlns:epub=\"http://www.idpf.org/2007/ops\">{0}</root>"


def row_widths(table: ET.Element) -> list[int]:
    widths = []
    for row in table.iter("tr"):
        width = 0
        for cell in row:
            if cell.tag not in ("td", "th"):
                continue
            width += int(cell.get("colspan", "1"))
        widths.append(width)
    return widths


def main() -> None:
    path = Path(sys.argv[1])
    entries = json.loads(path.read_text())
    problems: list[str] = []

    for entry in entries:
        key = entry.get("key", "?")
        html = entry.get("html", "")
        if not html.strip():
            problems.append(f"{key}: no markup")
            continue
        try:
            root = ET.fromstring(WRAPPER.format(html))
        except ET.ParseError as error:
            problems.append(f"{key}: not well-formed XML: {error}")
            continue
        tables = list(root.iter("table"))
        if not tables:
            problems.append(f"{key}: no <table> element")
            continue
        for index, table in enumerate(tables):
            widths = row_widths(table)
            if not widths:
                problems.append(f"{key}: table {index + 1} has no rows")
                continue
            if len(set(widths)) > 1:
                problems.append(
                    f"{key}: table {index + 1} rows have different widths {sorted(set(widths))}; "
                    "add the missing cells or use colspan")

    if problems:
        print(f"{len(problems)} problems:")
        for problem in problems:
            print(f"  {problem}")
        sys.exit(1)
    print(f"OK: {len(entries)} tables parse and are rectangular")


if __name__ == "__main__":
    main()
