#!/usr/bin/env python3
"""Tests for the shared geo-filter matcher (#127).

The combine-time filter and the scrape-time prefilter both call
`load_allowed_cities` + `location_matches_allowed_cities`, so these tests pin
the one definition they share. The bug: an in-area address that carries a ZIP
but no town name (common for US addresses) was dropped.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scrapers"))

from lib.city_filter import load_allowed_cities, location_matches_allowed_cities

BLOOMINGTON_DIR = Path(__file__).parent.parent / "cities" / "bloomington"


def _load(input_dir):
    allowed, excluded, allowed_zips = load_allowed_cities(str(input_dir))
    return allowed, excluded, allowed_zips


def test_bloomington_zip_only_address_is_in_area():
    allowed, excluded, allowed_zips = _load(BLOOMINGTON_DIR)
    assert location_matches_allowed_cities(
        "Sleeper's Bar, 2601 N Walnut St, IN 47404", allowed, excluded, allowed_zips
    )


def test_stinesville_zip_only_address_is_in_area():
    allowed, excluded, allowed_zips = _load(BLOOMINGTON_DIR)
    assert location_matches_allowed_cities(
        "McGlocklin Park, Market Street, IN 47464", allowed, excluded, allowed_zips
    )


def test_out_of_area_zip_is_dropped():
    allowed, excluded, allowed_zips = _load(BLOOMINGTON_DIR)
    assert not location_matches_allowed_cities(
        "Indiana Convention Center, 100 S Capitol Ave, Indianapolis, IN 46204",
        allowed,
        excluded,
        allowed_zips,
    )


def test_venue_only_location_passes_through():
    allowed, excluded, allowed_zips = _load(BLOOMINGTON_DIR)
    assert location_matches_allowed_cities("The Bluebird", allowed, excluded, allowed_zips)


def test_town_name_still_matches():
    allowed, excluded, allowed_zips = _load(BLOOMINGTON_DIR)
    assert location_matches_allowed_cities(
        "Brown County Music Center, 114 E Gould St, Nashville, IN", allowed, excluded, allowed_zips
    )
