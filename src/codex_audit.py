"""Independent audit of the transcribed mathematics, using a different model family.

    uv run python src/codex_audit.py             # the reproducible sample of 50
    uv run python src/codex_audit.py all         # every comparison image
    uv run python src/codex_audit.py all --workers 8 --fresh

Everything else in this pipeline is Claude reading Claude's work, so the accuracy figure it
produces is not independent. This script hands the same evidence to OpenAI's `codex` command
line tool: the comparison image, with the page's own typesetting above and the typeset
candidate below, and asks a single question - do these two say the same thing?

A sample is spread evenly across the book rather than drawn at random, so the result is
reproducible and covers every chapter. `all` audits the whole population instead; one answer
takes about 9 seconds, so 531 of them take about 10 minutes at 8 workers.

Answers are cached in work/codex_audit_cache.json under the identifier and the SHA-256 of the
comparison image. A re-run therefore costs nothing for an image that has not changed, and
re-asks by itself for one that has. `--fresh` ignores the cache.

Outputs:
  work/codex_audit.json         the report apply_verdicts.py reads
  work/codex_audit_cache.json   one answer per image digest
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
COMPARE = WORK / "math_compare"
CACHE_PATH = WORK / "codex_audit_cache.json"

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

_print_lock = threading.Lock()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ask(ident: str, timeout: int = 300) -> dict:
    image = COMPARE / f"{ident}.png"
    if not image.exists():
        return {"id": ident, "status": "no-image"}
    try:
        finished = subprocess.run(
            ["codex", "exec", "--skip-git-repo-check", "-s", "read-only", "-i", str(image), "--", PROMPT],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=ROOT,
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
    return {"id": ident, "status": "ok", "match": bool(payload.get("match")), "issue": payload.get("issue", "")}


def load_cache(use_cache: bool) -> dict[str, dict]:
    if not use_cache or not CACHE_PATH.exists():
        return {}
    return json.loads(CACHE_PATH.read_text())


def run(sample: list[str], cache: dict[str, dict], workers: int) -> list[dict]:
    """Answer every identifier in `sample`, taking from the cache what it already holds."""
    done: dict[str, dict] = {}
    pending: list[str] = []
    for ident in sample:
        image = COMPARE / f"{ident}.png"
        cached = cache.get(digest(image)) if image.exists() else None
        if cached and cached.get("status") == "ok":
            done[ident] = {"id": ident, **{k: v for k, v in cached.items() if k != "id"}}
        else:
            pending.append(ident)

    if done:
        print(f"{len(done)} answers reused from the cache, {len(pending)} to ask", flush=True)

    counter = {"n": 0}

    def answer(ident: str) -> dict:
        result = ask(ident)
        with _print_lock:
            counter["n"] += 1
            if counter["n"] % 25 == 0 or counter["n"] == len(pending):
                print(f"  {counter['n']}/{len(pending)} asked", flush=True)
        return result

    if pending:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for result in pool.map(answer, pending):
                done[result["id"]] = result

    return [done[ident] for ident in sample]


def retry(results: list[dict], cache: dict[str, dict], workers: int) -> list[dict]:
    """Ask once more for anything that timed out or came back unreadable."""
    stuck = [entry["id"] for entry in results if entry["status"] in ("timeout", "unparsed")]
    if not stuck:
        return results
    print(f"re-asking {len(stuck)} that timed out or came back unreadable", flush=True)
    second = {entry["id"]: entry for entry in run(stuck, cache, workers)}
    return [second.get(entry["id"], entry) for entry in results]


def save_cache(cache: dict[str, dict], results: list[dict]) -> None:
    for entry in results:
        if entry["status"] != "ok":
            continue
        image = COMPARE / f"{entry['id']}.png"
        if image.exists():
            cache[digest(image)] = entry
    CACHE_PATH.write_text(json.dumps(cache, indent=1, ensure_ascii=False))


def main() -> None:
    arguments = sys.argv[1:]
    use_cache = "--fresh" not in arguments
    arguments = [a for a in arguments if a != "--fresh"]
    workers = 4
    if "--workers" in arguments:
        index = arguments.index("--workers")
        workers = int(arguments[index + 1])
        del arguments[index : index + 2]

    candidates = sorted(path.stem for path in COMPARE.glob("*.png"))
    if not candidates:
        raise SystemExit("no comparison images; run render_candidates.py first")

    request = arguments[0] if arguments else "50"
    if request in ("all", "full"):
        sample = candidates
        mode = "full"
    else:
        size = int(request)
        step = max(1, len(candidates) // size)
        sample = candidates[::step][:size]
        mode = "sample"

    print(f"auditing {len(sample)} of {len(candidates)} expressions with codex", flush=True)

    cache = load_cache(use_cache)
    results = retry(run(sample, cache, workers), cache, workers)
    save_cache(cache, results)

    answered = [r for r in results if r["status"] == "ok"]
    agreed = [r for r in answered if r["match"]]
    report = {
        "mode": mode,
        "population": len(candidates),
        "sampled": len(sample),
        "answered": len(answered),
        "agreed": len(agreed),
        "agreement": (len(agreed) / len(answered) * 100) if answered else 0.0,
        "disagreements": [r for r in answered if not r["match"]],
        "problems": [r for r in results if r["status"] != "ok"],
    }
    (WORK / "codex_audit.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"answered {len(answered)}, agreed {len(agreed)} ({report['agreement']:.1f}%)")
    for entry in report["disagreements"][:15]:
        print(f"  {entry['id']}: {entry['issue']}")


if __name__ == "__main__":
    main()
