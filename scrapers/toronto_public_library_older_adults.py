#!/usr/bin/env python3
"""Toronto Public Library older-adult events."""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

from lib.tpl_audiences import TPL_OLDER_ADULTS, TorontoPublicLibraryAudienceScraper


class TorontoPublicLibraryOlderAdultsScraper(TorontoPublicLibraryAudienceScraper):
    name = "Toronto Public Library — Older Adults"
    target_audience_id = TPL_OLDER_ADULTS


if __name__ == "__main__":
    TorontoPublicLibraryOlderAdultsScraper.main()
