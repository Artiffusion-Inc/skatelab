#!/usr/bin/env python3
"""Sync references.bib entries to a NotebookLM notebook as URL sources.

Usage:
    uv run python scripts/sync_notebooklm.py [--notebook-id <id>]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

BIB_PATH = Path("docs/references.bib")
DEFAULT_NOTEBOOK_ID = "37bd7274-18f6-46c6-917f-0172c3b7c2f7"


def _run_nlm_json(args: list[str]) -> dict[str, Any] | list[Any] | None:
    """Run nlm CLI and parse JSON output."""
    cmd = ["nlm", *args, "--debug"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.stdout.strip():
            try:
                return json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                return None
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _run_nlm(args: list[str], timeout: int = 600) -> bool:
    """Run nlm CLI and return True on success."""
    try:
        subprocess.run(
            ["nlm", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
        return False


def parse_bibtex(path: Path) -> list[dict[str, str]]:
    """Parse simple BibTeX entries into dicts."""
    text = path.read_text(encoding="utf-8")
    # Split by @article{...} blocks
    entries = re.findall(r"@\w+\{(.*?),\s*(.*?)\n\}", text, re.DOTALL)
    results: list[dict[str, str]] = []
    for _citekey, body in entries:
        fields: dict[str, str] = {}
        # Match field = {value}, (value may contain nested braces)
        for match in re.finditer(r"(\w+)\s*=\s*\{(.*?)\},?\s*$", body, re.MULTILINE):
            key, val = match.group(1).lower(), match.group(2)
            fields[key] = val
        results.append(fields)
    return results


def get_existing_urls(notebook_id: str) -> set[str]:
    """Fetch existing source URLs from a notebook."""
    data = _run_nlm_json(["source", "list", notebook_id])
    urls: set[str] = set()
    if isinstance(data, list):
        for src in data:
            url = src.get("url")
            if url:
                urls.add(url)
    return urls


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync references.bib to NotebookLM")
    parser.add_argument(
        "--notebook-id",
        default=DEFAULT_NOTEBOOK_ID,
        help="NotebookLM notebook ID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be added without adding",
    )
    args = parser.parse_args()

    if not BIB_PATH.exists():
        print(f"Bib file not found: {BIB_PATH}", file=sys.stderr)
        return 1

    entries = parse_bibtex(BIB_PATH)
    if not entries:
        print("No entries found in references.bib")
        return 0

    existing = get_existing_urls(args.notebook_id)
    print(f"Existing sources in notebook: {len(existing)}")

    added = 0
    skipped = 0

    for fields in entries:
        arxiv_id = fields.get("eprint", "").strip()
        doi = fields.get("doi", "").strip()
        title = fields.get("title", "").strip()

        url: str | None = None
        if arxiv_id:
            url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        elif doi:
            url = f"https://doi.org/{doi}"

        if not url:
            print(f"Skipping '{title}': no URL")
            skipped += 1
            continue

        if url in existing:
            print(f"Skipping '{title}': already exists")
            skipped += 1
            continue

        if args.dry_run:
            print(f"Would add: {title} -> {url}")
            added += 1
            continue

        print(f"Adding: {title} -> {url}")
        result = _run_nlm(
            [
                "source",
                "add",
                args.notebook_id,
                "--url",
                url,
                "--title",
                title,
                "--wait",
            ]
        )
        if result is not None:
            print("  Added successfully")
            added += 1
            existing.add(url)
        else:
            print("  Failed to add", file=sys.stderr)
            skipped += 1

    print(f"\nDone: {added} added, {skipped} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
