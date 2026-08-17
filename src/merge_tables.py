"""Merge the per-batch table markup into one file the build can read.

    uv run python src/merge_tables.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"


def main() -> None:
    jobs = {job["key"] for job in json.loads((WORK / "table_jobs.json").read_text())}
    merged: dict[str, str] = {}
    for part in sorted((WORK / "table_parts").glob("*.json")):
        for entry in json.loads(part.read_text()):
            if entry.get("key") and entry.get("html", "").strip():
                merged[entry["key"]] = entry["html"].strip()
    (WORK / "tables_html.json").write_text(json.dumps(merged, indent=1, ensure_ascii=False))
    print(f"tables as HTML : {len(merged)} / {len(jobs)}")
    missing = sorted(jobs - set(merged))
    if missing:
        print("still images   :", ", ".join(missing))


if __name__ == "__main__":
    main()
