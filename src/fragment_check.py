"""Find transcriptions that are a fragment of an expression rather than an expression.

    uv run python src/fragment_check.py

A crop cut from an inline expression keeps only what rises above or falls below the text line:
the stretched delimiter and the operator's limits. The transcription then faithfully writes
down that fragment, so every check that compares the transcription against the crop passes it.
The picture is the problem, not the reading, which is why neither the adversarial verification
nor the independent audit can be relied on to find this class. This check does not look at any
picture. It asks of the LaTeX alone: is this a whole expression?

Two faults are deterministic enough to name:
  * a big operator with nothing to operate on - `\\int` alone, or `\\sum^{p}`;
  * delimiters that do not balance - `(x_1^{*}` or `)^{T}`.

Outputs work/fragment_check.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"

BIG_OPERATOR = re.compile(r"\\(sum|prod|int|iint|iiint|oint|bigcup|bigcap|coprod)\b")
# A limit is a `_` or `^` carrying either a braced group or one token.
LIMIT = re.compile(r"^(?:[_^](?:\{[^{}]*\}|\\[A-Za-z]+|.))+")
# What may follow an operator and still leave it with nothing to work on.
EMPTY_TAIL = re.compile(r"^(?:\s|\\right|\\[,;:!]|[)\]}.,]|\\\})*$")


def has_operand(latex: str, start: int) -> bool:
    """True if something follows the big operator at `start` other than its limits."""
    rest = latex[start:]
    rest = BIG_OPERATOR.match(rest).group(0) and rest[BIG_OPERATOR.match(rest).end() :]
    while True:
        limit = LIMIT.match(rest)
        if not limit:
            break
        rest = rest[limit.end() :]
    return not EMPTY_TAIL.match(rest)


def unbalanced(latex: str) -> str:
    braces = latex.count("{") - latex.count("}")
    if braces:
        return f"{abs(braces)} unclosed brace" if braces > 0 else f"{abs(braces)} extra brace"
    # An escaped brace is not a group, `\leftarrow` is not a `\left`, and a bracket set in
    # prose - "(among a set of n items.)" - is punctuation, not a delimiter.
    stripped = re.sub(r"\\[{}]", "", latex)
    stripped = re.sub(r"\\(?:text|textrm|texttt|textit|mbox)\{[^{}]*\}", "", stripped)
    openers = len(re.findall(r"\\left(?![a-zA-Z])", stripped))
    closers = len(re.findall(r"\\right(?![a-zA-Z])", stripped))
    if openers != closers:
        return f"{abs(openers - closers)} unmatched \\left"
    difference = stripped.count("(") - stripped.count(")")
    if difference:
        return f"{abs(difference)} unmatched parenthesis"
    return ""


def inspect(ident: str, latex: str) -> dict | None:
    for match in BIG_OPERATOR.finditer(latex):
        if not has_operand(latex, match.start()):
            return {"id": ident, "latex": latex, "fault": f"\\{match.group(1)} with nothing to sum over"}
    fault = unbalanced(latex)
    if fault:
        return {"id": ident, "latex": latex, "fault": fault}
    return None


def main() -> None:
    source = WORK / "math_final.json"
    if not source.exists():
        source = WORK / "math_transcription.json"
    entries = json.loads(source.read_text())
    jobs = {job["id"]: job for job in json.loads((WORK / "math_jobs_vlm.json").read_text())}

    fragments = []
    for ident, entry in entries.items():
        found = inspect(ident, entry.get("latex", "").strip())
        if found:
            found["page_pdf"] = jobs.get(ident, {}).get("page_pdf")
            found["kind"] = jobs.get(ident, {}).get("kind")
            fragments.append(found)

    report = {
        "source": source.name,
        "expressions": len(entries),
        "fragments": len(fragments),
        "share": round(len(fragments) / len(entries) * 100, 1) if entries else 0.0,
        "detail": fragments,
    }
    (WORK / "fragment_check.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"{len(fragments)} of {len(entries)} transcriptions are a fragment, not an expression")
    for entry in fragments:
        print(f"  {entry['id']} p{entry['page_pdf']} {entry['kind']:<8} {entry['fault']:<34} {entry['latex'][:44]}")


if __name__ == "__main__":
    main()
