#!/usr/bin/env python3
"""Scraper for Toronto planning/development review consultation meetings."""

from lib.social_pinpoint import SocialPinpointScraper


class TorontoPlanningConsultationsScraper(SocialPinpointScraper):
    name = "City Planning Consultations"
    domain = "haveyoursay.toronto.ca"
    timezone = "America/Toronto"
    page_url = "https://haveyoursay.toronto.ca/city-planning-development-review-community-consultations"
    default_url = page_url


if __name__ == "__main__":
    TorontoPlanningConsultationsScraper.main()
