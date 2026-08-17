#!/usr/bin/env python3
"""
Tests for recurring event expansion in the ICS pipeline.

Covers scenarios where a single instance of a recurring series is edited
to a new date (RECURRENCE-ID override). Verifies that the original date
is suppressed and the new date appears, even when the master event has
no EXDATE (Google Calendar pattern).

Run: python -m pytest tests/test_recurring_events.py -v
"""

import re
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scrapers.lib.timeutil import utc_today
from scripts.combine_ics import expand_rrules
from tests.helpers import VTIMEZONE_NY, make_ics, make_vevent


class TestRecurrenceIdOverride:
    """
    When a recurring event instance is edited (date changed via RECURRENCE-ID),
    the original date must be suppressed in the expanded output.

    Google Calendar ICS for a moved recurring instance uses a RECURRENCE-ID
    override with a different DTSTART but NO EXDATE on the master event.
    The recurring_ical_events library must suppress the original occurrence.

    See: https://github.com/B-Square-Bulletin/community-calendar/issues/28
    Root cause: delete_stale_events RPC timed out due to != ALL() on 3500+
    source_uids. Fixed by rewriting as NOT EXISTS (unnest) in migration
    supabase/migrations/20260615000000_fix_delete_stale_events_perf.sql
    """

    def test_edited_instance_replaces_original(self):
        """
        A recurring 3rd-Tuesday event has one instance edited to a later date.
        The expanded output should contain the new date, NOT the original.
        Uses relative dates so the test doesn't expire as time passes.
        """
        from datetime import date, timedelta

        today = utc_today()

        def nth_weekday(year, month, n, weekday):
            """Return the nth weekday (0=Mon, 1=Tue, ...) of a given month."""
            first = date(year, month, 1)
            days = (weekday - first.weekday()) % 7
            return first + timedelta(days=days + 7 * (n - 1))

        # Start series on 3rd Tuesday of previous month (always in the past)
        prev_m = today.month - 1
        prev_y = today.year
        if prev_m == 0:
            prev_m, prev_y = 12, today.year - 1
        start_date = nth_weekday(prev_y, prev_m, 3, 1)

        # Compute 3rd Tuesdays for this month + next 3 months
        occurrences = []
        for i in range(4):
            m = today.month + i
            y = today.year
            if m > 12:
                m -= 12
                y += 1
            occurrences.append(nth_weekday(y, m, 3, 1))

        # Filter to dates in the expansion window (today to today+90 days)
        in_window = [d for d in occurrences if d >= today]
        assert len(in_window) >= 3, (
            f"Need at least 3 occurrences in expansion window, got {len(in_window)}"
        )

        override_original = in_window[0]
        override_new = override_original + timedelta(days=7)

        start_str = start_date.strftime("%Y%m%d")
        override_orig_str = override_original.strftime("%Y%m%d")
        override_new_str = override_new.strftime("%Y%m%d")

        master_event = make_vevent(
            "BPTC Board Meeting",
            f"DTSTART;TZID=America/New_York:{start_str}T173000",
            f"DTEND;TZID=America/New_York:{start_str}T193000",
            "test-recurrence-edit@google.com",
            rrule="FREQ=MONTHLY;BYDAY=3TU",
        )
        # Override: RECURRENCE-ID points to original date, DTSTART is new date
        override_event = (
            "BEGIN:VEVENT\r\n"
            f"DTSTART;TZID=America/New_York:{override_new_str}T173000\r\n"
            f"DTEND;TZID=America/New_York:{override_new_str}T193000\r\n"
            "UID:test-recurrence-edit@google.com\r\n"
            f"RECURRENCE-ID;TZID=America/New_York:{override_orig_str}T173000\r\n"
            "SUMMARY:BPTC Board Meeting (Edited)\r\n"
            "SEQUENCE:2\r\n"
            "STATUS:CONFIRMED\r\n"
            "END:VEVENT\r\n"
        )
        ics = make_ics(
            master_event + override_event,
            tz_header="X-WR-TIMEZONE:America/New_York",
            vtimezone=VTIMEZONE_NY,
        )

        expanded = expand_rrules(ics, window_days=90)
        assert expanded is not None, "expand_rrules should not return None with RRULE present"
        assert len(expanded) > 0, "Should have expanded events"

        # Collect DTSTART dates and UIDs
        dtstarts = []
        uids = []
        for block in expanded:
            dt_match = re.search(r"DTSTART[^:]*:(\d{8})", block)
            if dt_match:
                dtstarts.append(dt_match.group(1))
            uid_match = re.search(r"UID:([^\r\n]+)", block)
            if uid_match:
                uids.append(uid_match.group(1))

        # The overridden original date MUST NOT appear
        assert override_orig_str not in dtstarts, (
            f"{override_original} should be suppressed by RECURRENCE-ID override, "
            f"but found in expanded output: {dtstarts}"
        )

        # The new (edited) date MUST appear
        assert override_new_str in dtstarts, (
            f"{override_new} (the edited instance) should appear, but not found in: {dtstarts}"
        )

        # Later unmodified occurrences should still appear
        for later_dt in in_window[1:3]:
            later_str = later_dt.strftime("%Y%m%d")
            assert later_str in dtstarts, f"{later_dt} (unmodified) should still appear"

        # UIDs should have date suffixes (from _serialize_vevent mutation)
        for uid in uids:
            assert "__" in uid, f"Expanded instance UID should have date suffix: {uid}"

        # The override event should have the correct suffixed UID
        override_uids = [
            u
            for b, u in zip(expanded, uids, strict=False)
            if override_new_str in (re.search(r"DTSTART[^:]*:(\d{8})", b) or [""])[0]
        ]
        if override_uids:
            assert f"__{override_new_str}" in override_uids[0], (
                f"Override UID should end with __{override_new_str}, got: {override_uids[0]}"
            )

    def test_no_override_preserves_all_instances(self):
        """
        A recurring event with NO RECURRENCE-ID override should expand
        all instances normally. Baseline / negative control.

        Uses near-future dates so expansion window (today + 120 days)
        covers all COUNT=N instances.
        """
        from datetime import timedelta

        start = utc_today() + timedelta(days=7)  # one week from now
        start_str = start.strftime("%Y%m%d")
        dtstart = f"DTSTART:{start_str}T090000"
        dtend = f"DTEND:{start_str}T100000"

        event = make_vevent(
            "Weekly Standup",
            dtstart,
            dtend,
            "weekly@test",
            rrule="FREQ=WEEKLY;COUNT=4",
        )
        ics = make_ics(event)
        expanded = expand_rrules(ics, window_days=120)
        assert expanded is not None
        assert len(expanded) == 4, f"Expected 4 weekly instances, got {len(expanded)}"

        # All UIDs should have date suffixes
        for block in expanded:
            m = re.search(r"UID:([^\r\n]+)", block)
            assert m and "__" in m.group(1)

    def test_multiple_overrides(self):
        """
        Multiple RECURRENCE-ID overrides in the same series should all
        be handled correctly. Overridden instances should be replaced,
        non-overridden instances should remain.
        """
        from datetime import timedelta

        start = utc_today() + timedelta(days=7)  # one week from now
        start_str = start.strftime("%Y%m%d")

        master = make_vevent(
            "Daily Class",
            f"DTSTART;TZID=America/New_York:{start_str}T100000",
            f"DTEND;TZID=America/New_York:{start_str}T110000",
            "multi-override@test",
            rrule="FREQ=DAILY;COUNT=10",
        )

        # Override day 3 → move to start+2 days after the series ends
        override_1_dt = (start + timedelta(days=12)).strftime("%Y%m%d")
        override_1 = (
            "BEGIN:VEVENT\r\n"
            f"DTSTART;TZID=America/New_York:{override_1_dt}T100000\r\n"
            f"DTEND;TZID=America/New_York:{override_1_dt}T110000\r\n"
            "UID:multi-override@test\r\n"
            f"RECURRENCE-ID;TZID=America/New_York:{(start + timedelta(days=2)).strftime('%Y%m%d')}T100000\r\n"
            "SUMMARY:Daily Class (Rescheduled)\r\n"
            "END:VEVENT\r\n"
        )

        # Override day 7 → move to start+3 days after the series ends
        override_2_dt = (start + timedelta(days=13)).strftime("%Y%m%d")
        override_2 = (
            "BEGIN:VEVENT\r\n"
            f"DTSTART;TZID=America/New_York:{override_2_dt}T100000\r\n"
            f"DTEND;TZID=America/New_York:{override_2_dt}T110000\r\n"
            "UID:multi-override@test\r\n"
            f"RECURRENCE-ID;TZID=America/New_York:{(start + timedelta(days=6)).strftime('%Y%m%d')}T100000\r\n"
            "SUMMARY:Daily Class (Rescheduled)\r\n"
            "END:VEVENT\r\n"
        )

        ics = make_ics(
            master + override_1 + override_2,
            tz_header="X-WR-TIMEZONE:America/New_York",
            vtimezone=VTIMEZONE_NY,
        )

        expanded = expand_rrules(ics, window_days=120)
        assert expanded is not None
        # 8 unmodified + 2 rescheduled = 10 total (original day 3 and day 7 suppressed)
        assert len(expanded) == 10, f"Expected 10 events, got {len(expanded)}"

        # Collect dates
        dtstarts = []
        for block in expanded:
            m = re.search(r"DTSTART[^:]*:(\d{8})", block)
            if m:
                dtstarts.append(m.group(1))

        # Original overridden days should NOT appear
        suppressed_3 = (start + timedelta(days=2)).strftime("%Y%m%d")
        suppressed_7 = (start + timedelta(days=6)).strftime("%Y%m%d")
        assert suppressed_3 not in dtstarts, (
            f"Day 3 ({suppressed_3}, overridden) should be suppressed"
        )
        assert suppressed_7 not in dtstarts, (
            f"Day 7 ({suppressed_7}, overridden) should be suppressed"
        )

        # Rescheduled days SHOULD appear
        assert override_1_dt in dtstarts, f"Rescheduled from day 3 ({override_1_dt}) should appear"
        assert override_2_dt in dtstarts, f"Rescheduled from day 7 ({override_2_dt}) should appear"

        # Unmodified days should still appear
        assert start_str in dtstarts, f"Day 1 ({start_str}, unmodified) should appear"
        day_2 = (start + timedelta(days=1)).strftime("%Y%m%d")
        assert day_2 in dtstarts, f"Day 2 ({day_2}, unmodified) should appear"
        day_4 = (start + timedelta(days=3)).strftime("%Y%m%d")
        assert day_4 in dtstarts, f"Day 4 ({day_4}, unmodified) should appear"
