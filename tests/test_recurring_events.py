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

from scripts.combine_ics import expand_rrules
from tests.helpers import make_ics, make_vevent, VTIMEZONE_NY


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
        A recurring 3rd-Tuesday event has its June 16 instance edited to June 23.
        The expanded output should contain June 23, NOT June 16.
        """
        # Master event: monthly on 3rd Tuesday starting May 19, 2026
        # June 16 = 3rd Tuesday → edited to June 23
        master_event = make_vevent(
            "BPTC Board Meeting",
            "DTSTART;TZID=America/New_York:20260519T173000",
            "DTEND;TZID=America/New_York:20260519T193000",
            "test-recurrence-edit@google.com",
            rrule="FREQ=MONTHLY;BYDAY=3TU",
        )
        # Override: RECURRENCE-ID points to June 16, DTSTART is June 23
        override_event = (
            "BEGIN:VEVENT\r\n"
            "DTSTART;TZID=America/New_York:20260623T173000\r\n"
            "DTEND;TZID=America/New_York:20260623T193000\r\n"
            "UID:test-recurrence-edit@google.com\r\n"
            "RECURRENCE-ID;TZID=America/New_York:20260616T173000\r\n"
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
        assert expanded is not None, (
            "expand_rrules should not return None with RRULE present"
        )
        assert len(expanded) > 0, "Should have expanded events"

        # Collect DTSTART dates and UIDs
        dtstarts = []
        uids = []
        for block in expanded:
            m = re.search(r"DTSTART[^:]*:(\d{8})", block)
            if m:
                dtstarts.append(m.group(1))
            uid_m = re.search(r"UID:([^\r\n]+)", block)
            if uid_m:
                uids.append(uid_m.group(1))

        # Original June 16 MUST NOT appear
        assert "20260616" not in dtstarts, (
            f"June 16 should be suppressed by RECURRENCE-ID override, "
            f"but found in expanded output: {dtstarts}"
        )

        # Edited June 23 MUST appear
        assert "20260623" in dtstarts, (
            f"June 23 (the edited instance) should appear, but not found in: {dtstarts}"
        )

        # Other recurring instances should still appear
        assert "20260721" in dtstarts, "July 21 (3rd Tuesday) should still appear"
        assert "20260818" in dtstarts, "August 18 (3rd Tuesday) should still appear"

        # UIDs should have date suffixes (from _serialize_vevent mutation)
        for uid in uids:
            assert "__" in uid, f"Expanded instance UID should have date suffix: {uid}"

        # June 23 event should have the correct suffixed UID
        june23_uids = [
            u
            for b, u in zip(expanded, uids)
            if "20260623" in (re.search(r"DTSTART[^:]*:(\d{8})", b) or [""])[0]
        ]
        if june23_uids:
            assert "__20260623" in june23_uids[0], (
                f"June 23 UID should end with __20260623, got: {june23_uids[0]}"
            )

    def test_no_override_preserves_all_instances(self):
        """
        A recurring event with NO RECURRENCE-ID override should expand
        all instances normally. Baseline / negative control.

        Uses near-future dates so expansion window (today + 120 days)
        covers all COUNT=N instances.
        """
        from datetime import date, timedelta

        start = date.today() + timedelta(days=7)  # one week from now
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
        from datetime import date, timedelta

        start = date.today() + timedelta(days=7)  # one week from now
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
        assert override_1_dt in dtstarts, (
            f"Rescheduled from day 3 ({override_1_dt}) should appear"
        )
        assert override_2_dt in dtstarts, (
            f"Rescheduled from day 7 ({override_2_dt}) should appear"
        )

        # Unmodified days should still appear
        assert start_str in dtstarts, f"Day 1 ({start_str}, unmodified) should appear"
        day_2 = (start + timedelta(days=1)).strftime("%Y%m%d")
        assert day_2 in dtstarts, f"Day 2 ({day_2}, unmodified) should appear"
        day_4 = (start + timedelta(days=3)).strftime("%Y%m%d")
        assert day_4 in dtstarts, f"Day 4 ({day_4}, unmodified) should appear"
