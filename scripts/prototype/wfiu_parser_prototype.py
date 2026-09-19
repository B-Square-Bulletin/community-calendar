#!/usr/bin/env python3
"""PROTOTYPE — throwaway. Wipe me.

Answers ticket #133: *does a WFIU listing+detail parser with free-text
recurrence expansion produce event dicts we trust, and where does it break?*

Not production. Not registered. No tests. It parses the captured HTML fixtures
under `docs/fixtures/wfiu/` offline and writes a self-contained HTML report
(`wfiu_parser_prototype_report.html`) plus a stdout table.

Run:  python scripts/prototype/wfiu_parser_prototype.py
"""

# ruff: noqa: DTZ001, DTZ007 -- WFIU carries no timezone; the prototype is naive.

from __future__ import annotations

import datetime as dt
import hashlib
import re
from pathlib import Path

from bs4 import BeautifulSoup
from dateutil.rrule import rrulestr

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "docs" / "fixtures" / "wfiu"
CORPUS = FIX / "wfiu-recurrence-corpus.txt"
REPORT = Path(__file__).resolve().parent / "wfiu_parser_prototype_report.html"

NOW = dt.datetime(2026, 9, 18, 0, 0)
HORIZON_DAYS = 90
ALLOWLIST = {
    "bloomington",
    "nashville",
    "spencer",
    "martinsville",
    "ellettsville",
    "brown county",
    "bedford",
    "columbus",
}

TIME_RE = r"\d{1,2}:\d{2} [AP]M"
MONTH_RE = r"[A-Z][a-z]{2}"
NICE_DATE_RE = rf"{MONTH_RE} \d{{1,2}}, \d{{4}}"
ONEOFF_DATE_RE = rf"\d{{1,2}} {MONTH_RE} \d{{4}}"
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
WEEKDAY_WORDS = [d for d in NAME_TO_DOW if len(d) > 3]


# --------------------------------------------------------------------------
# The liftable logic: parse free-text recurrence -> structured rule
# --------------------------------------------------------------------------


def parse_clock(s: str) -> dt.time:
    return dt.datetime.strptime(s, "%I:%M %p").time()


def parse_nice(s: str) -> dt.date:
    return dt.datetime.strptime(s.rstrip("."), "%b %d, %Y").date()


def _schedule(text: str):
    """Parse '<Weekday>: HH:MM AM - HH:MM AM' entries, which the site renders
    space-separated on one line (and sometimes duplicated)."""
    byday, times = [], []
    for name, start, end in re.findall(rf"([A-Z][a-z]+): ({TIME_RE}) - ({TIME_RE})", text):
        code = NAME_TO_DOW[name]
        if code not in byday:  # source emits duplicate weekdays
            byday.append(code)
            times.append((code, parse_clock(start), parse_clock(end)))
    return (byday, times) if byday else (None, [])


def parse_recurrence(raw: str) -> dict:
    """Return {kind, rrule, dtstart, first_time, until, times} or kind='unknown'."""
    s = " ".join(raw.split())
    # one-off timed
    m = re.match(rf"^({TIME_RE}) - ({TIME_RE}) on {MONTH_RE}, ({ONEOFF_DATE_RE})$", s)
    if m:
        day = dt.datetime.strptime(m.group(3), "%d %b %Y").date()
        return {
            "kind": "one-off",
            "dtstart": dt.datetime.combine(day, parse_clock(m.group(1))),
            "first_time": parse_clock(m.group(1)),
            "end_time": parse_clock(m.group(2)),
        }
    # multi-day all-day
    m = re.match(rf"^({MONTH_RE}) (\d{{1,2}}) - ({MONTH_RE}) (\d{{1,2}}), (\d{{4}})$", s)
    if m:
        start = dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(5)}", "%b %d %Y").date()
        end = dt.datetime.strptime(f"{m.group(3)} {m.group(4)} {m.group(5)}", "%b %d %Y").date()
        return {
            "kind": "multi-day",
            "dtstart": dt.datetime.combine(start, dt.time(0, 0)),
            "until": end,
            "all_day": True,
        }
    # all-day single
    m = re.match(rf"^({NICE_DATE_RE})$", s)
    if m:
        day = parse_nice(m.group(1))
        return {
            "kind": "date-only",
            "dtstart": dt.datetime.combine(day, dt.time(0, 0)),
            "until": day,
            "all_day": True,
        }
    # all-day daily
    m = re.match(rf"^all day through ({NICE_DATE_RE})$", s)
    if m:
        until = parse_nice(m.group(1))
        return {"kind": "daily", "freq": "DAILY", "interval": 1, "until": until}
    # daily timed
    m = re.match(rf"^({TIME_RE}) - ({TIME_RE}), every day through ({NICE_DATE_RE})\.$", s)
    if m:
        until = parse_nice(m.group(3))
        return {
            "kind": "daily",
            "freq": "DAILY",
            "interval": 1,
            "until": until,
            "first_time": parse_clock(m.group(1)),
            "end_time": parse_clock(m.group(2)),
        }
    # monthly on <Weekday>
    m = re.match(
        rf"^({TIME_RE}) - ({TIME_RE}), every (?:(other|\d+) )?months? on ([A-Z][a-z]+) "
        rf"through ({NICE_DATE_RE})\.$",
        s,
    )
    if m:
        interval = 2 if m.group(3) == "other" else int(m.group(3)) if m.group(3) else 1
        until = parse_nice(m.group(5))
        byday = NAME_TO_DOW[m.group(4)]
        return {
            "kind": "monthly",
            "freq": "MONTHLY",
            "interval": interval,
            "byday": [byday],
            "until": until,
            "first_time": parse_clock(m.group(1)),
            "end_time": parse_clock(m.group(2)),
        }
    # "Every [N] weeks/months through <date>. <Weekday>: HH:MM - HH:MM [...]"
    m = re.match(rf"^Every (?:(other|\d+) )?(weeks?|months?) through ({NICE_DATE_RE})\.(.*)$", s)
    if m:
        interval = 2 if m.group(1) == "other" else int(m.group(1)) if m.group(1) else 1
        freq = "WEEKLY" if m.group(2).startswith("week") else "MONTHLY"
        until = parse_nice(m.group(3))
        byday, times = _schedule(m.group(4))
        if byday is None:
            return {"kind": "unknown", "raw": raw}
        first = times[0]
        return {
            "kind": freq.lower(),
            "freq": freq,
            "interval": interval,
            "byday": byday,
            "until": until,
            "first_time": first[1],
            "end_time": first[2],
        }
    return {"kind": "unknown", "raw": raw}


def expand(parsed: dict, anchor: dt.date) -> list[dt.datetime]:
    kind = parsed["kind"]
    if kind == "one-off":
        return [parsed["dtstart"]]
    if kind in ("date-only", "multi-day"):
        return [parsed["dtstart"]]
    if kind == "unknown":
        return []
    start = dt.datetime.combine(anchor, parsed.get("first_time") or dt.time(0, 0))
    until = min(
        dt.datetime.combine(parsed["until"], dt.time(23, 59)),
        dt.datetime.combine(anchor, dt.time(0, 0)) + dt.timedelta(days=HORIZON_DAYS),
    )
    rrule = f"FREQ={parsed['freq']};INTERVAL={parsed.get('interval', 1)}"
    if parsed.get("byday"):
        rrule += f";BYDAY={','.join(parsed['byday'])}"
    rrule += f";UNTIL={until.strftime('%Y%m%dT%H%M%S')}"
    return list(rrulestr(rrule, dtstart=start).between(start, until, inc=True))


# --------------------------------------------------------------------------
# Parsing captured HTML
# --------------------------------------------------------------------------


def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def parse_cards(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for node in soup.select("ps-promo.PromoEvent"):
        link = node.select_one("a.PromoEvent-link-link")
        cards.append(
            {
                "url": link["href"] if link else None,
                "title": _text(node.select_one(".PromoEvent-title")),
                "venue_name": _text(node.select_one(".PromoEvent-venue")),
                "date_display": _text(node.select_one(".PromoEvent-date-date")),
                "time_raw": _text(node.select_one(".PromoEvent-time")),
                "recurring": node.select_one(".PromoEvent-time[data-recurring]") is not None,
                "price": _text(node.select_one(".PromoEvent-price")),
                "categories": [_text(a) for a in node.select(".PromoEvent-categories-item a")],
                "description": _text(node.select_one(".PromoEvent-description")),
            }
        )
    return cards


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.select_one("meta[name='brightspot.contentId']")
    city = _text(soup.select_one(".VenueInformation-address-city"))
    return {
        "content_id": meta["content"] if meta else None,
        "name": _text(soup.select_one(".EventPage-name")),
        "venue_name": _text(soup.select_one(".VenueInformation-name")),
        "street": _text(soup.select_one(".VenueInformation-address-streetAddress")),
        "city": city,
        "state": _text(soup.select_one(".VenueInformation-address-state")),
        "zip": _text(soup.select_one(".VenueInformation-address-zip")),
        "description": _text(soup.select_one(".EventPage-description")),
        "ticket_url": (soup.select_one(".EventPage-ticketing a[href]") or {}).get("href"),
        "presenting_org": _text(soup.select_one(".PresentingOrganizationInformation-name")),
        "image_url": (soup.select_one(".EventPage-image img") or {}).get("src"),
    }


def city_from_text(text: str) -> str:
    m = re.search(r",\s*([A-Z][A-Za-z .]+),\s*(?:IN|Indiana)\b", text)
    return m.group(1).strip() if m else ""


def anchor_date(display: str, fallback: dt.date) -> dt.date:
    m = re.match(rf"({MONTH_RE}) (\d{{1,2}})", display)
    if not m:
        return fallback
    for year in (NOW.year, NOW.year + 1):
        try:
            d = dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {year}", "%b %d %Y").date()
        except ValueError:
            continue
        if d >= fallback - dt.timedelta(days=1):
            return d
    return fallback


# --------------------------------------------------------------------------
# Build events + flag breaks
# --------------------------------------------------------------------------


def build_events(card: dict, detail: dict | None) -> tuple[list[dict], list[str]]:
    flags: list[str] = []
    parsed = parse_recurrence(card["time_raw"])
    kwargs = detail or {}
    city = kwargs.get("city") or city_from_text(card["description"])
    if not city:
        flags.append("no city (detail never fetched?)")
    elif city.lower() not in ALLOWLIST:
        flags.append(f"OUT OF REGION: {city}")

    if parsed["kind"] == "unknown":
        flags.append(f"UNPARSEABLE recurrence: {card['time_raw']!r}")
    if parsed.get("kind") == "daily" and parsed.get("until"):
        span = (parsed["until"] - anchor_date(card["date_display"], NOW.date())).days
        if span > 14:
            flags.append(f"long 'daily' series ({span}d) — description may say weekly")
    if parsed.get("freq") == "DAILY":
        for day in WEEKDAY_WORDS:
            if day.lower() + "s" in card["description"].lower():
                flags.append(f"conflict: recurrence says daily, description says {day}s")
                break

    anchor = anchor_date(card["date_display"], NOW.date())
    occurrences = expand(parsed, anchor)
    if len(occurrences) > 30:
        flags.append(f"{len(occurrences)} occurrences — cardinality risk")
    if parsed["kind"] in ("one-off", "date-only", "multi-day") and occurrences:
        occurrences = [o for o in occurrences if o.date() >= NOW.date() - dt.timedelta(days=1)]

    events = []
    for occ in occurrences:
        if not (
            NOW.date() - dt.timedelta(days=1)
            <= occ.date()
            <= NOW.date() + dt.timedelta(days=HORIZON_DAYS)
        ):
            continue
        end = None
        if kwargs.get("kind") is None and parsed.get("end_time") is not None:
            end = dt.datetime.combine(occ.date(), parsed["end_time"])
        if end is not None and end <= occ:
            end += dt.timedelta(days=1)
        key = (kwargs.get("content_id") or card["url"] or card["title"]) + occ.date().isoformat()
        events.append(
            {
                "uid": hashlib.sha1(key.encode()).hexdigest()[:12],
                "title": card["title"],
                "dtstart": occ,
                "dtend": end,
                "all_day": parsed.get("all_day", False) or parsed.get("first_time") is None,
                "url": card["url"],
                "location": ", ".join(
                    x for x in [kwargs.get("venue_name") or card["venue_name"], city] if x
                ),
                "description": kwargs.get("description") or card["description"],
                "image_url": kwargs.get("image_url"),
                "ticket_url": kwargs.get("ticket_url"),
                "source": "WFIU Community Calendar",
            }
        )
    return events, flags


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


EVENT_LINE = re.compile(r"^(\d{1,2}:\d{2} [AP]M|all day|Every)")


def load_corpus() -> list[str]:
    out = []
    for line in CORPUS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if EVENT_LINE.match(line):
            out.append(line)
    return out


def html_escape(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(cards, details, events, flags, corpus_rows) -> str:
    rows = "\n".join(
        f"<tr><td>{html_escape(e['title'])}</td><td>{e['dtstart']:%Y-%m-%d %H:%M}</td>"
        f"<td>{'all-day' if e['all_day'] else e['dtend'] or ''}</td>"
        f"<td>{html_escape(e['location'])}</td><td><code>{e['uid']}</code></td></tr>"
        for e in events
    )
    flagrows = "\n".join(f"<li>{html_escape(f)}</li>" for f in flags) or "<li>none</li>"
    corows = "\n".join(
        f"<tr><td><code>{html_escape(c[:70])}</code></td><td>{html_escape(parse_recurrence(c)['kind'])}</td>"
        f"<td>{len(expand(parse_recurrence(c), NOW.date()))}</td></tr>"
        for c in corpus_rows
    )
    return f"""<!doctype html><meta charset=utf-8><title>WFIU parser prototype</title>
<style>body{{font:15px/1.5 -apple-system,system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#222}}
h1{{font-size:1.4rem}} h2{{font-size:1.05rem;margin-top:2rem;border-bottom:1px solid #ddd;padding-bottom:.2rem}}
table{{border-collapse:collapse;width:100%;font-size:13px}} td,th{{border:1px solid #e2e2e2;padding:4px 6px;text-align:left;vertical-align:top}}
code{{background:#f4f4f4;padding:0 3px}} .flag{{background:#fff4f4}} li{{margin:.2rem 0}}</style>
<h1>WFIU parser prototype <small>— throwaway, ticket #133</small></h1>
<p><b>Question:</b> does a WFIU listing+detail parser with free-text recurrence expansion
produce event dicts we trust, and where does it break? Parsed offline from
<code>docs/fixtures/wfiu/</code>; now = {NOW:%Y-%m-%d}, horizon = {HORIZON_DAYS}d.</p>

<h2>Parsed cards → events ({len(events)} occurrences from {len(cards)} cards)</h2>
<table><tr><th>title</th><th>start</th><th>end</th><th>location</th><th>uid</th></tr>{rows}</table>

<h2>Breaks / flags</h2><ul class=flag>{flagrows}</ul>

<h2>Recurrence corpus classification ({sum(1 for c in corpus_rows if parse_recurrence(c)["kind"] == "unknown")} unknown of {len(corpus_rows)})</h2>
<table><tr><th>raw</th><th>kind</th><th>occurrences in 90d</th></tr>{corows}</table>
"""


def main() -> int:
    cards = parse_cards((FIX / "wfiu-listing-card.html").read_text(encoding="utf-8"))
    detail = parse_detail((FIX / "wfiu-detail-page.html").read_text(encoding="utf-8"))
    details_by_url = {cards[0]["url"]: detail} if cards else {}

    all_events, all_flags = [], []
    for card in cards:
        events, flags = build_events(card, details_by_url.get(card["url"]))
        all_events += events
        all_flags += [f"[{card['title']}] {f}" for f in flags]

    corpus_rows = load_corpus()
    REPORT.write_text(
        render(cards, details_by_url, all_events, all_flags, corpus_rows), encoding="utf-8"
    )

    print(f"cards={len(cards)} events={len(all_events)} flags={len(all_flags)}")
    print("wrote", REPORT.relative_to(ROOT))
    for card in cards:
        parsed = parse_recurrence(card["time_raw"])
        n = len([e for e in all_events if e["title"] == card["title"]])
        print(
            f"  - {card['title']!r}: kind={parsed['kind']} card_date={card['date_display']!r} "
            f"events={n} raw={card['time_raw']!r}"
        )
    for f in all_flags:
        print("  FLAG", f)
    unknown = [c for c in corpus_rows if parse_recurrence(c)["kind"] == "unknown"]
    print(f"corpus: {len(corpus_rows) - len(unknown)}/{len(corpus_rows)} classified")
    for c in unknown:
        print("  UNKNOWN", repr(c))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
