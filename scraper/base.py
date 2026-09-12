"""
WebNovel Scraper — Abstract Base Scraper

Every site-specific scraper must subclass ``BaseScraper`` and implement
the four abstract methods:  ``search``, ``get_novel_details``,
``get_chapter_list``, ``get_chapter_content``.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup, Tag

from utils.http import ResilientClient


# ──────────────────────────────────────────────
# Data transfer objects
# ──────────────────────────────────────────────
@dataclass
class NovelSearchResult:
    """Lightweight result returned from a search query."""
    title: str
    url: str
    author: str = "Unknown"
    cover_url: str = ""
    synopsis: str = ""
    source_site: str = ""
    genres: list[str] = field(default_factory=list)
    chapter_count: int = 0
    rating: float = 0.0
    status: str = "Unknown"


@dataclass
class NovelDetails:
    """Full metadata for a single novel."""
    title: str
    url: str
    author: str = "Unknown"
    cover_url: str = ""
    synopsis: str = ""
    source_site: str = ""
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    chapter_count: int = 0
    rating: float = 0.0
    status: str = "Unknown"


@dataclass
class ChapterInfo:
    """One entry in a novel's table of contents."""
    chapter_number: int
    title: str
    url: str


# ──────────────────────────────────────────────
# Base class
# ──────────────────────────────────────────────
class BaseScraper(ABC):
    """Abstract base for all site-specific scrapers."""

    # Subclasses MUST set these
    site_name: str = ""
    base_url: str = ""
    supported_genres: list[str] = []

    def __init__(self, client: Optional[ResilientClient] = None) -> None:
        self.client = client or ResilientClient()

    # ── Abstract interface ────────────────────
    @abstractmethod
    def search(self, query: str, page: int = 1) -> list[NovelSearchResult]:
        """Search the site for novels matching *query*."""
        ...

    @abstractmethod
    def get_novel_details(self, url: str) -> NovelDetails:
        """Fetch full metadata for the novel at *url*."""
        ...

    @abstractmethod
    def get_chapter_list(self, url: str) -> list[ChapterInfo]:
        """Return an ordered list of chapters for the novel at *url*."""
        ...

    @abstractmethod
    def get_chapter_content(self, url: str) -> str:
        """Fetch the text content of a single chapter at *url*."""
        ...

    # ── Shared helpers ────────────────────────
    def _soup(self, url: str) -> BeautifulSoup:
        """Fetch *url* and return a BeautifulSoup object."""
        resp = self.client.get(url)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    @staticmethod
    def _clean_text(element: Tag | None) -> str:
        """Extract visible text from an HTML element, collapsing whitespace."""
        if element is None:
            return ""
        # Replace <br> and <p> with newlines for readability
        for br in element.find_all(["br", "p"]):
            br.insert_before("\n")
        text = element.get_text(separator="\n")
        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _clean_html(element: Tag | None) -> str:
        """Extract clean, safe HTML preserving original publishing formatting
        (italics, bold, scene dividers, blockquotes, code/stat blocks).
        """
        if element is None:
            return ""

        from bs4 import BeautifulSoup, Comment

        soup = BeautifulSoup(str(element), "lxml")

        # Decompose unwanted elements
        for bad in soup.find_all([
            "script", "style", "iframe", "object", "embed", "applet",
            "nav", "aside", "footer", "header", "form", "button", "input", "noscript"
        ]):
            bad.decompose()

        # Remove comments
        for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
            comment.extract()

        ALLOWED_TAGS = {
            "p", "br", "hr",
            "em", "i", "strong", "b", "u", "s", "strike", "del", "sub", "sup",
            "blockquote", "q", "cite",
            "pre", "code", "samp", "kbd",
            "h1", "h2", "h3", "h4", "h5", "h6",
            "ul", "ol", "li", "dl", "dt", "dd",
            "table", "thead", "tbody", "tfoot", "tr", "th", "td",
            "span", "div",
        }

        # Unwrap non-allowed tags while keeping their children
        for tag in list(soup.find_all(True)):
            if tag.name not in ALLOWED_TAGS:
                tag.unwrap()
            else:
                style = tag.get("style", "")
                tag.attrs = {}
                if style and ("center" in style or "right" in style or "justify" in style):
                    if "center" in style:
                        tag["style"] = "text-align: center;"
                    elif "right" in style:
                        tag["style"] = "text-align: right;"

        body = soup.body if soup.body else soup
        if not body.find_all(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"]):
            raw_text = str(body)
            paragraphs = [p.strip() for p in raw_text.split("\n") if p.strip()]
            return "\n".join(f"<p>{p}</p>" for p in paragraphs)

        cleaned_html = "".join(str(c) for c in body.contents).strip()
        cleaned_html = re.sub(r"\n\s*\n+", "\n", cleaned_html)
        return cleaned_html

    @staticmethod
    def _abs_url(base: str, path: str) -> str:
        """Resolve a possibly-relative *path* against *base*."""
        if path.startswith(("http://", "https://")):
            return path
        from urllib.parse import urljoin
        return urljoin(base, path)
