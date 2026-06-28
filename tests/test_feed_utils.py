#!/usr/bin/env python3
"""
Tests for lib/feed_utils.py.

Run: python -m pytest tests/test_feed_utils.py -v
"""

import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

# Add project root and scrapers to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'scrapers'))

from lib.feed_utils import slugify, parse_feeds_txt, build_stem_name_map


class TestSlugify:
    """Tests for URL → filename slug generation."""

    def test_meetup(self):
        result = slugify(
            "https://www.meetup.com/bloomington-hikers/events/ical/"
        )
        assert result == "meetup_bloomington_hikers"

    def test_tockify(self):
        result = slugify("https://tockify.com/api/feeds/ics/abc123")
        assert result == "tockify_abc123"

    def test_google_calendar(self):
        result = slugify(
            "https://calendar.google.com/calendar/ical/abc123def%40group.calendar.google.com/public/basic.ics"
        )
        assert result == "gcal_abc123def"

    def test_generic_domain_path(self):
        result = slugify("https://example.com/events/?ical=1")
        assert result.startswith("example")
        assert not result.endswith("_")

    def test_civicplus(self):
        result = slugify(
            "https://www.cityofexample.org/common/modules/iCalendar/"
            "iCalendar.aspx?feed=calendar&catID=22"
        )
        assert result.startswith("civicplus_cityofexample_22")

    def test_libcal(self):
        result = slugify(
            "https://iu.libcal.com/ical?cid=12345"
        )
        assert result == "libcal_iu_12345"

    def test_campuslabs(self):
        result = slugify(
            "https://iu.campuslabs.com/engage/events/ical"
        )
        assert result == "campuslabs_iu"

    def test_livewhale(self):
        result = slugify(
            "https://events.iu.edu/live/ical/events/group_id/56"
        )
        assert "livewhale" in result.lower()

    def test_length_limit(self):
        long_url = (
            "https://very-long-domain-name-that-goes-on.com/"
            + "very-long-path/" * 5
            + "?ical=1"
        )
        result = slugify(long_url)
        assert len(result) <= 50


class TestParseFeedsTxt:
    """Tests for unified feeds.txt parser."""

    def test_ics_feed_with_name(self):
        content = "# Friendly Source Name\nhttps://example.com/events/?ical=1\n"
        feeds_file = _write_temp(content)
        feeds = parse_feeds_txt(feeds_file)

        assert len(feeds) == 1
        f = feeds[0]
        assert f['type'] == 'ics_url'
        assert f['name'] == 'Friendly Source Name'
        assert f['url'] == 'https://example.com/events/?ical=1'
        assert f['basename'] is not None
        assert f['fallback_url'] is None

    def test_ics_feed_with_fallback(self):
        content = (
            "# Friendly Source | https://fallback.example.com/\n"
            "https://example.com/events/?ical=1\n"
        )
        feeds_file = _write_temp(content)
        feeds = parse_feeds_txt(feeds_file)

        assert len(feeds) == 1
        assert feeds[0]['name'] == 'Friendly Source'
        assert feeds[0]['fallback_url'] == 'https://fallback.example.com/'

    def test_ics_feed_no_name(self):
        content = "https://example.com/events/?ical=1\n"
        feeds_file = _write_temp(content)
        feeds = parse_feeds_txt(feeds_file)

        assert len(feeds) == 1
        assert feeds[0]['name'] == 'https://example.com/events/?ical=1'

    def test_scraper_with_cmd(self):
        content = (
            "# cmd: python scrapers/myscraper.py --name \"My Scraper\" "
            "--url \"https://example.com/source\"\n"
            "cities/mycity/myscraper.ics\n"
        )
        feeds_file = _write_temp(content)
        feeds = parse_feeds_txt(feeds_file)

        assert len(feeds) == 1
        f = feeds[0]
        assert f['type'] == 'scraper'
        assert f['name'] == 'My Scraper'
        assert f['basename'] == 'myscraper'
        assert f['scraper_cmd'].startswith('python scrapers/myscraper.py')
        assert f['source_url'] == 'https://example.com/source'

    def test_scraper_with_default_url(self):
        content = (
            "# cmd: python scrapers/myscraper.py "
            "--default-url \"https://example.com/venue\"\n"
            "cities/mycity/myscraper.ics\n"
        )
        feeds_file = _write_temp(content)
        feeds = parse_feeds_txt(feeds_file)

        assert len(feeds) == 1
        assert feeds[0]['source_url'] == 'https://example.com/venue'

    def test_scraper_no_name_in_cmd(self):
        content = (
            "# cmd: python scrapers/simple.py\n"
            "cities/mycity/simple.ics\n"
        )
        feeds_file = _write_temp(content)
        feeds = parse_feeds_txt(feeds_file)

        assert len(feeds) == 1
        assert feeds[0]['name'] == 'Simple'  # titlecased basename
        assert feeds[0]['scraper_cmd'] == 'python scrapers/simple.py'

    def test_scraper_name_via_comment(self):
        content = (
            "# My Custom Scraper\n"
            "# cmd: python scrapers/custom.py\n"
            "cities/mycity/custom.ics\n"
        )
        feeds_file = _write_temp(content)
        feeds = parse_feeds_txt(feeds_file)

        assert len(feeds) == 1
        assert feeds[0]['name'] == 'My Custom Scraper'

    def test_multiple_feeds(self):
        content = (
            "# ICS Feed\n"
            "https://example.com/ical\n"
            "\n"
            "# cmd: python scrapers/mine.py --name \"Mine\"\n"
            "cities/my/mine.ics\n"
        )
        feeds_file = _write_temp(content)
        feeds = parse_feeds_txt(feeds_file)

        assert len(feeds) == 2
        assert feeds[0]['type'] == 'ics_url'
        assert feeds[1]['type'] == 'scraper'

    def test_skips_section_headers(self):
        content = (
            "# --- Section Header ---\n"
            "https://example.com/ical\n"
        )
        feeds_file = _write_temp(content)
        feeds = parse_feeds_txt(feeds_file)

        assert len(feeds) == 1
        assert feeds[0]['type'] == 'ics_url'

    def test_skips_category_labels(self):
        content = (
            "# Scraper\n"
            "https://example.com/ical\n"
        )
        feeds_file = _write_temp(content)
        feeds = parse_feeds_txt(feeds_file)

        assert len(feeds) == 1
        # 'Scraper' category header should be skipped, URL should get
        # the URL as its name since no legitimate metadata was found
        assert feeds[0]['name'] == 'https://example.com/ical'

    def test_empty_file(self):
        feeds = parse_feeds_txt('/nonexistent/feeds.txt')
        assert feeds == []

    def test_basename_computed_for_scraper(self):
        content = (
            "# cmd: python scrapers/buskirk_chumley.py --name \"Buskirk\"\n"
            "cities/bloomington/buskirk_chumley.ics\n"
        )
        feeds_file = _write_temp(content)
        feeds = parse_feeds_txt(feeds_file)

        assert feeds[0]['basename'] == 'buskirk_chumley'

    def test_source_url_null_when_no_url_arg(self):
        content = (
            "# cmd: python scrapers/simple.py --name \"Simple\"\n"
            "cities/my/simple.ics\n"
        )
        feeds_file = _write_temp(content)
        feeds = parse_feeds_txt(feeds_file)

        assert feeds[0]['source_url'] is None


class TestBuildStemNameMap:
    """Tests for stem → name map builder."""

    def test_maps_scraper_stems_to_names(self):
        content = (
            "# cmd: python scrapers/a.py --name \"Scraper A\"\n"
            "cities/my/a.ics\n"
            "# cmd: python scrapers/b.py --name \"Scraper B\"\n"
            "cities/my/b.ics\n"
        )
        feeds_file = _write_temp(content)
        name_map = build_stem_name_map(feeds_file)

        assert name_map == {'a': 'Scraper A', 'b': 'Scraper B'}

    def test_ics_feeds_not_included(self):
        content = (
            "# ICS Feed\nhttps://example.com/ical\n"
            "# cmd: python scrapers/m.py --name \"Scraper\"\n"
            "cities/my/m.ics\n"
        )
        feeds_file = _write_temp(content)
        name_map = build_stem_name_map(feeds_file)

        assert 'example' not in name_map
        assert name_map == {'m': 'Scraper'}


def _write_temp(content: str) -> str:
    """Write content to a named temp file and return its path."""
    f = NamedTemporaryFile(mode='w', suffix='_feeds.txt', delete=False)
    f.write(content)
    f.close()
    return f.name
