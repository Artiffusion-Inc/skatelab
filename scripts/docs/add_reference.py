#!/usr/bin/env python3
"""Add a reference to docs/references.bib from DOI, arXiv ID, or title.

Usage:
    uv run python scripts/add_reference.py --doi "10.48550/arXiv.2504.19514"
    uv run python scripts/add_reference.py --arxiv "2504.19514"
    uv run python scripts/add_reference.py --title "Pose3DM bidirectional mamba"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BIB_PATH = Path("docs/references.bib")


def _fetch_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def _make_citekey(title: str, first_author: str, year: str) -> str:
    """Generate a human-readable citekey: authorYearFirstWord."""
    author_part = re.sub(
        r"[^a-zA-Z]", "", first_author.rsplit(maxsplit=1)[-1] if first_author else "unknown"
    ).lower()[:12]
    year_part = year if year else "nd"
    title_words = re.findall(r"[a-zA-Z]+", title.lower())
    title_part = "".join(title_words[:3])[:15]
    return f"{author_part}{year_part}{title_part}"


def fetch_crossref(doi: str) -> dict[str, Any] | None:
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
    data = _fetch_json(url, {"User-Agent": "Mozilla/5.0 (Research Sync)"})
    return data.get("message") if data else None


def fetch_arxiv(arxiv_id: str) -> dict[str, Any] | None:
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            xml = resp.read().decode()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None

    # Parse only the first <entry> block (the paper), skip feed-level title
    entry_match = re.search(r"<entry>(.*?)</entry>", xml, re.DOTALL)
    if not entry_match:
        return None
    entry_xml = entry_match.group(1)

    title_match = re.search(r"<title>([^<]+)</title>", entry_xml)
    author_matches = re.findall(
        r"<author>.*?<name>([^<]+)</name>.*?</author>", entry_xml, re.DOTALL
    )
    published_match = re.search(r"<published>(\d{4})", entry_xml)
    summary_match = re.search(r"<summary>([^<]+)</summary>", entry_xml, re.DOTALL)

    if not title_match:
        return None

    return {
        "title": title_match.group(1).strip().replace("\n", " "),
        "authors": author_matches[:5],
        "year": published_match.group(1) if published_match else "",
        "abstract": summary_match.group(1).strip() if summary_match else "",
        "arxiv_id": arxiv_id,
    }


def fetch_semantic_scholar(query: str) -> dict[str, Any] | None:
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={urllib.parse.quote(query)}&fields=title,authors,year,venue,externalIds&limit=1"
    data = _fetch_json(url)
    if not data or not data.get("data"):
        return None
    paper = data["data"][0]
    return {
        "title": paper.get("title", ""),
        "authors": [a.get("name", "") for a in paper.get("authors", [])[:5]],
        "year": str(paper.get("year", "")),
        "venue": paper.get("venue", ""),
        "doi": paper.get("externalIds", {}).get("DOI", ""),
        "arxiv_id": paper.get("externalIds", {}).get("ArXiv", ""),
    }


def to_bibtex(meta: dict[str, Any]) -> str:
    """Generate a BibTeX entry from metadata dict."""
    title = meta.get("title", "").replace("{", "{{").replace("}", "}}")
    authors = meta.get("authors", [])
    author_str = " and ".join(authors) if authors else "Unknown"
    year = meta.get("year", "")
    venue = meta.get("venue", "")
    doi = meta.get("doi", "")
    arxiv_id = meta.get("arxiv_id", "")
    citekey = _make_citekey(title, authors[0] if authors else "", year)

    lines = [f"@article{{{citekey},"]
    lines.append(f"  title = {{{title}}},")
    lines.append(f"  author = {{{author_str}}},")
    if year:
        lines.append(f"  year = {{{year}}},")
    if venue:
        lines.append(f"  journal = {{{venue}}},")
    if doi:
        lines.append(f"  doi = {{{doi}}},")
    if arxiv_id:
        lines.append(f"  eprint = {{{arxiv_id}}},")
        lines.append("  archiveprefix = {arXiv},")
    lines.append("}")
    return "\n".join(lines)


def add_to_bib(bibtex: str) -> bool:
    """Append BibTeX entry to docs/references.bib if not duplicate."""
    # Extract citekey
    match = re.search(r"@\w+\{(\w+),", bibtex)
    if not match:
        return False
    citekey = match.group(1)

    BIB_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = BIB_PATH.read_text(encoding="utf-8") if BIB_PATH.exists() else ""

    if citekey in existing:
        print(f"Citekey '{citekey}' already exists in {BIB_PATH}")
        return False

    with BIB_PATH.open("a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n\n"):
            f.write("\n\n")
        f.write(bibtex)
        f.write("\n")

    print(f"Added {citekey} to {BIB_PATH}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Add a reference to docs/references.bib")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--doi", help="DOI of the paper")
    group.add_argument("--arxiv", help="arXiv ID (e.g. 2504.19514)")
    group.add_argument("--title", help="Paper title (searches Semantic Scholar)")
    args = parser.parse_args()

    meta: dict[str, Any] | None = None

    if args.doi:
        print(f"Fetching DOI: {args.doi}...")
        cr = fetch_crossref(args.doi)
        if cr:
            authors = []
            for a in cr.get("author", []):
                name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                if name:
                    authors.append(name)
            year = ""
            pub = cr.get("published-print") or cr.get("published-online") or {}
            parts = pub.get("date-parts", [[""]])[0]
            if parts:
                year = str(parts[0])
            meta = {
                "title": cr.get("title", [""])[0],
                "authors": authors,
                "year": year,
                "venue": cr.get("container-title", [""])[0] if cr.get("container-title") else "",
                "doi": args.doi,
            }
        else:
            print("Crossref lookup failed.", file=sys.stderr)
            return 1

    elif args.arxiv:
        print(f"Fetching arXiv: {args.arxiv}...")
        meta = fetch_arxiv(args.arxiv)
        if not meta:
            print("arXiv lookup failed.", file=sys.stderr)
            return 1

    elif args.title:
        print(f"Searching: {args.title}...")
        meta = fetch_semantic_scholar(args.title)
        if not meta:
            print("Semantic Scholar search failed.", file=sys.stderr)
            return 1

    if not meta:
        print("No metadata found.", file=sys.stderr)
        return 1

    bib = to_bibtex(meta)
    print("\nGenerated BibTeX:")
    print(bib)
    print()

    add_to_bib(bib)
    return 0


if __name__ == "__main__":
    sys.exit(main())
