#!/usr/bin/env python3
"""Toronto Public Library school-age events."""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

from lib.tpl_audiences import TPL_SCHOOL_AGE, TorontoPublicLibraryAudienceScraper


class TorontoPublicLibrarySchoolAgeScraper(TorontoPublicLibraryAudienceScraper):
    name = "Toronto Public Library — School Age"
    target_audience_id = TPL_SCHOOL_AGE


if __name__ == "__main__":
    TorontoPublicLibrarySchoolAgeScraper.main()
