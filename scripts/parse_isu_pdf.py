"""Parse ISU Communication PDFs into structured JSON.

Usage:
    python scripts/parse_isu_pdf.py --comm 2707 --season 2025-26 --input ISU_Comm_2707.pdf
    python scripts/parse_isu_pdf.py --comm 2701 --season 2025-26 --input ISU_Comm_2701.pdf --type goe
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# SOV row: code + base_value + modifier columns (q, <, <<, e, !)
_SOV_ROW_RE = re.compile(
    r"(\d[A-Z][a-z]?)\s+"
    r"(\d+\.\d+)\s+"  # clean BV
    r"(\d+\.\d+)\s+"  # q
    r"(\d+\.\d+)\s+"  # <
    r"(\d+\.\d+|-)\s+"  # <<
    r"(\d+\.\d+|-)\s*"  # e
    r"(\d+\.\d+|-)?"  # !
)


def parse_sov_pdf(sample_sov_text: str = "", pdf_path: str = "") -> dict:
    """Parse SOV table from ISU PDF text or sample text."""
    text = sample_sov_text
    if pdf_path and Path(pdf_path).exists():
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open(pdf_path)
        text = "\n".join(page.get_text() for page in doc)

    entries: dict[str, dict] = {}
    for m in _SOV_ROW_RE.finditer(text):
        code = m.group(1).strip()
        bv = float(m.group(2))
        q_val = float(m.group(3))
        lt_val = float(m.group(4))
        ltlt_val = None if m.group(5).strip() == "-" else float(m.group(5))
        e_val = None if m.group(6).strip() == "-" else float(m.group(6))
        bang_val = None if m.group(7).strip() == "-" else float(m.group(7)) if m.group(7) else None

        entries[code] = {
            "base_value": bv,
            "modifiers": {"q": q_val, "<": lt_val, "<<": ltlt_val, "e": e_val, "!": bang_val},
        }
    return entries


def parse_goe_pdf(sample_text: str = "", pdf_path: str = "") -> list[dict]:
    """Parse GOE positive bullets from ISU PDF text."""
    text = sample_text
    if pdf_path and Path(pdf_path).exists():
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open(pdf_path)
        text = "\n".join(page.get_text() for page in doc)

    bullets: list[dict] = []
    bullet_re = re.compile(r"(\d)\s+(.+?)(?:\s{2,}|$)", re.MULTILINE)
    for m in bullet_re.finditer(text):
        num = int(m.group(1))
        text_en = m.group(2).strip()
        if 1 <= num <= 6:
            bullets.append({"number": num, "text_en": text_en})
    return bullets


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse ISU Communication PDFs")
    parser.add_argument("--comm", required=True, help="Communication number")
    parser.add_argument("--season", required=True, help="Season (e.g., 2025-26)")
    parser.add_argument("--input", required=True, help="PDF file path")
    parser.add_argument("--type", default="sov", choices=["sov", "goe", "deductions"])
    args = parser.parse_args()

    season_key = args.season.replace("/", "_")
    out_dir = Path("data/isu")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.type == "sov":
        entries = parse_sov_pdf(pdf_path=args.input)
        out_file = out_dir / f"sov_{season_key}.json"
        with out_file.open("w") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        sys.stdout.write(f"Wrote {len(entries)} entries to {out_file}\n")

    elif args.type == "goe":
        bullets = parse_goe_pdf(pdf_path=args.input)
        out_file = out_dir / f"goe_rules_{season_key}.json"
        with out_file.open("w") as f:
            json.dump({"positive_bullets": bullets}, f, indent=2, ensure_ascii=False)
        sys.stdout.write(f"Wrote {len(bullets)} bullets to {out_file}\n")


if __name__ == "__main__":
    main()
