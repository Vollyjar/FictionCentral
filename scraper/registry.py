"""
WebNovel Scraper — Scraper Registry

Central registry that maps site keys to scraper instances.
Provides look-up by site key or by URL.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from scraper.base import BaseScraper
from utils.http import ResilientClient

# Lazy singleton
_client: ResilientClient | None = None
_scrapers: dict[str, BaseScraper] | None = None


def _get_client() -> ResilientClient:
    global _client
    if _client is None:
        _client = ResilientClient()
    return _client


def _init_scrapers() -> dict[str, BaseScraper]:
    """Import and instantiate all site scrapers."""
    client = _get_client()

    from scraper.royalroad import RoyalRoadScraper
    from scraper.scribblehub import ScribbleHubScraper
    from scraper.fanfiction import FanFictionScraper
    from scraper.ao3 import AO3Scraper
    from scraper.webnovel import WebnovelScraper
    from scraper.wattpad import WattpadScraper
    from scraper.tapas import TapasScraper
    from scraper.inkitt import InkittScraper
    from scraper.novelfire import NovelfireScraper
    from scraper.spacebattles import SpaceBattlesScraper

    return {
        "royalroad": RoyalRoadScraper(client),
        "scribblehub": ScribbleHubScraper(client),
        "fanfiction": FanFictionScraper(client),
        "ao3": AO3Scraper(client),
        "webnovel": WebnovelScraper(client),
        "wattpad": WattpadScraper(client),
        "tapas": TapasScraper(client),
        "inkitt": InkittScraper(client),
        "novelfire": NovelfireScraper(client),
        "spacebattles": SpaceBattlesScraper(client),
    }


def _ensure_init() -> dict[str, BaseScraper]:
    global _scrapers
    if _scrapers is None:
        _scrapers = _init_scrapers()
    return _scrapers


def get_scraper(site_key: str) -> BaseScraper | None:
    """Return the scraper for *site_key* (e.g. 'royalroad')."""
    return _ensure_init().get(site_key)


def get_all_scrapers() -> list[BaseScraper]:
    """Return all registered scrapers."""
    return list(_ensure_init().values())


# Domain → scraper key mapping for URL-based lookup
_DOMAIN_MAP: dict[str, str] = {
    "royalroad.com": "royalroad",
    "www.royalroad.com": "royalroad",
    "scribblehub.com": "scribblehub",
    "www.scribblehub.com": "scribblehub",
    "fanfiction.net": "fanfiction",
    "www.fanfiction.net": "fanfiction",
    "m.fanfiction.net": "fanfiction",
    "fichub.net": "fanfiction",
    "archiveofourown.org": "ao3",
    "www.archiveofourown.org": "ao3",
    "webnovel.com": "webnovel",
    "www.webnovel.com": "webnovel",
    "m.webnovel.com": "webnovel",
    "wattpad.com": "wattpad",
    "www.wattpad.com": "wattpad",
    "m.wattpad.com": "wattpad",
    "tapas.io": "tapas",
    "www.tapas.io": "tapas",
    "inkitt.com": "inkitt",
    "www.inkitt.com": "inkitt",
    "novelfire.net": "novelfire",
    "www.novelfire.net": "novelfire",
    "spacebattles.com": "spacebattles",
    "www.spacebattles.com": "spacebattles",
    "forums.spacebattles.com": "spacebattles",
    "sufficientvelocity.com": "spacebattles",
    "www.sufficientvelocity.com": "spacebattles",
    "forums.sufficientvelocity.com": "spacebattles",
}


def normalize_novel_url(url: str) -> str:
    """Normalize any direct chapter, mobile, or novel link to canonical novel details URL."""
    clean = (url or "").strip()
    if not clean:
        return ""

    # Digits only -> FanFiction.net story ID
    if clean.isdigit():
        return f"https://www.fanfiction.net/s/{clean}/1/"

    if not clean.startswith(("http://", "https://")):
        clean = "https://" + clean

    # Royal Road: normalize /chapter/ to /fiction/ID
    m = re.search(r"royalroad\.com/fiction/(\d+)", clean, re.IGNORECASE)
    if m:
        return f"https://www.royalroad.com/fiction/{m.group(1)}"

    # AO3: normalize /chapters/ to /works/ID
    m = re.search(r"archiveofourown\.org/works/(\d+)", clean, re.IGNORECASE)
    if m:
        return f"https://archiveofourown.org/works/{m.group(1)}"

    # FanFiction.net: normalize story ID
    m = re.search(r"fanfiction\.net/s/(\d+)", clean, re.IGNORECASE)
    if m:
        return f"https://www.fanfiction.net/s/{m.group(1)}/1/"

    # FicHub URL
    m = re.search(r"fichub\.net/\?q=(https?://[^\s&]+)", clean, re.IGNORECASE)
    if m:
        return m.group(1)

    # Scribble Hub: normalize /read/ or /series/ to /series/ID/novel
    m = re.search(r"scribblehub\.com/(?:series|read)/(\d+)", clean, re.IGNORECASE)
    if m:
        return f"https://www.scribblehub.com/series/{m.group(1)}/novel"

    # Webnovel: normalize /book/ID/chapter to /book/ID
    m = re.search(r"webnovel\.com/book/(?:[^/]*_)?(\d+)", clean, re.IGNORECASE)
    if m:
        return f"https://www.webnovel.com/book/{m.group(1)}"

    # Novelfire: strip /chapter-X
    if "novelfire.net/book/" in clean.lower():
        clean = re.sub(r"/chapter-[^/?#]+.*$", "", clean)

    # SpaceBattles / Sufficient Velocity: normalize thread
    m = re.search(r"((?:forums\.)?(?:spacebattles|sufficientvelocity)\.com/threads/[^/]*\.(\d+))", clean, re.IGNORECASE)
    if m:
        domain = m.group(1).split("/threads/")[0]
        if not domain.startswith("forums."):
            domain = "forums." + domain
        return f"https://{domain}/threads/{m.group(2)}/"

    return clean


def get_scraper_for_url(url: str) -> BaseScraper | None:
    """Identify the correct scraper for a given URL."""
    clean_url = normalize_novel_url(url)
    if not clean_url:
        return None

    domain = urlparse(clean_url).netloc.lower()
    if ":" in domain:
        domain = domain.split(":", 1)[0]

    key = _DOMAIN_MAP.get(domain)
    if key:
        return get_scraper(key)

    for registered_domain, site_key in _DOMAIN_MAP.items():
        if domain.endswith("." + registered_domain):
            return get_scraper(site_key)

    for root_domain, site_key in [
        ("royalroad", "royalroad"),
        ("scribblehub", "scribblehub"),
        ("fanfiction", "fanfiction"),
        ("archiveofourown", "ao3"),
        ("webnovel", "webnovel"),
        ("wattpad", "wattpad"),
        ("tapas", "tapas"),
        ("inkitt", "inkitt"),
        ("novelfire", "novelfire"),
        ("spacebattles", "spacebattles"),
        ("sufficientvelocity", "spacebattles"),
        ("fichub", "fanfiction"),
    ]:
        if root_domain in domain:
            return get_scraper(site_key)

    return None
