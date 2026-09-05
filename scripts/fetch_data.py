"""Fetch the Wesnoth Polish .po source files used to build the translation memory.

Downloads the selected gettext textdomains from the Wesnoth GitHub repository at a
PINNED release tag, so the dataset is reproducible and its GPL provenance is exact.

Two ways to use it:

1. Standalone (writes the .po files into data/, ready for ingest.py):
       python scripts/fetch_data.py
       python scripts/fetch_data.py --dest data --ref 1.18.0

2. Wired into a Prefect flow: import iter_po_files() as a task. Example:

       from prefect import flow, task
       from scripts.fetch_data import iter_po_files

       @task
       def fetch_po_sources():
           return list(iter_po_files())   # dicts: textdomain, filename, ref, content

       @flow(name="fetch_po")
       def fetch_po_flow():
           return fetch_po_sources()

       fetch_po_flow()

   (For the actual TM you would parse the .po into segments before loading; this
   fetch step only handles the raw extract. Keep the parse in ingest.py so there
   is a single source of truth.)

Reproducibility note (READ THIS):
The .po files committed in data/ are the FROZEN snapshot the evaluation was run on.
They were taken from Wesnoth *master* at a past commit (verified 2026-09-05: 4 of
the 5 committed files still match current master byte-for-byte, but pl_units has
since drifted, and no stable 1.18.x tag matches - those are older, 708 vs 783
help entries). So this frozen snapshot cannot be re-fetched byte-exactly from a
tag, and master keeps moving.

Consequence, choose one:
  (A) Reproduce the exact evaluation TM: ingest from the COMMITTED data/ .po files
      (do not re-fetch). Point the Prefect flow at the local files. This matches
      the reported metrics exactly. Recommended for the reproducibility story.
  (B) Refresh from upstream: run this fetch at a pinned REF (default a stable
      release tag below). This gives a valid but slightly different TM, so the
      committed snapshot stays the canonical eval dataset. Use for the "living
      pipeline" demonstration, and say so in the README.
REF default is a stable release tag (reproducible run to run). Set REF="master"
to get closest to the committed data (4/5 files match today) at the cost of
reproducibility, since master moves.

License: the fetched data is part of The Battle for Wesnoth, GPL v2+. Keep COPYING.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path
from typing import Iterator

# Pinned upstream version. A stable release tag (reproducible). See the module
# docstring: the committed data/ snapshot came from master and is not byte-exactly
# reproducible from a tag; keep the committed files as the frozen eval dataset.
REPO = "wesnoth/wesnoth"
REF = "1.18.6"

# Map each upstream textdomain to the local filename ingest.py already expects.
TEXTDOMAINS: dict[str, str] = {
    "wesnoth-help": "pl_help.po",
    "wesnoth-httt": "pl_httt.po",
    "wesnoth-manual": "pl_manual.po",
    "wesnoth-tutorial": "pl_tutorial.po",
    "wesnoth-units": "pl_units.po",
}

RAW_URL = "https://raw.githubusercontent.com/{repo}/{ref}/po/{domain}/pl.po"

_TIMEOUT = 60  # seconds per file


def download_po(domain: str, ref: str = REF, repo: str = REPO) -> str:
    """Download one textdomain's Polish .po and return it as text (raises on error)."""
    url = RAW_URL.format(repo=repo, ref=ref, domain=domain)
    req = urllib.request.Request(url, headers={"User-Agent": "fuzzy-rag-translator-fetch"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        if resp.status != 200:
            raise RuntimeError(f"GET {url} returned HTTP {resp.status}")
        return resp.read().decode("utf-8")


def iter_po_files(ref: str = REF, repo: str = REPO) -> Iterator[dict]:
    """Yield one dict per textdomain. Prefect-task friendly.

    Keys: textdomain, filename, ref, content.
    """
    for domain, filename in TEXTDOMAINS.items():
        yield {
            "textdomain": domain,
            "filename": filename,
            "ref": ref,
            "content": download_po(domain, ref=ref, repo=repo),
        }


def fetch_to_dir(dest: str = "data", ref: str = REF, repo: str = REPO) -> list[Path]:
    """Download all textdomains and write them into dest/. Returns the written paths.

    Idempotent: the same ref always writes the same content.
    """
    dest_dir = Path(dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for item in iter_po_files(ref=ref, repo=repo):
        out = dest_dir / item["filename"]
        out.write_text(item["content"], encoding="utf-8")
        written.append(out)
        print(f"  {item['textdomain']:18} -> {out}  ({len(item['content']):,} chars)")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Wesnoth Polish .po files for the TM.")
    parser.add_argument("--dest", default="data", help="Output directory (default: data)")
    parser.add_argument("--ref", default=REF, help=f"Git tag/commit to pin (default: {REF})")
    args = parser.parse_args()

    print(f"Fetching {len(TEXTDOMAINS)} textdomains from {REPO} @ {args.ref}")
    try:
        paths = fetch_to_dir(dest=args.dest, ref=args.ref)
    except Exception as exc:  # network / HTTP errors: report and fail loudly
        print(f"ERROR: fetch failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Done. Wrote {len(paths)} files to {args.dest}/ (ref {args.ref}).")
    print("Reminder: data is GPL v2+ (The Battle for Wesnoth); keep COPYING.")


if __name__ == "__main__":
    main()
