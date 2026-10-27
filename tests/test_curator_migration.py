#!/usr/bin/env python3
"""Pins the token extraction in the curator-feed migration.

The migration is destructive, and pgTAP cannot replay it: `supabase test db`
runs psql where the repo's migration path is not readable, so `\\i` fails.
That leaves the constraints covered by pgTAP and the conversion verified by
hand. This test covers the piece that already broke in review — a regex
anchored to the end of the URL, which silently skipped a token followed by
another query parameter and left the row to be retired instead of converted.
"""

import re
from pathlib import Path

MIGRATION = (
    Path(__file__).parent.parent
    / "supabase"
    / "migrations"
    / "20261026120000_curator_feeds_without_public_tokens.sql"
)


def _token_pattern() -> re.Pattern[str]:
    match = re.search(r"from 'token=\((.*?)\)'", MIGRATION.read_text())
    assert match, "migration no longer extracts a token from feeds.url"
    return re.compile(match.group(1))


def test_matches_a_plain_token():
    url = "https://ref.supabase.co/functions/v1/my-picks?token=0d6f3c1a-1111-2222-3333-444444444444"
    assert _token_pattern().search(url)


def test_matches_a_token_followed_by_another_parameter():
    url = (
        "https://ref.supabase.co/functions/v1/my-picks"
        "?token=0d6f3c1a-1111-2222-3333-444444444444&format=json"
    )
    assert _token_pattern().search(url)


def test_matches_uppercase_uuid_hex():
    url = "https://ref.supabase.co/functions/v1/my-picks?token=0D6F3C1A-1111-2222-3333-444444444444"
    assert _token_pattern().search(url)
