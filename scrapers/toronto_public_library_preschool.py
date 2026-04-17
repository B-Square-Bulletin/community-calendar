#!/usr/bin/env python3
"""Toronto Public Library preschool events."""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

from lib.tpl_audiences import TPL_PRESCHOOL, TorontoPublicLibraryAudienceScraper


class TorontoPublicLibraryPreschoolScraper(TorontoPublicLibraryAudienceScraper):
    name = "Toronto Public Library — Preschool"
    target_audience_id = TPL_PRESCHOOL


if __name__ == "__main__":
    TorontoPublicLibraryPreschoolScraper.main()
