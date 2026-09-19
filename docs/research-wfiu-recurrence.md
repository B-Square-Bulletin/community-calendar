# Research: WFIU free-text recurrence — `recurrent` and alternatives

**Ticket:** [#132](https://github.com/B-Square-Bulletin/community-calendar/issues/132)
**Map:** [#130](https://github.com/B-Square-Bulletin/community-calendar/issues/130)
**Sibling:** [#131](https://github.com/B-Square-Bulletin/community-calendar/issues/131) (machine-readable surface)
**Date:** 2026-09-18
**Method:** library inspection from PyPI/sdist/GitHub (primary), plus a live
corpus gathered with a browser User-Agent, plain HTTP, 2.5 s spacing, 28
listing requests, no cookies and no mutation of source data.

## TL;DR

**Do not add `recurrent` as a dependency. Parse the WFIU template with a small
hand-rolled grammar, emit explicit occurrences inside the Horizon, and use
`python-dateutil`'s `rrulestr` only to expand.** `recurrent` can be coaxed to
31/31 on the observed recurring strings, but only after a normalization layer
that rewrites WFIU's `through` to `until` — without it, `recurrent` silently
drops the series end bound. It is also dormant (last release 2021-08-16) and
its own compound-string handling over-generates (see §3).

Per-pattern result on the observed corpus (details in §3):

| Pattern | Hand-rolled | `recurrent` | `rrulestr` (raw text) | `dateparser` |
|---|---|---|---|---|
| one-off timed | **PASS** | PASS (datetime) | FAIL | scalar only |
| daily `every day through <date>` | **PASS** | PASS \* | FAIL | FAIL |
| weekly + day-of-week/time prefix | **PASS** | PASS \* | FAIL | FAIL |
| `every N weeks` + prefix | **PASS** | PASS \* | FAIL | FAIL |
| monthly `every month on <Weekday>` | **PASS** | PASS \* (ambiguous) | FAIL | FAIL |
| date-only / all-day (synthetic) | **PASS** | n/a | FAIL | scalar only |
| multi-day (synthetic) | **PASS** | n/a (loses start) | FAIL | FAIL |
| `every N months` (synthetic) | **PASS** | PASS \* | FAIL | FAIL |

\* PASS only after rewriting `through` → `until` and stripping the clock range;
on the raw string `recurrent` returns an RRULE with **no `UNTIL`**.

Concrete fallback for an unparseable series: emit a **single event at the
card's displayed next occurrence** (`PromoEvent-date-date` + first time range).
Never drop the event. Detect "unparseable" as `parse_wfiu(...).kind == "unknown"`
or as an expansion that yields zero occurrences. Details in §5.

---

## 1. `recurrent` from primary sources

### What it is

`recurrent` "is a python library for natural language parsing and formatting of
dates and recurring events. It turns strings like 'every tuesday and thurs until
next month' into RFC-compliant RRULES, to be fed into a calendar api or
python-dateutil's rrulestr." (`README.md`, github.com/kvh/recurrent). Public API
is two functions (`recurrent/__init__.py`):

```python
def parse(s, now=None):  return RecurringEvent(now).parse(s)
def format(r, now=None): return RecurringEvent(now).format(r)
```

### Input grammar

The grammar is permissive English phrase-matching, not a formal grammar. It is
enumerated by the package's own tests (`recurrent/test.py`, 554 lines) across
daily/weekly/monthly/yearly, ordinals (`first friday of the month`), intervals
(`every other day`, `every 3 weeks`), counts (`fridays twice`, `for 5 times`),
ranges (`from november until february`, `starting in may`), exclusions
(`daily except on June 23rd`), day lists (`tuesdays and thursdays`), and
`weekdays`/`weekends`. Token vocabulary is in `recurrent/constants.py`.

**Critical gap for WFIU:** the end-marker regex only recognises `end`/`until`
(`event_parser.py:30`):

```python
RE_ENDING = re.compile(r'(?:\bend|until)(?:s|ing)?')
```

`through`/`thru` are tokenised as a content type (`RE_THROUGH`,
`constants.py:83`) but are never consumed as an end bound. WFIU writes its end
bound **exclusively** as `through` (see §2), so unmodified `recurrent` loses the
bound.

### Output shape

`parse()` returns one of three shapes (`event_parser.py:241-243`):

> returns a rrule string if it is a recurring date, a datetime.datetime if it is
> a non-recurring date, and None if it is neither.

`get_RFC_rrule()` (`event_parser.py:215`) emits an iCalendar rule string such as
`DTSTART:20100105\nRRULE:FREQ=DAILY;INTERVAL=1;UNTIL=20100201`, or `None` if no
frequency was found. Confirmed live (§3): one-off input yields a `datetime`,
recurrence yields an RRULE string, and clock ranges are parsed as a start time
only.

### License — metadata is inconsistent

- `LICENSE` file: **MIT** ("Copyright (c) 2012 Ken Van Haren", MIT text).
- `setup.py`: `license='BSD'`, classifier `License :: OSI Approved :: BSD License`.
- PyPI JSON: `"license": "BSD"` for 0.4.1.

Both are permissive, but the divergence is a (minor) hygiene flag worth noting
in any dependency review.

### Maintenance status

- Latest PyPI release **0.4.1, 2021-08-16** (PyPI JSON `releases`).
- Repository default branch last commit **2021-08-16** ("Merge pull request #23
  from Mayerch1/formatting", GitHub API). No GitHub releases.
- **270 stars, 33 forks, 5 open issues, not archived** (GitHub API, fetched
  2026-09-18).
- Runtime dependency `parsedatetime` is itself dormant: version 2.6, released
  **2020-05-31** (PyPI JSON).

Verdict: effectively **unmaintained** (~5 years). Not a hard blocker, but a
fresh WFIU scraper should not acquire a dead dependency for a grammar this
small.

### Python version support and dependency weight

- `Requires-Python: >3.6.0` (`setup.py`, wheel `METADATA`); no upper bound.
  Verified working on **3.10, 3.11, 3.12, 3.14** (throwaway venvs,
  `recurrent==0.4.1`).
- Installs exactly one package: `parsedatetime`. Pure Python, no compiled
  extensions; installed footprint ≈ 184 KB + 356 KB (`recurrent` +
  `parsedatetime`, 1,894 lines of Python in `recurrent`).
- Fit as a project dependency: the repo's `pyproject.toml` dependencies are
  `beautifulsoup4, pytz, requests, urllib3, feedparser, icalendar,
  recurring-ical-events, Jinja2, anthropic, tenacity`. Adding `recurrent`
  would be a net-new dormant dependency. `python-dateutil` is already present
  transitively at `2.9.0.post0` via `icalendar` and `recurring-ical-events`
  (checked `uv.lock`), but it is **not** a declared direct dependency.

---

## 2. The corpus

**Asset:** [`docs/fixtures/wfiu-recurrence-corpus.txt`](fixtures/wfiu-recurrence-corpus.txt)
(fetcher: [`scripts/research/wfiu_fetch_corpus.py`](../scripts/research/wfiu_fetch_corpus.py)).

The recurrence text is the `PromoEvent-time` block on each listing card;
recurring cards also carry a `data-recurring` attribute and an
`icon-arrow-rotate` icon. 28 server-rendered listing pages (`?p=1..28`) yielded
**300 cards and 142 distinct strings** (31 recurring, 111 one-off). The live
HTML uses `<br>` separators inside the recurring form; the corpus renders them
as ` || `.

The **entire observed vocabulary** is these five templates:

| Template | Observed example |
|---|---|
| One-off timed | `06:30 PM - 08:30 PM on Fri, 18 Sep 2026` |
| Daily series | `09:00 AM - 10:00 PM, every day through Sep 20, 2026.` |
| Monthly series | `03:00 PM - 04:00 PM, every month on Friday through Sep 25, 2026.` |
| Weekly series | `Every week through Oct 31, 2026. || Tuesday: 12:00 PM - 04:00 PM || …` |
| N-weekly series | `Every 7 weeks through Oct 14, 2026. || Wednesday: 12:30 PM - 02:30 PM` |

The weekly forms can carry **multiple weekdays with different clock ranges**
(e.g. `Tuesday: 12:00 PM - 04:00 PM || Wednesday: 12:00 PM - 04:00 PM ||
Saturday: 10:00 AM - 02:00 PM`). Day-of-week prefixes are always
`<Weekday>: <start> - <end>`.

**Not present** in the 28-page sample: date-only/all-day, multi-day, and
`every N months` were never observed. `every other Thursday` appeared only in a
*description*, not in the structured time field. The corpus therefore adds
labelled `synthetic:` representatives for those templates. `recurrent` was
tested against all 31 observed recurring strings.

---

## 3. Test results

Harness: [`scripts/research/wfiu_recurrence_eval.py`](../scripts/research/wfiu_recurrence_eval.py).
Run with `recurrent==0.4.1`, `dateparser==1.4.3`, `python-dateutil==2.9.0.post0`
on CPython 3.12; `NOW = 2026-09-18`; series anchored at their first matching
occurrence (the card's next-occurrence date).

### 3.1 `recurrent` on the raw WFIU strings (fails to bound the series)

| Raw input | `recurrent.parse(...)` |
|---|---|
| `Every week through Oct 31, 2026. \|\| Tuesday: 12:00 PM - 04:00 PM` | `RRULE:BYDAY=TU;BYMONTHDAY=31;BYMONTH=10;INTERVAL=1;FREQ=WEEKLY` |
| `09:00 AM - 10:00 PM, every day through Sep 20, 2026.` | `RRULE:BYMONTHDAY=20;BYMONTH=9;BYHOUR=9;BYMINUTE=0;INTERVAL=1;FREQ=DAILY` |
| `Every 7 weeks through Oct 14, 2026. \|\| Wednesday: 12:30 PM - 02:30 PM` | `RRULE:BYDAY=WE;BYMONTHDAY=14;BYMONTH=10;INTERVAL=7;FREQ=WEEKLY` |

Every output **omits `UNTIL`**. `through Sep 20, 2026` is mis-read as
`BYMONTH=9;BYMONTHDAY=20` (a September-20-only yearly rule), so the series is
both unbounded and semantically wrong. The frequency and interval are correct;
the bound is lost.

### 3.2 `recurrent` after normalizing `through`→`until` and stripping the clock range

31/31 observed recurring strings PASS:

| Input → normalized clause | `recurrent` RRULE |
|---|---|
| `every day through Sep 20, 2026` → `every day until Sep 20 2026` | `RRULE:INTERVAL=1;FREQ=DAILY;UNTIL=20260920` |
| `Every week … ` → `every week until Oct 31 2026` | `RRULE:INTERVAL=1;FREQ=WEEKLY;UNTIL=20261031` |
| `Every 7 weeks …` → `every 7 weeks until Oct 14 2026` | `RRULE:INTERVAL=7;FREQ=WEEKLY;UNTIL=20261014` |
| `every month on Friday through Sep 25, 2026` → `… until Sep 25 2026` | `RRULE:BYDAY=FR;INTERVAL=1;FREQ=MONTHLY;UNTIL=20260925` |

This proves `recurrent` *can* produce the right rule, but it needs a
source-specific preprocessor — i.e. we would still be hand-writing the WFIU
grammar, then handing the easy half to a dead library.

### 3.3 `recurrent` on edge shapes

| Input | `recurrent.parse(...)` | Note |
|---|---|---|
| `06:30 PM - 08:30 PM on Fri, 18 Sep 2026` | `datetime(2026, 9, 18, 18, 30)` | start only, drop end |
| `Sep 18, 2026` | `datetime(2026, 9, 18, 0, 0)` | usable |
| `Sep 18 - Sep 20, 2026` | `datetime(2026, 9, 20, 0, 0)` | **loses the start date** |

### 3.4 Hand-rolled parser

A ~120-line parser for the five templates classified **148/148** corpus lines
(31 recurring + 111 one-off + 6 synthetic) and expanded correctly with
`dateutil.rrule`:

| Pattern | Input | Output |
|---|---|---|
| one-off | `06:30 PM - 08:30 PM on Fri, 18 Sep 2026` | `dtstart=2026-09-18 18:30`, end 20:30 |
| daily | `09:00 AM - 10:00 PM, every day through Sep 20, 2026.` | `FREQ=DAILY;UNTIL=20260920T235959` → 3 occurrences |
| weekly | `Every week through Oct 31, 2026. \|\| Tuesday: 12:00 PM - 04:00 PM` | `FREQ=WEEKLY;INTERVAL=1;BYDAY=TU;UNTIL=20261031T235959` → 6 |
| N-weekly | `Every 7 weeks through Oct 14, 2026. \|\| Wednesday: 12:30 PM - 02:30 PM` | `FREQ=WEEKLY;INTERVAL=7;BYDAY=WE;UNTIL=20261014T235959` |
| monthly | `03:00 PM - 04:00 PM, every month on Friday through Sep 25, 2026.` | `FREQ=MONTHLY;INTERVAL=1;BYDAY=FR;UNTIL=20260925T235959` |
| date-only | `Sep 18, 2026` | single all-day event |
| multi-day | `Sep 18 - Sep 20, 2026` | explicit range 09-18..09-20 |
| N-monthly | `Every 2 months through Dec 31, 2026. \|\| Tuesday: 12:00 PM - 01:00 PM` | `FREQ=MONTHLY;INTERVAL=2;BYDAY=TU;UNTIL=20261231T235959` |

The only semantic ambiguity is **monthly-on-a-weekday**: `every month on Friday`
becomes `FREQ=MONTHLY;BYDAY=FR`, which selects *every* Friday of the month. If
Brightspot's underlying data meant a specific Friday-of-month, the RRULE
over-generates. The text alone cannot distinguish the two, so this should be
flagged rather than guessed (see §5).

---

## 4. Alternatives on the same corpus

| Library | Version | Result | Cost |
|---|---|---|---|
| `dateutil.rrule.rrulestr` | 2.9.0.post0 | **FAIL on all natural-language input.** `'every day through Sep 20, 2026'` → `ValueError: not enough values to unpack`; `'06:30 PM - 08:30 PM on Fri, 18 Sep 2026'` → `ValueError: unsupported property: 06`. It is an RRULE *syntax* parser, not NL. Passes on a well-formed RRULE string. | already locked (transitive) |
| `dateparser` | 1.4.3 | **NL recurrence: FAIL.** `parse()` → `None` for every WFIU recurrence string and for clock ranges. Only the embedded scalar date parses (`'Sep 20, 2026'` → `2026-09-20`). | heavy: pulls `regex` (~1.4 MB), `tzlocal`, `pytz`, `python-dateutil`, `six` |
| Hand-rolled template parser | ~120 lines | **148/148 classified**, correct expansion on all observed + synthetic patterns | zero new deps; `dateutil` already present |

`dateparser` is redundant here: it would only replace `datetime.strptime` for a
handful of absolute-date formats we already parse directly.

---

## 5. Recommendation

### Parse to structured recurrence, expand to explicit occurrences

1. **Parse the `PromoEvent-time` text with a hand-rolled grammar** (the five
   templates in §2) into `{freq, interval, byday, until, time_blocks[]}`.
   WFIU's text is **templated by Brightspot, not free English**, so the grammar
   is tiny and stable — the right place for a small, well-tested parser rather
   than a dormant NLP dependency.
2. **Expand with `dateutil.rrule`** (already in the environment at
   `2.9.0.post0`). Use `rrulestr(rrule, dtstart=<card start>)` and
   `between(dtstart, horizon_end)`.
3. **Emit one VEVENT per occurrence**, each with its own UID, exactly like the
   existing per-occurrence scrapers. This sidesteps two real constraints:
   - `BaseScraper.create_event()` (`scrapers/lib/base.py:101`) has **no RRULE
     support**, and
   - an RRULE carries a single DTSTART/time, so a WFIU weekly series with
     **different times per weekday** cannot be expressed as one RRULE. It would
     require one RRULE per distinct time block, which is more machinery than
     expanding in the scraper.
   (The pipeline *can* expand RRULEs — `combine_ics.expand_rrules()` uses
   `recurring_ical_events` over a 90-day window — so emitting RRULEs is a valid
   alternative, but it needs base-class changes and per-block rules.)
4. Bound expansion by the Horizon (`scrapers/lib/horizon.py`); skip series that
   start after it.

### Do not add `recurrent`

It is dormant, its license metadata contradicts itself, and it needs a
WFIU-specific `through`→`until` rewrite before it works. Reinventing one small
parser is cheaper and testable. If the team wants a fallback for irregular
future text, `recurrent` can be an *optional, non-default* path — but never let
its un-normalized output reach an unbounded RRULE.

### Concrete fallback for unparseable series

- **Single unexpanded event at the card's next occurrence.** Every card has a
  concrete date (`PromoEvent-date-date`, e.g. `Sep 18 Friday`) and a time block,
  so a card is never lost:
  - parse: one VEVENT, `DTSTART = <card date> + first start time`,
    `DTEND = first end time`; no recurrence.
  - log `WARNING` with the raw string for later triage.
- If the recurrence clause parses but the **expansion is empty** (DTSTART
  anchoring, past `UNTIL`, etc.), apply the same single-event fallback rather
  than dropping the card.
- For **monthly-on-a-weekday**, prefer the conservative interpretation
  (expand `BYDAY=<day>` within the bound) and log the ambiguity; do not silently
  produce an over-broad unbounded rule.

### How to detect unparseable input

1. `parse_wfiu(raw).kind == "unknown"` — no template matched.
2. The resulting RRULE fails `rrulestr(...)` or expands to **zero**
   occurrences within `[dtstart, until]`.
3. A recurrence clause with **no parseable end bound** (`through <date>`) is
   treated as unparseable/single-event rather than expanded unbounded.

All three are cheap, deterministic checks and are exactly what the harness in
`scripts/research/wfiu_recurrence_eval.py` exercises.

### Tests to carry into implementation

- Reuse the corpus as a pytest fixture: every `recurring:` line must parse to a
  non-empty expansion with an `UNTIL` ≤ its through-date; every `one-off:` line
  must yield exactly one occurrence; the `synthetic:` lines guard the
  date-only/multi-day/N-monthly branches.
- Keep monthly-on-weekday as an explicit xfail/expected-ambiguity test until
  the Brightspot semantics are confirmed against a real card.

---

## 6. Risks and open questions

- **Monthly semantics** (`every month on <Weekday>`) cannot be resolved from the
  text alone. Confirm against a known event's observed occurrence dates.
- **The `through` bug is silent.** If someone later wires `recurrent` in
  without the rewrite, they get an unbounded recurring event with a wrong
  `BYMONTH`/`BYMONTHDAY`. The hand-rolled approach removes that failure mode.
- **No timezone in WFIU data** (#131/#130) is orthogonal to recurrence: times
  are local (America/Indiana/Indianapolis); set TZID as the existing scrapers
  do via `BaseScraper.timezone`.
- **Sampling bias:** the sample is the first 28 of 77 listing pages
  (Sep 18–Oct 20, 2026). Date-only/all-day and multi-day were not observed;
  their synthetic forms are best-effort and should be re-checked against a real
  card before relying on them.

## Files

- Corpus: [`docs/fixtures/wfiu-recurrence-corpus.txt`](fixtures/wfiu-recurrence-corpus.txt)
- Evaluation harness: [`scripts/research/wfiu_recurrence_eval.py`](../scripts/research/wfiu_recurrence_eval.py)
- Corpus fetcher: [`scripts/research/wfiu_fetch_corpus.py`](../scripts/research/wfiu_fetch_corpus.py)
