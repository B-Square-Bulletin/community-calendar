#!/usr/bin/env python3
"""Toronto Public Library adult events."""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

from lib.tpl_audiences import TPL_ADULTS, TorontoPublicLibraryAudienceScraper


class TorontoPublicLibraryAdultsScraper(TorontoPublicLibraryAudienceScraper):
    name = "Toronto Public Library — Adults"
    target_audience_id = TPL_ADULTS


if __name__ == "__main__":
    TorontoPublicLibraryAdultsScraper.main()
