"""Merge the per-batch transcription files into one, and report what is missing.

    uv run python src/merge_transcription.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
PARTS = WORK / "math_transcription_parts"


def main() -> None:
    jobs = json.loads((WORK / "math_jobs_vlm.json").read_text())
    wanted = {job["id"] for job in jobs}

    # Start from anything carried over from an earlier extraction, then overlay the new parts.
    merged: dict[str, dict] = {}
    existing = WORK / "math_transcription.json"
    if existing.exists():
        merged.update(json.loads(existing.read_text()))
    for part in sorted(PARTS.glob("*.json")):
        entries = json.loads(part.read_text())
        if isinstance(entries, dict):
            entries = [{"id": k, **v} for k, v in entries.items()]
        for entry in entries:
            if entry.get("id") and entry.get("latex"):
                merged[entry["id"]] = {
                    "latex": entry["latex"].strip(),
                    "confidence": entry.get("confidence", 1.0),
                    "notes": entry.get("notes", ""),
                }

    missing = sorted(wanted - set(merged))
    (WORK / "math_transcription.json").write_text(json.dumps(merged, indent=1, ensure_ascii=False))
    (WORK / "math_missing.json").write_text(json.dumps(missing, indent=1))

    low = [ident for ident, entry in merged.items() if entry.get("confidence", 1) < 0.7]
    print(f"transcribed : {len(merged)} / {len(wanted)}")
    print(f"missing     : {len(missing)}")
    print(f"low conf    : {len(low)}")
    if missing[:15]:
        print("  first missing:", ", ".join(missing[:15]))


if __name__ == "__main__":
    main()
