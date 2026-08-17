"""Check that a batch of candidate LaTeX actually typesets.

    uv run python src/check_latex.py work/math_transcription_parts/batch_000.json

Reads a JSON array of {"id", "latex"} and reports which entries MathJax refuses. Used by the
transcription agents to catch their own syntax errors before the result is accepted.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check(entries: list[dict]) -> list[dict]:
    jobs = [{"id": entry["id"], "tex": entry.get("latex", ""), "display": True}
            for entry in entries if entry.get("latex")]
    if not jobs:
        return []
    with tempfile.TemporaryDirectory() as scratch:
        scratch_path = Path(scratch)
        jobs_path = scratch_path / "jobs.json"
        manifest_path = scratch_path / "manifest.json"
        jobs_path.write_text(json.dumps(jobs))
        subprocess.run(
            ["node", str(ROOT / "src" / "render_math.cjs"), str(jobs_path),
             str(scratch_path / "svg"), str(manifest_path)],
            check=True, cwd=ROOT, capture_output=True,
        )
        return json.loads(manifest_path.read_text())["failures"]


def main() -> None:
    path = Path(sys.argv[1])
    entries = json.loads(path.read_text())
    if isinstance(entries, dict):
        entries = [{"id": k, **v} for k, v in entries.items()]
    failures = check(entries)
    missing = [entry["id"] for entry in entries if not entry.get("latex")]
    if missing:
        print(f"{len(missing)} entries have no LaTeX: {', '.join(missing[:20])}")
    if not failures:
        print(f"OK: all {len(entries) - len(missing)} expressions typeset cleanly")
        return
    print(f"{len(failures)} of {len(entries)} failed to typeset:")
    for failure in failures:
        print(f"  {failure['id']}: {failure['error']}")
        print(f"      {failure['tex']}")
    sys.exit(1)


if __name__ == "__main__":
    main()
