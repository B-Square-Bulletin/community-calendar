#!/usr/bin/env python3
"""Scraper for TCDSB public eScribe meetings calendar."""

from lib.escribe import EScribeScraper


class TCDSBMeetingsScraper(EScribeScraper):
    name = "Toronto Catholic District School Board Meetings"
    domain = "tcdsbpublishing.escribemeetings.com"
    timezone = "America/Toronto"
    root_url = "https://tcdsbpublishing.escribemeetings.com/"
    endpoint_url = root_url + "MeetingsCalendarView.aspx/GetCalendarMeetings"
    default_url = root_url + "MeetingsCalendarView.aspx"


if __name__ == "__main__":
    TCDSBMeetingsScraper.main()
