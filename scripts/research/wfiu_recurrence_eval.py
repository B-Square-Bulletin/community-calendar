#!/usr/bin/env python3
"""Evaluate recurrence parsers against the WFIU free-text corpus.

Ticket: B-Square-Bulletin/community-calendar#132
Corpus: docs/fixtures/wfiu-recurrence-corpus.txt

Run with a throwaway venv that has `recurrent`, `dateparser`, and
`python-dateutil` installed, e.g.:

    uv venv /tmp/recvenv && uv pip install --python /tmp/recvenv/bin/python \
        recurrent dateparser python-dateutil
    /tmp/recvenv/bin/python scripts/research/wfiu_recurrence_eval.py

The script is read-only with respect to the corpus. It prints a per-pattern
PASS/FAIL summary for the hand-rolled parser and the library alternatives.
"""

# ruff: noqa: DTZ001, DTZ007 -- WFIU carries no timezone; evaluation is naive.

from __future__ import annotations

import contextlib
import datetime as dt
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

try:
    from dateutil.rrule import rrulestr
except ImportError:  # pragma: no cover
    sys.exit("python-dateutil is required")

HERE = Path(__file__).resolve().parent
CORPUS = HERE / ".." / ".." / "docs" / "fixtures" / "wfiu-recurrence-corpus.txt"

recurrent: Any = None
dateparser: Any = None
with contextlib.suppress(ImportError):
    import recurrent  # type: ignore
with contextlib.suppress(ImportError):
    import dateparser  # type: ignore

NOW = dt.datetime(2026, 9, 18, 0, 0)
DOW = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
NAME_TO_DOW = {
    "Monday": "MO",
    "Tuesday": "TU",
    "Wednesday": "WE",
    "Thursday": "TH",
    "Friday": "FR",
    "Saturday": "SA",
    "Sunday": "SU",
    "Mon": "MO",
    "Tue": "TU",
    "Wed": "WE",
    "Thu": "TH",
    "Fri": "FR",
    "Sat": "SA",
    "Sun": "SU",
}
DOW_TO_NAME = {v: k for k, v in NAME_TO_DOW.items() if len(k) > 3}
MONTH_RE = r"[A-Z][a-z]{2}"
TIME_RE = r"\d{1,2}:\d{2} [AP]M"
NICE_DATE_RE = rf"{MONTH_RE} \d{{1,2}}, \d{{4}}"  # "Sep 20, 2026"
ONEOFF_DATE_RE = rf"\d{{1,2}} {MONTH_RE} \d{{4}}"  # "18 Sep 2026"


def parse_clock(s: str) -> dt.time:
    return dt.datetime.strptime(s, "%I:%M %p").time()


def parse_nice_date(s: str) -> dt.date:
    return dt.datetime.strptime(s.rstrip("."), "%b %d, %Y").date()


def parse_oneoff_date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%d %b %Y").date()


def load_corpus() -> OrderedDict[str, list[str]]:
    sections: OrderedDict[str, list[str]] = OrderedDict(
        [("recurring", []), ("one-off", []), ("synthetic", [])]
    )
    with CORPUS.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            for key in sections:
                if line.startswith(key + ":"):
                    value = line[len(key) + 1 :].strip()
                    if value:
                        sections[key].append(value)
    return sections


class Parsed:
    def __init__(
        self,
        kind: str,
        rrule: str | None = None,
        times: list | None = None,
        dtstart: dt.datetime | None = None,
        until: dt.date | None = None,
        byday: list | None = None,
        interval: int | None = None,
        freq: str | None = None,
    ) -> None:
        self.kind = kind
        self.rrule = rrule
        self.times = times or []
        self.dtstart = dtstart
        self.until = until
        self.byday = byday or []
        self.interval = interval
        self.freq = freq


def parse_wfiu(raw: str) -> Parsed:
    """Hand-rolled parser for the Brightspot PromoEvent-time template.

    Returns Parsed(kind='unknown') when nothing matches.
    """
    s = raw.strip()
    # one-off timed: "TIME - TIME on Ddd, D Mon YYYY"
    m = re.match(rf"^({TIME_RE}) - ({TIME_RE}) on {MONTH_RE}, ({ONEOFF_DATE_RE})$", s)
    if m:
        day = parse_oneoff_date(m.group(3))
        return Parsed(
            "one-off",
            dtstart=dt.datetime.combine(day, parse_clock(m.group(1))),
            times=[(None, parse_clock(m.group(1)), parse_clock(m.group(2)))],
        )

    # multi-day all-day: "Mon D - Mon D, YYYY"
    m = re.match(rf"^({MONTH_RE}) (\d{{1,2}}) - ({MONTH_RE}) (\d{{1,2}}), (\d{{4}})$", raw.strip())
    if m:
        start = dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(5)}", "%b %d %Y").date()
        end = dt.datetime.strptime(f"{m.group(3)} {m.group(4)} {m.group(5)}", "%b %d %Y").date()
        return Parsed(
            "multi-day",
            dtstart=dt.datetime.combine(start, dt.time(0, 0)),
            until=end,
            times=[(None, None, None)],
        )

    # date-only / all-day single: "Mon D, YYYY"
    m = re.match(rf"^({NICE_DATE_RE})$", raw.strip())
    if m:
        day = parse_nice_date(m.group(1))
        return Parsed(
            "date-only", dtstart=dt.datetime.combine(day, dt.time(0, 0)), times=[(None, None, None)]
        )

    # all-day daily: "all day through Mon D, YYYY"
    m = re.match(rf"^all day through ({NICE_DATE_RE})$", raw.strip())
    if m:
        until = parse_nice_date(m.group(1))
        return Parsed(
            "daily",
            rrule=f"FREQ=DAILY;UNTIL={until.strftime('%Y%m%d')}T235959",
            until=until,
            freq="DAILY",
            interval=1,
            times=[(None, None, None)],
        )

    # daily: "TIME - TIME, every day through Mon D, YYYY."
    m = re.match(rf"^({TIME_RE}) - ({TIME_RE}), every day through ({NICE_DATE_RE})\.$", raw.strip())
    if m:
        until = parse_nice_date(m.group(3))
        return Parsed(
            "daily",
            rrule=f"FREQ=DAILY;UNTIL={until.strftime('%Y%m%d')}T235959",
            until=until,
            freq="DAILY",
            interval=1,
            times=[(None, parse_clock(m.group(1)), parse_clock(m.group(2)))],
        )

    # monthly on <Weekday> (optionally every N months): "TIME - TIME, every [N] month[s] on <W> through DATE."
    m = re.match(
        rf"^({TIME_RE}) - ({TIME_RE}), every (?:(other|\d+) )?months? on ([A-Z][a-z]+) "
        rf"through ({NICE_DATE_RE})\.$",
        raw.strip(),
    )
    if m:
        interval = 2 if m.group(3) == "other" else int(m.group(3)) if m.group(3) else 1
        until = parse_nice_date(m.group(5))
        byday = NAME_TO_DOW[m.group(4)]
        return Parsed(
            "monthly",
            rrule=(
                f"FREQ=MONTHLY;INTERVAL={interval};BYDAY={byday};"
                f"UNTIL={until.strftime('%Y%m%d')}T235959"
            ),
            until=until,
            freq="MONTHLY",
            interval=interval,
            byday=[byday],
            times=[(byday, parse_clock(m.group(1)), parse_clock(m.group(2)))],
        )

    # monthly / N-monthly header + weekday schedule
    parts = [p.strip() for p in raw.split("||")]
    header, schedule = parts[0], parts[1:]
    m = re.match(rf"^Every (?:(other|\d+) )?months? through ({NICE_DATE_RE})\.$", header)
    if m:
        interval = 2 if m.group(1) == "other" else int(m.group(1)) if m.group(1) else 1
        until = parse_nice_date(m.group(2))
        byday, times = _read_schedule(schedule)
        if byday is None:
            return Parsed("unknown")
        return Parsed(
            "monthly",
            rrule=(
                f"FREQ=MONTHLY;INTERVAL={interval};BYDAY={','.join(byday)};"
                f"UNTIL={until.strftime('%Y%m%d')}T235959"
            ),
            until=until,
            freq="MONTHLY",
            interval=interval,
            byday=byday,
            times=times,
        )

    # weekly / N-weekly: "Every [N|other] week[s] through DATE. || <Weekday>: TIME - TIME"
    m = re.match(rf"^Every (?:(other|\d+) )?weeks? through ({NICE_DATE_RE})\.$", header)
    if m:
        interval = 2 if m.group(1) == "other" else int(m.group(1)) if m.group(1) else 1
        until = parse_nice_date(m.group(2))
        byday, times = _read_schedule(schedule)
        if byday is None:
            return Parsed("unknown")
        return Parsed(
            "weekly",
            rrule=(
                f"FREQ=WEEKLY;INTERVAL={interval};BYDAY={','.join(byday)};"
                f"UNTIL={until.strftime('%Y%m%d')}T235959"
            ),
            until=until,
            freq="WEEKLY",
            interval=interval,
            byday=byday,
            times=times,
        )

    return Parsed("unknown")


def _read_schedule(schedule: list[str]):
    byday, times = [], []
    for item in schedule:
        dm = re.match(rf"^([A-Z][a-z]+): ({TIME_RE}) - ({TIME_RE})$", item)
        if not dm:
            return None, []
        code = NAME_TO_DOW[dm.group(1)]
        byday.append(code)
        times.append((code, parse_clock(dm.group(2)), parse_clock(dm.group(3))))
    return byday, times


def anchored_start(parsed: Parsed, base: dt.datetime) -> dt.datetime:
    """WFIU cards show a next-occurrence date; emulate that DTSTART anchor."""
    if parsed.kind in ("one-off", "date-only", "multi-day"):
        return parsed.dtstart or base
    if parsed.kind == "weekly" and parsed.byday:
        for i in range(14):
            cand = base + dt.timedelta(days=i)
            if DOW[cand.weekday()] in parsed.byday:
                return cand
    return base


def expand(parsed: Parsed, horizon_days: int = 400) -> list[dt.datetime]:
    start = anchored_start(parsed, NOW)
    if not parsed.rrule:
        return [start]
    rule = rrulestr(parsed.rrule, dtstart=start)
    return list(rule.between(start, start + dt.timedelta(days=horizon_days), inc=True))


def recurrent_clause(raw: str) -> str:
    """Reduce a PromoEvent-time string to the clause `recurrent` is meant to see.

    WFIU writes its end bound with "through"; recurrent only recognises
    "until"/"end". Times are stripped so recurrent is not confused by the
    "HH:MM - HH:MM" clock range.
    """
    s = raw.split("||")[0].strip().rstrip(".")
    s = re.sub(rf"^{TIME_RE} - {TIME_RE}, ", "", s)
    s = re.sub(r"^Every week", "every week", s)
    s = re.sub(r"^Every (?P<n>other|\d+) weeks?", r"every \g<n> weeks", s)
    s = re.sub(r"\s+through\s+", " until ", s)
    return s


def recurrent_parse(raw: str):
    if recurrent is None:
        return None, "recurrent not installed"
    clause = recurrent_clause(raw)
    try:
        out = recurrent.RecurringEvent(NOW).parse(clause)
    except Exception as exc:  # pragma: no cover
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(out, str) or not out.startswith("RRULE"):
        return out, f"non-RRULE ({type(out).__name__})"
    try:
        rrulestr(out, dtstart=NOW)
    except Exception as exc:
        return out, f"unexpandable RRULE: {exc}"
    return out, None


def recurrent_raw(raw: str):
    if recurrent is None:
        return None
    try:
        out = recurrent.RecurringEvent(NOW).parse(raw)
        return out
    except Exception as exc:  # pragma: no cover
        return f"{type(exc).__name__}: {exc}"


def dateparser_probe(raw: str):
    if dateparser is None:
        return None
    settings = {"RELATIVE_BASE": NOW, "DATE_ORDER": "MDY"}
    whole = dateparser.parse(raw, settings=settings)
    scalars = re.findall(NICE_DATE_RE + "|" + ONEOFF_DATE_RE, raw)
    scalar = dateparser.parse(scalars[0], settings=settings) if scalars else None
    return whole, scalar


def rrulestr_raw(raw: str):
    try:
        return rrulestr(raw)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def check_parsed(raw: str, parsed: Parsed):
    if parsed.kind == "unknown":
        return False, "unclassified"
    if parsed.kind in ("one-off", "date-only"):
        if not parsed.dtstart:
            return False, "no dtstart"
        note = "all-day" if parsed.kind == "date-only" else "explicit datetime"
        return True, note
    if parsed.kind == "multi-day":
        if not parsed.until:
            return False, "no end"
        return True, f"{parsed.dtstart.date()}..{parsed.until}"  # type: ignore[union-attr]
    if parsed.until is None:
        return False, "no UNTIL bound"
    occ = expand(parsed)
    if not occ:
        return False, "expands to zero occurrences"
    if parsed.freq == "WEEKLY" and parsed.byday:
        got = {DOW[o.weekday()] for o in occ}
        if got != set(parsed.byday):
            return False, f"dow mismatch {got} vs {parsed.byday}"
    return True, f"{len(occ)} occurrences, until={parsed.until}"


def check_recurrent(parsed: Parsed, raw: str):
    if recurrent is None:
        return None, "not installed"
    rrule, err = recurrent_parse(raw)
    if parsed.kind == "one-off":
        if isinstance(rrule, dt.datetime):
            return True, f"datetime {rrule:%Y-%m-%d %H:%M}"
        return False, err or f"non-RRULE ({type(rrule).__name__})"
    if err:
        return False, err
    assert isinstance(rrule, str)
    if parsed.kind in ("daily", "weekly", "monthly"):
        if "UNTIL=" not in rrule:
            return False, f"lost UNTIL: {rrule}"
        if parsed.freq and f"FREQ={parsed.freq}" not in rrule:
            return False, f"freq mismatch: {rrule}"
        if parsed.interval and parsed.interval > 1 and f"INTERVAL={parsed.interval}" not in rrule:
            return False, f"interval mismatch: {rrule}"
    return True, rrule


REPRESENTATIVES = [
    ("one-off timed", "06:30 PM - 08:30 PM on Fri, 18 Sep 2026", "observed"),
    (
        "daily `every day through <date>`",
        "09:00 AM - 10:00 PM, every day through Sep 20, 2026.",
        "observed",
    ),
    (
        "weekly + day-of-week/time prefix",
        "Every week through Oct 31, 2026. || Tuesday: 12:00 PM - 04:00 PM",
        "observed",
    ),
    (
        "`every N weeks` + prefix",
        "Every 7 weeks through Oct 14, 2026. || Wednesday: 12:30 PM - 02:30 PM",
        "observed",
    ),
    (
        "monthly `every month on <Weekday>`",
        "03:00 PM - 04:00 PM, every month on Friday through Sep 25, 2026.",
        "observed",
    ),
    ("date-only / all-day", "Sep 18, 2026", "synthetic"),
    ("multi-day", "Sep 18 - Sep 20, 2026", "synthetic"),
    (
        "`every N months`",
        "Every 2 months through Dec 31, 2026. || Tuesday: 12:00 PM - 01:00 PM",
        "synthetic",
    ),
    (
        "`every 2 weeks` (interval)",
        "Every 2 weeks through Dec 17, 2026. || Thursday: 04:00 PM - 05:45 PM",
        "synthetic",
    ),
]


def main() -> int:
    sections = load_corpus()
    print("recurrent:", "installed" if recurrent else "MISSING")
    print("dateparser:", "installed" if dateparser else "MISSING")
    print("dateutil: rrulestr available\n")

    all_strings = sections["recurring"] + sections["one-off"] + sections["synthetic"]
    kinds = {raw: parse_wfiu(raw) for raw in all_strings}
    classified = sum(1 for p in kinds.values() if p.kind != "unknown")
    print(
        f"hand-rolled classifier: {classified}/{len(all_strings)} classified "
        f"({len(all_strings) - classified} unknown)"
    )
    unknown = [r for r, p in kinds.items() if p.kind == "unknown"]
    for r in unknown:
        print("  UNKNOWN:", repr(r))

    print("\n== per-pattern matrix (corpus section in parens) ==")
    header = f"{'pattern':<40} {'hand-rolled':<42} {'recurrent (normalized)':<52} {'rrulestr(raw)':<12} dateparser"
    print(header)
    print("-" * len(header))
    for label, raw, origin in REPRESENTATIVES:
        parsed = parse_wfiu(raw)
        ok, note = check_parsed(raw, parsed)
        hr = f"{'PASS' if ok else 'FAIL'} {note}"

        if origin == "synthetic":
            rec = "n/a (not observed)"
        else:
            rok, rnote = check_recurrent(parsed, raw)
            rec = f"{'PASS' if rok else 'FAIL'} {rnote}" if rok is not None else rnote

        raw_rr = rrulestr_raw(raw)
        rr = "PASS" if not isinstance(raw_rr, str) else "FAIL"

        dp = dateparser_probe(raw)
        if dp is None:
            dptxt = "not installed"
        else:
            whole, scalar = dp
            dptxt = "whole=None" if whole is None else f"whole={whole:%Y-%m-%d %H:%M}"
            if scalar is not None:
                dptxt += f", scalar={scalar:%Y-%m-%d}"
        print(f"{label:<40} {hr:<42} {rec:<52} {rr:<12} {dptxt}")

    if recurrent is not None:
        print("\n== recurrent over observed recurring corpus (clause normalized) ==")
        npass = 0
        for raw in sections["recurring"]:
            parsed = parse_wfiu(raw)
            rok, rnote = check_recurrent(parsed, raw)
            npass += bool(rok)
            print(f"  {'PASS' if rok else 'FAIL'}  {raw[:66]:<68} {rnote}")
        print(
            f"  {npass}/{len(sections['recurring'])} PASS with `through`->`until` + time stripping"
        )

        print("\n== recurrent on the RAW (unnormalized) template ==")
        for raw in [
            "Every week through Oct 31, 2026. || Tuesday: 12:00 PM - 04:00 PM",
            "09:00 AM - 10:00 PM, every day through Sep 20, 2026.",
            "Every 7 weeks through Oct 14, 2026. || Wednesday: 12:30 PM - 02:30 PM",
        ]:
            print(f"  {raw[:66]:<68} -> {recurrent_raw(raw)!r}")

        print("\n== recurrent on observed one-off / synthetic edge cases (raw) ==")
        for raw in [
            "06:30 PM - 08:30 PM on Fri, 18 Sep 2026",
            "Sep 18, 2026",
            "Sep 18 - Sep 20, 2026",
        ]:
            print(f"  {raw[:66]:<68} -> {recurrent_raw(raw)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
