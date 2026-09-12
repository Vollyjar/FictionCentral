"""
WebNovel Scraper — Application Configuration
"""
import os
import pathlib

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
APP_NAME = "FictionCentral"
APP_VERSION = "1.1.0"

_default_dir = pathlib.Path.home() / "AppData" / "Local" / "FictionCentral"
_legacy_dir = pathlib.Path.home() / "AppData" / "Local" / "WebNovelScraper"
_fallback_dir = _legacy_dir if (not _default_dir.exists() and _legacy_dir.exists()) else _default_dir

APP_DIR = pathlib.Path(
    os.environ.get("FICTIONCENTRAL_APP_DIR", os.environ.get("WEBNOVEL_APP_DIR", str(_fallback_dir)))
)
APP_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = APP_DIR / "library.db"
COVERS_DIR = APP_DIR / "covers"
COVERS_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────
# HTTP / Crawling
# ──────────────────────────────────────────────
DEFAULT_TIMEOUT = (30, 60)          # (connect, read) in seconds
MAX_RETRIES = 5
BACKOFF_BASE = 2.0                  # seconds
BACKOFF_MAX = 60.0                  # seconds
DEFAULT_DELAY = 0.4                 # seconds between requests to same domain
RETRY_429_FALLBACK = 30             # seconds to wait on 429 without Retry-After

# Per-site delay overrides (seconds). Optimized for speed while avoiding rate limits.
SITE_DELAYS: dict[str, float] = {
    "royalroad.com": 0.35,
    "scribblehub.com": 0.35,
    "novelfire.net": 0.35,
    "inkitt.com": 0.35,
    "tapas.io": 0.5,
    "wattpad.com": 0.5,
    "webnovel.com": 0.6,
    "archiveofourown.org": 0.8,
    "fanfiction.net": 0.5,
    "forums.spacebattles.com": 0.5,
    "forums.sufficientvelocity.com": 0.5,
}

# Rotating User-Agent pool (real desktop browser strings)
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",  # noqa: E501
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",  # noqa: E501
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",  # noqa: E501
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",  # noqa: E501
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",  # noqa: E501
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",  # noqa: E501
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 OPR/111.0.0.0",  # noqa: E501
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",  # noqa: E501
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

# ──────────────────────────────────────────────
# Genres used for recommendations / filtering
# ──────────────────────────────────────────────
PREFERRED_GENRES: list[str] = [
    "Fantasy",
    "Fan-Fiction",
    "Science Fiction",
    "Cultivation",
]

ALL_GENRES: list[str] = [
    "Fantasy",
    "Fan-Fiction",
    "Science Fiction",
    "Cultivation",
    "Romance",
    "LitRPG",
    "Progression Fantasy",
    "Isekai",
    "Xianxia",
    "Xuanhuan",
    "Wuxia",
    "Action",
    "Adventure",
    "Comedy",
    "Drama",
    "Horror",
    "Mystery",
    "Thriller",
    "Slice of Life",
    "Tragedy",
    "Historical",
    "Supernatural",
    "Martial Arts",
    "Mecha",
    "Psychological",
    "School Life",
    "Seinen",
    "Shounen",
    "Josei",
    "Shoujo",
    "Harem",
    "Mature",
]

# ──────────────────────────────────────────────
# GUI
# ──────────────────────────────────────────────
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
APPEARANCE_MODE = "dark"       # "dark", "light", or "system"
COLOR_THEME = "blue"           # CustomTkinter built-in theme
