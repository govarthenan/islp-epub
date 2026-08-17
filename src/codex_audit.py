"""Independent audit of the transcribed mathematics, using a different model family.

    uv run python src/codex_audit.py [sample_size]

Everything else in this pipeline is Claude reading Claude's work, so the accuracy figure it
produces is not independent. This script hands the same evidence to OpenAI's `codex` command
line tool: the comparison image, with the page's own typesetting above and the typeset
candidate below, and asks a single question - do these two say the same thing?

The sample is spread evenly across the book rather than drawn at random, so the result is
reproducible and covers every chapter.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
COMPARE = WORK / "math_compare"

PROMPT = """The picture has two halves separated by a horizontal rule.

TOP: an expression cut straight out of a printed statistics textbook.
BOTTOM: the same expression as re-typeset from a LaTeX transcription of it.

Decide whether the BOTTOM says exactly the same mathematics as the TOP. Ignore differences of
font, spacing, size and line breaking. Report a difference only if it changes the mathematics:
a wrong or missing symbol, a wrong subscript or superscript, a missing factor or term, a
numerator and denominator swapped, wrong limits on a sum or product, a lost accent (hat, bar,
tilde), or a lost delimiter.

Answer with one line of JSON and nothing else:
{"match": true or false, "issue": "empty when they match, otherwise the single clearest difference"}
"""

JSON_RE = re.compile(r"\{[^{}]*\"match\"[^{}]*\}")


def ask(ident: str, timeout: int = 300) -> dict:
    image = COMPARE / f"{ident}.png"
    if not image.exists():
        return {"id": ident, "status": "no-image"}
    try:
        finished = subprocess.run(
            ["codex", "exec", "--skip-git-repo-check", "-s", "read-only",
             "-i", str(image), "--", PROMPT],
            capture_output=True, text=True, timeout=timeout, cwd=ROOT,
        )
    except subprocess.TimeoutExpired:
        return {"id": ident, "status": "timeout"}
    match = None
    for candidate in JSON_RE.findall(finished.stdout):
        match = candidate
    if match is None:
        return {"id": ident, "status": "unparsed", "raw": finished.stdout[-400:]}
    try:
        payload = json.loads(match)
    except json.JSONDecodeError:
        return {"id": ident, "status": "unparsed", "raw": match}
    return {"id": ident, "status": "ok", "match": bool(payload.get("match")),
            "issue": payload.get("issue", "")}


def main() -> None:
    sample_size = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    candidates = sorted(path.stem for path in COMPARE.glob("*.png"))
    if not candidates:
        raise SystemExit("no comparison images; run render_candidates.py first")
    step = max(1, len(candidates) // sample_size)
    sample = candidates[::step][:sample_size]
    print(f"auditing {len(sample)} of {len(candidates)} expressions with codex", flush=True)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(ask, sample))

    answered = [r for r in results if r["status"] == "ok"]
    agreed = [r for r in answered if r["match"]]
    report = {
        "sampled": len(sample),
        "answered": len(answered),
        "agreed": len(agreed),
        "agreement": (len(agreed) / len(answered) * 100) if answered else 0.0,
        "disagreements": [r for r in answered if not r["match"]],
        "problems": [r for r in results if r["status"] != "ok"],
    }
    (WORK / "codex_audit.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"answered {len(answered)}, agreed {len(agreed)} "
          f"({report['agreement']:.1f}%)")
    for entry in report["disagreements"][:15]:
        print(f"  {entry['id']}: {entry['issue']}")


if __name__ == "__main__":
    main()
