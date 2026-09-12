"""
WebNovel Scraper — Resilient HTTP Client

Reliability-first design:
  • Per-domain rate limiting (configurable delay between requests)
  • Exponential backoff with jitter on failures
  • Rotating User-Agent pool
  • Persistent cookies per session
  • Respects 429 Retry-After headers
  • Configurable timeouts and max retries
"""
from __future__ import annotations

import logging
import random
import time
from threading import Lock
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    BACKOFF_BASE,
    BACKOFF_MAX,
    DEFAULT_DELAY,
    DEFAULT_TIMEOUT,
    MAX_RETRIES,
    RETRY_429_FALLBACK,
    SITE_DELAYS,
    USER_AGENTS,
)

logger = logging.getLogger(__name__)


class ResilientClient:
    """Thread-safe HTTP client with per-domain rate limiting, retries,
    and rotating User-Agents.
    """

    def __init__(self) -> None:
        self._session = requests.Session()

        # Mount a retry adapter for transport-level retries
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=20, pool_maxsize=20)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

        # Per-domain timestamps to enforce rate limiting
        self._domain_last_request: dict[str, float] = {}
        self._lock = Lock()

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────
    def get(self, url: str, **kwargs) -> requests.Response:
        """GET with rate-limiting, retry & backoff.  Returns the Response."""
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        """POST with rate-limiting, retry & backoff."""
        return self._request("POST", url, **kwargs)

    @property
    def cookies(self) -> requests.cookies.RequestsCookieJar:
        """Return the current session cookie jar."""
        return self._session.cookies

    @property
    def session(self) -> requests.Session:
        """Return the underlying requests.Session."""
        return self._session

    def close(self) -> None:
        self._session.close()

    # ──────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────
    def _get_domain(self, url: str) -> str:
        return urlparse(url).netloc.lower()

    def _get_delay(self, domain: str) -> float:
        """Return the inter-request delay for *domain*."""
        for site_key, delay in SITE_DELAYS.items():
            if site_key in domain:
                return delay
        return DEFAULT_DELAY

    def _wait_for_rate_limit(self, domain: str) -> None:
        """Block until enough time has elapsed since the last request to *domain*."""
        delay = self._get_delay(domain)
        with self._lock:
            last = self._domain_last_request.get(domain, 0.0)
            elapsed = time.monotonic() - last
            if elapsed < delay:
                wait = delay - elapsed
                # Add a small jitter (0-10 %) to look more human
                wait += wait * random.uniform(0, 0.1)
                time.sleep(wait)
            self._domain_last_request[domain] = time.monotonic()

    def _pick_ua(self) -> str:
        return random.choice(USER_AGENTS)

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        domain = self._get_domain(url)
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", self._pick_ua())
        headers.setdefault("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        headers.setdefault("Accept-Language", "en-US,en;q=0.9")

        last_exc: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            self._wait_for_rate_limit(domain)

            try:
                resp = self._session.request(method, url, headers=headers, **kwargs)

                # Handle 429 Too Many Requests
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait = int(retry_after)
                        except ValueError:
                            wait = RETRY_429_FALLBACK
                    else:
                        wait = RETRY_429_FALLBACK
                    logger.warning(
                        "429 from %s — backing off %ds (attempt %d/%d)",
                        domain, wait, attempt, MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue

                # Treat other 4xx / 5xx as retryable only for server errors
                if resp.status_code >= 500:
                    logger.warning(
                        "Server error %d from %s (attempt %d/%d)",
                        resp.status_code, domain, attempt, MAX_RETRIES,
                    )
                    self._backoff(attempt)
                    continue

                return resp

            except (
                requests.ConnectionError,
                requests.Timeout,
                requests.exceptions.ChunkedEncodingError,
            ) as exc:
                last_exc = exc
                logger.warning(
                    "%s for %s (attempt %d/%d): %s",
                    type(exc).__name__, url, attempt, MAX_RETRIES, exc,
                )
                self._backoff(attempt)

        # All retries exhausted — raise last exception
        raise requests.ConnectionError(
            f"All {MAX_RETRIES} retries exhausted for {url}"
        ) from last_exc

    def _backoff(self, attempt: int) -> None:
        """Exponential backoff with jitter."""
        delay = min(BACKOFF_BASE ** attempt, BACKOFF_MAX)
        jitter = delay * random.uniform(0, 0.3)
        wait = delay + jitter
        logger.debug("Backoff: sleeping %.1fs (attempt %d)", wait, attempt)
        time.sleep(wait)
