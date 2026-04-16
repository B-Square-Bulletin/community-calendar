#!/usr/bin/env python3
"""Toronto Public Library young-adult events."""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

from lib.tpl_audiences import TPL_YOUNG_ADULTS, TorontoPublicLibraryAudienceScraper


class TorontoPublicLibraryYoungAdultsScraper(TorontoPublicLibraryAudienceScraper):
    name = "Toronto Public Library — Young Adults"
    target_audience_id = TPL_YOUNG_ADULTS


if __name__ == "__main__":
    TorontoPublicLibraryYoungAdultsScraper.main()
