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

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

FILENAME = "ran_sources.txt"
CALENDAR_MARKER = "BEGIN:VCALENDAR"
CALENDAR_END = "END:VCALENDAR"
EVENT_MARKER = "BEGIN:VEVENT"

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


def classify(body: str) -> Outcome:
    """Classify an already-fetched body.

    A body that opens a calendar but never closes it is a cut-off download: a
    failed ingestion, not a quiet source, because combine_ics extracts no
    complete events from it. Requiring both markers keeps the sweep boundary
    where ADR 0017 put it.
    """
    events = body.count(EVENT_MARKER)
    if CALENDAR_MARKER not in body:
        return Outcome(NOT_CALENDAR, _content_detail(body), events)
    if CALENDAR_END not in body:
        return Outcome(TRUNCATED, None, events)
    return Outcome(CALENDAR, None, events)


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
