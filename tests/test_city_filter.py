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

from lib.city_filter import (
    load_allowed_cities,
    location_matches_allowed_cities,
    parse_zips_directive,
)

BLOOMINGTON_DIR = Path(__file__).parent.parent / "cities" / "bloomington"


def _in_area(location):
    allowed, excluded, allowed_zips = load_allowed_cities(str(BLOOMINGTON_DIR))
    return location_matches_allowed_cities(location, allowed, excluded, allowed_zips)


def test_bloomington_zip_only_address_is_in_area():
    assert _in_area("Sleeper's Bar, 2601 N Walnut St, IN 47404")


def test_stinesville_zip_only_address_is_in_area():
    assert _in_area("McGlocklin Park, Market Street, IN 47464")


def test_out_of_area_zip_is_dropped():
    assert not _in_area("Indiana Convention Center, 100 S Capitol Ave, Indianapolis, IN 46204")


def test_venue_only_location_passes_through():
    assert _in_area("The Bluebird")


def test_town_name_still_matches():
    assert _in_area("Brown County Music Center, 114 E Gould St, Nashville, IN")


def test_zip_before_a_country_suffix_is_matched():
    assert _in_area("Bell Trace, 800 Bell Trace Ct, IN 47408, USA")


def test_zip_before_an_escaped_comma_is_matched():
    # Combine-time locations are still serialized ICS text: commas are "\,".
    assert _in_area(r"Bell Trace\, 800 Bell Trace Ct\, IN 47408\, USA")


def test_five_digit_house_number_is_not_mistaken_for_a_zip():
    # 47404 collides with a Bloomington ZIP but is a house number here.
    allowed = {"bloomington"}
    assert not location_matches_allowed_cities(
        "47404 Main St, Chicago, IL", allowed, allowed_zips={"47404"}
    )


def test_zips_directive_is_case_insensitive():
    assert parse_zips_directive("# ZIPS: 47404, 47464") == {"47404", "47464"}
    assert parse_zips_directive("# a plain comment") is None
