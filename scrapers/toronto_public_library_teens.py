#!/usr/bin/env python3
"""Toronto Public Library teen events."""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

from lib.tpl_audiences import TPL_TEENS, TorontoPublicLibraryAudienceScraper


class TorontoPublicLibraryTeensScraper(TorontoPublicLibraryAudienceScraper):
    name = "Toronto Public Library — Teens"
    target_audience_id = TPL_TEENS


if __name__ == "__main__":
    TorontoPublicLibraryTeensScraper.main()
