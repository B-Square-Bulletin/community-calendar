#!/usr/bin/env python3
"""Scraper for TDSB public eScribe meetings calendar."""

from lib.escribe import EScribeScraper


class TDSBMeetingsScraper(EScribeScraper):
    name = "Toronto District School Board Meetings"
    domain = "pub-tdsb.escribemeetings.com"
    timezone = "America/Toronto"
    root_url = "https://pub-tdsb.escribemeetings.com/"
    endpoint_url = root_url + "MeetingsCalendarView.aspx/GetCalendarMeetings"
    default_url = root_url + "MeetingsCalendarView.aspx"


if __name__ == "__main__":
    TDSBMeetingsScraper.main()
