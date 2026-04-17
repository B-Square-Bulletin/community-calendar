"""Audience-specific Toronto Public Library scraper helpers."""

from .bibliocommons import BibliocommonsEventsScraper


TPL_PRESCHOOL = "67eab59f53f2873000a90aa9"
TPL_SCHOOL_AGE = "6894f7dab7a97e36001ab2b9"
TPL_TEENS = "67eab59153f2873000a90aa8"
TPL_YOUNG_ADULTS = "6894f7ed639e1e9694a55425"
TPL_ADULTS = "67bf594ebd7c6c2800fd3bda"
TPL_OLDER_ADULTS = "6894f7fb639e1e9694a5542a"


# TPL events often carry multiple audience tags. Route each event to exactly one
# audience feed so we don't create duplicate events across six separate sources.
# The order below prefers the more specific audience bucket over the broader one.
TPL_AUDIENCE_PRIORITY = [
    TPL_PRESCHOOL,
    TPL_SCHOOL_AGE,
    TPL_TEENS,
    TPL_YOUNG_ADULTS,
    TPL_OLDER_ADULTS,
    TPL_ADULTS,
]


class TorontoPublicLibraryAudienceScraper(BibliocommonsEventsScraper):
    """Bibliocommons scraper that routes TPL events to one audience feed."""

    domain = "tpl.bibliocommons.com"
    timezone = "America/Toronto"
    library_slug = "tpl"
    page_limit = 100
    max_pages = 80
    target_audience_id: str = ""

    def _matches_filters(self, definition: dict[str, object]) -> bool:
        audience_ids = definition.get("audienceIds") or []
        if not audience_ids or not self.target_audience_id:
            return False

        for audience_id in TPL_AUDIENCE_PRIORITY:
            if audience_id in audience_ids:
                return audience_id == self.target_audience_id

        return False
