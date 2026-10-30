"""MVP web scraper: parse local HTML listing pages into JSONL and CSV."""

from web_scraper.pipeline import ScrapeResult, scrape

__all__ = ["ScrapeResult", "scrape"]
