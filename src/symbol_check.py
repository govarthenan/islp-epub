"""A free, deterministic cross-check of every transcription.

    uv run python src/symbol_check.py

The PDF's text layer loses the structure of an expression but not its symbols. So the symbols
the transcription claims can be compared against the symbols the page actually contains,
without asking any model. It cannot tell a correct fraction from an inverted one, but it
catches a dropped term, a missed subscript letter and an invented symbol, and it costs
nothing.

Outputs work/symbol_check.json.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"

COMMAND_SYMBOL = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ϵ",
    "varepsilon": "ϵ", "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι",
    "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π",
    "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "chi": "χ",
    "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ",
    "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ",
    "Omega": "Ω", "ell": "ℓ", "partial": "∂", "infty": "∞",
}

# Commands that carry no symbol of their own.
STRUCTURAL = re.compile(
    r"\\(?:frac|sqrt|hat|bar|tilde|widehat|overline|left|right|begin|end|text|mathrm|mathbf"
    r"|mathbb|mathcal|mathsf|mathtt|operatorname|quad|qquad|,|;|:|!|displaystyle|limits"
    r"|nolimits|big|Big|bigg|Bigg|langle|rangle|lvert|rvert|lVert|rVert)\b\*?"
)

DROP_CHARS = "".join(chr(code) for code in range(0xF8E0, 0xF900)) + "�"


def symbols_from_pdf(text: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for char in text:
        if char in DROP_CHARS or char.isspace():
            continue
        if char.isalnum() or unicodedata.category(char).startswith("L"):
            counter[normalise(char)] += 1
    return counter


def symbols_from_latex(latex: str) -> Counter[str]:
    text = STRUCTURAL.sub(" ", latex)

    def expand(match: re.Match) -> str:
        return COMMAND_SYMBOL.get(match.group(1), " ")

    text = re.sub(r"\\([A-Za-z]+)", expand, text)
    counter: Counter[str] = Counter()
    for char in text:
        if char.isspace() or char in "{}[]()_^\\&$%#~":
            continue
        if char.isalnum() or unicodedata.category(char).startswith("L"):
            counter[normalise(char)] += 1
    return counter


def normalise(char: str) -> str:
    return {"µ": "μ", "ε": "ϵ"}.get(char, char)


def main() -> None:
    jobs = {job["id"]: job for job in json.loads((WORK / "math_jobs_vlm.json").read_text())}
    transcription = json.loads((WORK / "math_transcription.json").read_text())

    report = []
    for ident, entry in transcription.items():
        job = jobs.get(ident)
        if not job:
            continue
        page_symbols = symbols_from_pdf(job.get("extracted_characters", ""))
        latex_symbols = symbols_from_latex(entry["latex"])
        missing = page_symbols - latex_symbols
        invented = latex_symbols - page_symbols
        total = sum(page_symbols.values())
        agreement = 1.0 - (sum(missing.values()) / total) if total else 1.0
        report.append({
            "id": ident,
            "page_pdf": job["page_pdf"],
            "symbols_on_page": total,
            "missing": dict(missing),
            "invented": dict(invented),
            "agreement": round(agreement, 3),
        })

    report.sort(key=lambda entry: entry["agreement"])
    scored = [entry for entry in report if entry["symbols_on_page"] >= 3]
    perfect = [entry for entry in scored if not entry["missing"]]
    weak = [entry for entry in scored if entry["agreement"] < 0.8]

    summary = {
        "checked": len(report),
        "scored": len(scored),
        "no_symbol_lost": len(perfect),
        "share_no_symbol_lost": round(len(perfect) / len(scored) * 100, 1) if scored else 0.0,
        "mean_agreement": round(sum(e["agreement"] for e in scored) / len(scored), 3)
        if scored else 0.0,
        "weakest": report[:40],
        "weak_ids": [entry["id"] for entry in weak],
    }
    (WORK / "symbol_check.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    print(f"checked {summary['checked']} transcriptions "
          f"({summary['scored']} with enough symbols to score)")
    print(f"no symbol lost   : {summary['no_symbol_lost']} "
          f"({summary['share_no_symbol_lost']}%)")
    print(f"mean agreement   : {summary['mean_agreement']}")
    print(f"below 0.80       : {len(weak)}")


if __name__ == "__main__":
    main()
