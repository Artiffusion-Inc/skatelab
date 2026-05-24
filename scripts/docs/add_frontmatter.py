#!/usr/bin/env python3
"""Add YAML frontmatter to all docs/**/*.md files that lack it.

Usage:
    uv run python scripts/add_frontmatter.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DOCS_ROOT = Path("docs")
FRONTMATTER_RE = re.compile(r"^---\s*\n")

# Map citekeys to filenames that reference them
CITEKEY_MAP: dict[str, list[str]] = {
    "leuthold2025physicsinformed": [
        "PHYSICS_DETECTION_RESEARCH.md",
        "RESEARCH_SUMMARY_2026-03-28.md",
    ],
    "tanaka2025vifssviewinvari": [
        "RESEARCH_VIFSS_2026-04-12.md",
    ],
    "gao2025fsbenchafigure": [
        "RESEARCH_SUMMARY_2026-03-28.md",
    ],
    "chen2024yourskatingcoac": [
        "RESEARCH_SUMMARY_2026-03-28.md",
    ],
}


def extract_title(text: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else "Untitled"


def extract_date_from_filename(path: Path) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    return m.group(1) if m else ""


def extract_date_from_header(text: str) -> str:
    m = re.search(r"\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})", text)
    return m.group(1) if m else ""


def guess_status(path: Path) -> str:
    name = path.name.lower()
    if "plan" in name or path.parent.name == "plans":
        return "planned"
    if "design" in name or path.parent.name == "specs":
        return "draft"
    if "research" in name.lower():
        return "active"
    return ""


def process_file(path: Path, dry_run: bool) -> bool:
    text = path.read_text(encoding="utf-8")

    # Skip if already has frontmatter
    if FRONTMATTER_RE.match(text):
        return False

    title = extract_title(text)
    date = extract_date_from_filename(path) or extract_date_from_header(text)
    status = guess_status(path)

    # Find citekey
    citekey = ""
    for ck, files in CITEKEY_MAP.items():
        if path.name in files:
            citekey = ck
            break

    fm_lines = ["---"]
    fm_lines.append(f'title: "{title}"')
    if date:
        fm_lines.append(f'date: "{date}"')
    if status:
        fm_lines.append(f"status: {status}")
    if citekey:
        fm_lines.append(f'citekey: "{citekey}"')
    fm_lines.append("---")
    fm_lines.append("")

    new_text = "\n".join(fm_lines) + text

    if dry_run:
        print(f"Would update: {path}")
        return True

    path.write_text(new_text, encoding="utf-8")
    print(f"Updated: {path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Add frontmatter to docs/**/*.md")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    updated = 0
    skipped = 0

    for subdir in ["research", "specs", "plans"]:
        for path in sorted((DOCS_ROOT / subdir).rglob("*.md")):
            if process_file(path, args.dry_run):
                updated += 1
            else:
                skipped += 1

    print(f"\nDone: {updated} updated, {skipped} already have frontmatter")
    return 0


if __name__ == "__main__":
    sys.exit(main())
