#!/usr/bin/env python3
"""Collect the WFIU free-text recurrence corpus from the live listing.

Ticket: B-Square-Bulletin/community-calendar#132

Good-citizen fetch: browser User-Agent, 2.5 s between requests, plain stdlib
HTTP, no cookies, no data mutation. The run that produced the committed corpus
issued 28 listing requests (`?p=1..28`). Output HTML is cached in a temp
directory (default `/tmp/wfiu`); pass `--out DIR` to change it.

Usage:
    python scripts/research/wfiu_fetch_corpus.py --pages 1 28
    python scripts/research/wfiu_fetch_corpus.py --extract /tmp/wfiu

`--extract` re-parses cached listing HTML into the corpus format (it performs
no network I/O), emitting `recurring:` / `one-off:` lines that match
docs/fixtures/wfiu-recurrence-corpus.txt.
"""

from __future__ import annotations

import argparse
import gzip
import re
import time
import urllib.request
from pathlib import Path

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
LISTING = "https://www.ipm.org/community-calendar?p={p}"
TIME_BLOCK = re.compile(
    r'<div class="PromoEvent-time PromoEvent-content-item"([^>]*)>\s*<svg.*?</svg>\s*(.*?)\s*</div>',
    re.S,
)


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        return data.decode("utf-8", "replace")


def norm(raw: str) -> str:
    raw = re.sub(r"<br\s*/?>", " || ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def collect(out: Path, start: int, end: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for p in range(start, end + 1):
        path = out / f"list{p}.html"
        if path.exists():
            print(f"cached list{p}")
            continue
        body = fetch(LISTING.format(p=p))
        path.write_text(body, encoding="utf-8")
        print(f"HTTP 200 list{p} ({len(body)} bytes)")
        time.sleep(2.5)


def extract(out: Path) -> None:
    rec, one = set(), set()
    for f in sorted(out.glob("list*.html")):
        h = f.read_text(encoding="utf-8")
        for m in TIME_BLOCK.finditer(h):
            (rec if "data-recurring" in m.group(1) else one).add(norm(m.group(2)))
    for label, values in (("recurring", rec), ("one-off", one)):
        for v in sorted(values):
            print(f"{label}: {v}")
    print(f"# distinct: {len(rec)} recurring, {len(one)} one-off", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/wfiu")
    ap.add_argument("--pages", nargs=2, type=int, metavar=("START", "END"))
    ap.add_argument("--extract", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    if args.pages:
        collect(out, *args.pages)
    if args.extract:
        extract(out)


if __name__ == "__main__":
    main()
