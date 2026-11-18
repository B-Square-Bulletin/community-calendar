#!/usr/bin/env python3
"""One source-outcome rule: what did a source's output bytes turn out to be?

Every consumer that asks "did this source run?" (the download and scraper
runners, ``local_build``, ``report``) classifies output here rather than
re-sniffing the bytes itself. The module reports document facts; each consumer
keeps its own published label.

A build run writes one manifest per city next to its calendars, listing the
``source_id`` stem of every source whose ingestion succeeded (issue #233).
The loader sweeps only those sources, so a quiet source is cleaned while a
failed one keeps its rows. A missing manifest means no runner reported and
the loader falls back to the pre-#233 payload-presence behavior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

FILENAME = "ran_sources.txt"

# A structural line names a block: no leading space (so a folded continuation
# line never counts as structure). Component names are case-insensitive, but a
# VEVENT the extractor cannot read is refused in _scan_blocks.
BLOCK_LINE = re.compile(r"^(BEGIN|END):([A-Za-z0-9-]+)$", re.IGNORECASE)

# iCalendar text is UTF-8 and may hold U+2028 or U+0085 inside a property value,
# so a physical line ends only at CR or LF.
LINE_BREAK = re.compile(r"\r\n|\n|\r")

# Internal failure names for the structural scan; neither is a public kind.
_UNCLOSED = "unclosed"
_MALFORMED = "malformed"

CALENDAR = "calendar"
NOT_CALENDAR = "not_calendar"
TRUNCATED = "truncated"
UNREADABLE = "unreadable"


@dataclass(frozen=True)
class Outcome:
    """What the bytes are: ``kind``, an optional cause ``detail`` (only for
    ``not_calendar``: html / json / empty / unknown), and the ``events`` count.
    """

    kind: str
    detail: str | None = None
    events: int = 0


def _content_detail(body: str) -> str:
    """Best-effort label for what a non-calendar body actually contains."""
    head = body[:512].lstrip().lower()
    if not head:
        return "empty"
    if head.startswith(("<!doctype", "<html")) or "<html" in head:
        return "html"
    if head.startswith(("{", "[")):
        return "json"
    return "unknown"


def _scan_blocks(body: str) -> tuple[str | None, int]:
    """The first structural failure (or ``None``) and the completed event count.

    ``unclosed`` is a block still open at the end of the body (a cut-off
    download); ``malformed`` is anything else — an ``END`` that does not close
    the block it is in, a top-level block that is not a calendar, content
    outside every block, or a ``VEVENT`` whose marker is not uppercase. A
    lowercase event marker is refused because the fallback extractor is
    uppercase-only while the recurring path parses any case, so such a body
    can extract only partly. A ``VEVENT`` counts once its own uppercase
    ``END:VEVENT`` closes it.
    """
    stack: list[str] = []
    problem: str | None = None
    events = 0
    saw_calendar = False
    for line in LINE_BREAK.split(body):
        match = BLOCK_LINE.match(line.rstrip())
        if not match:
            if not stack and line.strip():
                problem = problem or _MALFORMED
            continue
        marker = match.group(0)
        readable = marker == marker.upper()
        tag, name = match.group(1).upper(), match.group(2).upper()
        if name == "VEVENT" and not readable:
            problem = problem or _MALFORMED
        if tag == "BEGIN":
            if not stack:
                if name != "VCALENDAR":
                    problem = problem or _MALFORMED
                    continue
                saw_calendar = True
            stack.append(name)
        elif stack and stack[-1] == name:
            stack.pop()
            if name == "VEVENT" and readable:
                events += 1
        else:
            problem = problem or _MALFORMED
    if problem is not None:
        return problem, events
    if stack:
        return _UNCLOSED, events
    if not saw_calendar:
        return _MALFORMED, events
    return None, events


def classify(body: str) -> Outcome:
    """Classify an already-fetched body.

    A body whose blocks do not pair up is a failed ingestion, not a quiet
    source, because combine_ics extracts only complete events from it.
    Requiring the structure keeps the sweep boundary where ADR 0017 put it.
    """
    body = body.removeprefix("\ufeff")
    problem, events = _scan_blocks(body)
    if problem is None:
        return Outcome(CALENDAR, None, events)
    if problem == _UNCLOSED:
        return Outcome(TRUNCATED, None, events)
    return Outcome(NOT_CALENDAR, _content_detail(body), events)


def classify_file(path: Path) -> Outcome:
    """Classify a file: one read, and an unreadable file is a kind, not a crash."""
    try:
        return classify(path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return Outcome(UNREADABLE)


def record_ran(ics_path: Path) -> Outcome:
    """Record the calendar's stem in the manifest beside it, and return the outcome.

    Appends rather than writes so the scraper and feed runners can both
    contribute to one city's manifest; the loader de-duplicates. This is the
    only writer of the manifest and the single gate: only a complete calendar
    counts as ran, so a failed source keeps its rows (#233).
    """
    outcome = classify_file(ics_path)
    if outcome.kind != CALENDAR:
        return outcome
    manifest = ics_path.parent / FILENAME
    with manifest.open("a") as f:
        f.write(ics_path.stem + "\n")
    return outcome
