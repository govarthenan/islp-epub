"""Carry transcriptions across a re-extraction, and list what still needs reading.

    uv run python src/reuse_transcription.py

Identifiers change whenever the extraction changes, but most crops come out byte for byte
identical. Matching on the image content rather than the identifier means only genuinely new
or changed expressions have to be read again.

Outputs:
  work/math_transcription.json   carried-over entries, keyed by the new identifiers
  work/math_batches/            fresh batches holding only what is still unread
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
CROPS = WORK / "math_crops"
PREVIOUS_CROPS = WORK / "math_crops_prev"
BATCHES = WORK / "math_batches"
BATCH_SIZE = 25


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    jobs = json.loads((WORK / "math_jobs_vlm.json").read_text())

    previous: dict[str, dict] = {}
    transcription_path = WORK / "math_transcription.json"
    if transcription_path.exists():
        previous = json.loads(transcription_path.read_text())
    else:
        parts = WORK / "math_transcription_parts"
        for part in sorted(parts.glob("*.json")):
            entries = json.loads(part.read_text())
            if isinstance(entries, dict):
                entries = [{"id": k, **v} for k, v in entries.items()]
            for entry in entries:
                if entry.get("id") and entry.get("latex"):
                    previous[entry["id"]] = {"latex": entry["latex"].strip(),
                                             "confidence": entry.get("confidence", 1.0),
                                             "notes": entry.get("notes", "")}

    by_hash: dict[str, dict] = {}
    if PREVIOUS_CROPS.exists():
        for path in PREVIOUS_CROPS.glob("*.png"):
            entry = previous.get(path.stem)
            if entry:
                by_hash[digest(path)] = entry

    carried: dict[str, dict] = {}
    remaining = []
    for job in jobs:
        crop = ROOT / job["image"]
        entry = by_hash.get(digest(crop)) if crop.exists() else None
        if entry:
            carried[job["id"]] = dict(entry)
        else:
            remaining.append(job)

    transcription_path.write_text(json.dumps(carried, indent=1, ensure_ascii=False))

    if BATCHES.exists():
        shutil.rmtree(BATCHES)
    BATCHES.mkdir(parents=True)
    remaining.sort(key=lambda job: (job["page_pdf"], job["id"]))
    for start in range(0, len(remaining), BATCH_SIZE):
        chunk = remaining[start:start + BATCH_SIZE]
        (BATCHES / f"batch_{start // BATCH_SIZE:03d}.json").write_text(
            json.dumps(chunk, indent=1, ensure_ascii=False))

    print(f"expressions now : {len(jobs)}")
    print(f"carried over    : {len(carried)}")
    print(f"still to read   : {len(remaining)} in "
          f"{len(list(BATCHES.glob('*.json')))} batches")


if __name__ == "__main__":
    main()
