"""Apply the verification verdicts and produce the final LaTeX.

    uv run python src/apply_verdicts.py

A verdict of "wrong" replaces the candidate with the verifier's correction, but only after the
correction is shown to typeset; a correction MathJax refuses is worse than the original, so it
is refused in turn and recorded.

Outputs:
  work/math_final.json          the LaTeX the EPUB is built from
  work/math_verification.json   the numbers index.html reports
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from check_latex import check

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"


def main() -> None:
    transcription = json.loads((WORK / "math_transcription.json").read_text())
    verdicts: dict[str, dict] = {}
    for part in sorted((WORK / "math_verdicts").glob("*.json")):
        entries = json.loads(part.read_text())
        if isinstance(entries, dict):
            entries = [{"id": k, **v} for k, v in entries.items()]
        for entry in entries:
            if entry.get("id"):
                verdicts[entry["id"]] = entry

    counts: Counter[str] = Counter()
    corrections: list[dict] = []
    rejected: list[dict] = []
    final: dict[str, dict] = {}

    proposed = []
    for ident, entry in transcription.items():
        verdict = verdicts.get(ident)
        counts[verdict["verdict"] if verdict else "unchecked"] += 1
        final[ident] = dict(entry)
        if verdict and verdict.get("verdict") == "wrong" and verdict.get("corrected_latex"):
            proposed.append({"id": ident, "latex": verdict["corrected_latex"].strip(),
                             "issue": verdict.get("issue", "")})

    failures = {failure["id"] for failure in check(proposed)} if proposed else set()
    for entry in proposed:
        if entry["id"] in failures:
            rejected.append(entry)
            continue
        final[entry["id"]]["latex"] = entry["latex"]
        final[entry["id"]]["corrected"] = True
        corrections.append(entry)

    (WORK / "math_final.json").write_text(json.dumps(final, indent=1, ensure_ascii=False))

    checked = sum(counts[key] for key in ("same", "cosmetic", "wrong"))
    agreed = counts["same"] + counts["cosmetic"]
    audit_path = WORK / "codex_audit.json"
    audit = json.loads(audit_path.read_text()) if audit_path.exists() else {}
    symbols_path = WORK / "symbol_check.json"
    symbols = json.loads(symbols_path.read_text()) if symbols_path.exists() else {}

    report = {
        "expressions": len(transcription),
        "checked": checked,
        "verdicts": dict(counts),
        "accuracy": round(agreed / checked * 100, 1) if checked else 0.0,
        "corrections_applied": len(corrections),
        "corrections_refused": len(rejected),
        "correction_examples": corrections[:25],
        "refused_examples": rejected[:10],
        "symbol_check": {
            "scored": symbols.get("scored"),
            "no_symbol_lost_share": symbols.get("share_no_symbol_lost"),
            "mean_agreement": symbols.get("mean_agreement"),
        },
        "independent_audit": {
            "sampled": audit.get("answered"),
            "agreement": round(audit.get("agreement", 0.0), 1),
        } if audit else {},
    }
    (WORK / "math_verification.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))

    print(f"expressions        : {report['expressions']}")
    print(f"checked            : {checked}")
    print(f"verdicts           : {dict(counts)}")
    print(f"agreed with page   : {report['accuracy']}%")
    print(f"corrections applied: {len(corrections)} ({len(rejected)} refused as untypesettable)")


if __name__ == "__main__":
    main()
