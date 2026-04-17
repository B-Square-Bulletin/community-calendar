#!/usr/bin/env python3
"""Scraper for City of Toronto public consultations on Have Your Say."""

from lib.social_pinpoint import SocialPinpointScraper


class TorontoPublicConsultationsScraper(SocialPinpointScraper):
    name = "City of Toronto Public Consultations"
    domain = "haveyoursay.toronto.ca"
    timezone = "America/Toronto"
    page_url = "https://haveyoursay.toronto.ca/events"
    default_url = page_url


if __name__ == "__main__":
    TorontoPublicConsultationsScraper.main()
