"""
WebNovel Scraper — Royal Road Scraper Implementation

Target site: Royal Road (https://www.royalroad.com)
Key: royalroad
Access: Free
Primary genres: LitRPG, Progression Fantasy, Science Fiction, Fantasy
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

from bs4 import Tag

from scraper.base import BaseScraper, ChapterInfo, NovelDetails, NovelSearchResult

logger = logging.getLogger(__name__)


class RoyalRoadScraper(BaseScraper):
    """Scraper implementation for Royal Road (royalroad.com)."""

    site_name: str = "royalroad"
    base_url: str = "https://www.royalroad.com"
    supported_genres: list[str] = [
        "LitRPG",
        "Progression Fantasy",
        "Science Fiction",
        "Fantasy",
        "Action",
        "Adventure",
        "Comedy",
        "Contemporary",
        "Drama",
        "Historical",
        "Horror",
        "Mystery",
        "Psychological",
        "Romance",
        "Satire",
        "Short Story",
        "Tragedy",
        "Cultivation",
        "Fan-Fiction",
        "Isekai",
        "Supernatural",
        "Martial Arts",
    ]

    # Known status badge texts mapped to normalized strings
    _STATUS_MAP: dict[str, str] = {
        "COMPLETED": "Completed",
        "ONGOING": "Ongoing",
        "HIATUS": "Hiatus",
        "STUB": "Stub",
        "INACTIVE": "Inactive",
        "DROPPED": "Dropped",
    }

    # Known anti-piracy / watermark regex patterns injected by Royal Road
    _WATERMARK_PATTERNS: list[re.Pattern] = [
        re.compile(r"Unauthorized tale usage", re.IGNORECASE),
        re.compile(r"Unauthorized reproduction", re.IGNORECASE),
        re.compile(r"stolen from Royal Road", re.IGNORECASE),
        re.compile(r"taken without permission.*report", re.IGNORECASE),
        re.compile(r"unlawfully lifted without the author", re.IGNORECASE),
        re.compile(r"purloined without the author", re.IGNORECASE),
        re.compile(r"unlawfully obtained without the author", re.IGNORECASE),
        re.compile(
            r"if you (?:spot|see|find|are reading) this (?:story|tale|narrative|content|novel) on Amazon",
            re.IGNORECASE,
        ),
    ]

    # ──────────────────────────────────────────
    # Search
    # ──────────────────────────────────────────
    def search(self, query: str, page: int = 1) -> list[NovelSearchResult]:
        """Search Royal Road for novels matching *query*."""
        query_str = query.strip()
        if not query_str:
            return []

        search_url = f"{self.base_url}/fictions/search?title={quote_plus(query_str)}&page={page}"
        logger.debug("Searching Royal Road: %s (page %d)", query_str, page)

        try:
            soup = self._soup(search_url)
        except Exception as exc:
            logger.error("Failed to fetch search results for '%s' (page %d): %s", query_str, page, exc)
            return []

        items = soup.select("div.fiction-list-item")
        results: list[NovelSearchResult] = []

        for item in items:
            title_el = item.select_one("h2.fiction-title a, .fiction-title a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href = title_el.get("href", "").strip()
            if not href:
                continue
            novel_url = self._abs_url(self.base_url, href)

            # Author (often not in search card, fallback to Unknown)
            author_el = item.select_one(".author a, a[href*='/profile/'], .author, span.author")
            author = author_el.get_text(strip=True) if author_el else "Unknown"

            # Cover image
            cover_url = ""
            img_el = item.select_one("figure img, img[data-type='cover'], img")
            if img_el:
                raw_img = img_el.get("src") or img_el.get("data-src") or ""
                if raw_img and "nocover" not in raw_img:
                    cover_url = self._abs_url(self.base_url, raw_img)

            # Synopsis (hidden or visible in card)
            desc_el = item.select_one("div[id^='description-'], .fiction-description, .description")
            synopsis = self._clean_text(desc_el) if desc_el else ""

            # Tags / Genres
            genres: list[str] = []
            for tag_el in item.select("span.tags a.fiction-tag, a.fiction-tag, .tags a"):
                t = tag_el.get_text(strip=True)
                if t and t not in genres:
                    genres.append(t)

            # Status (COMPLETED, ONGOING, HIATUS, STUB, etc.)
            status = "Unknown"
            for label in item.select(".margin-bottom-10 span.label, span.label"):
                text_val = label.get_text(strip=True).upper()
                if text_val in self._STATUS_MAP:
                    status = self._STATUS_MAP[text_val]
                    break

            # Chapter count
            chapter_count = 0
            stats_text = item.select_one("div.stats")
            stats_str = stats_text.get_text() if stats_text else item.get_text()
            m_ch = re.search(r"([\d,]+)\s*Chapters?", stats_str, re.IGNORECASE)
            if m_ch:
                try:
                    chapter_count = int(m_ch.group(1).replace(",", ""))
                except ValueError:
                    pass

            # Rating
            rating = 0.0
            rating_el = item.select_one(
                ".stats [aria-label*='Rating'], "
                "span.star[title], "
                "[aria-label*='Rating'], "
                ".stats .star"
            )
            if rating_el:
                content = rating_el.get("aria-label") or rating_el.get("title") or ""
                m_r = re.search(r"(\d+(?:\.\d+)?)", content)
                if m_r:
                    try:
                        rating = float(m_r.group(1))
                    except ValueError:
                        pass

            results.append(
                NovelSearchResult(
                    title=title,
                    url=novel_url,
                    author=author,
                    cover_url=cover_url,
                    synopsis=synopsis,
                    source_site=self.site_name,
                    genres=genres,
                    chapter_count=chapter_count,
                    rating=rating,
                    status=status,
                )
            )

        return results

    # ──────────────────────────────────────────
    # Novel Details
    # ──────────────────────────────────────────
    def get_novel_details(self, url: str) -> NovelDetails:
        """Fetch full metadata for the Royal Road novel at *url*."""
        logger.debug("Fetching novel details from Royal Road: %s", url)
        soup = self._soup(url)

        # Title
        title_el = soup.select_one("div.fic-title h1, .fic-title h1, h1.font-white, h1")
        title = title_el.get_text(strip=True) if title_el else "Untitled"

        # Author
        author_el = soup.select_one(
            "div.fic-title h4 a, "
            ".fic-title h4 a, "
            "div.mt-card-content a[href*='/profile/'], "
            "a[href*='/profile/']"
        )
        author = author_el.get_text(strip=True) if author_el else "Unknown"
        if author == "Unknown":
            h4 = soup.select_one("div.fic-title h4")
            if h4:
                h4_text = h4.get_text(strip=True)
                if "by" in h4_text.lower():
                    parts = re.split(r"\bby\b", h4_text, flags=re.IGNORECASE)
                    if len(parts) > 1 and parts[-1].strip():
                        author = parts[-1].strip()

        # Cover image
        cover_url = ""
        img_el = soup.select_one(
            "div.cover-art-container img, "
            "div.fic-header img[data-type='cover'], "
            "img[data-type='cover'], "
            ".fic-header img, "
            "img.thumbnail"
        )
        if img_el:
            raw_img = img_el.get("src") or img_el.get("data-src") or ""
            if raw_img and "nocover" not in raw_img:
                cover_url = self._abs_url(self.base_url, raw_img)

        # Synopsis
        desc_el = soup.select_one("div.description div.hidden-content, div.description")
        synopsis = self._clean_text(desc_el) if desc_el else ""

        # Status
        status = "Unknown"
        for label in soup.select("div.fiction-info span.label, span.label"):
            text_val = label.get_text(strip=True).upper()
            if text_val in self._STATUS_MAP:
                status = self._STATUS_MAP[text_val]
                break

        # Tags and Genres
        tags: list[str] = []
        for tag_el in soup.select("span.tags a.fiction-tag, ul.tag-list li a, a.fiction-tag"):
            t = tag_el.get_text(strip=True)
            if t and t not in tags:
                tags.append(t)

        genres: list[str] = []
        # Badges like "Original" or "Fan Fiction"
        for badge in soup.select("div.fiction-info span.label, .fic-header span.label"):
            bt = badge.get_text(strip=True)
            if bt.upper() in ("ORIGINAL", "FAN FICTION", "FANFICTION"):
                if bt not in genres:
                    genres.append(bt)

        for t in tags:
            if t not in genres:
                genres.append(t)

        # Rating
        rating = 0.0
        rating_el = soup.select_one(
            "span.star[title='Overall Score'], "
            ".fiction-stats span[data-content*='/ 5'], "
            "span[data-content*='/ 5'], "
            "span[aria-label*='stars'], "
            ".fiction-stats span[data-content]"
        )
        if rating_el:
            raw = rating_el.get("data-content") or rating_el.get("aria-label") or rating_el.get("title") or ""
            m_r = re.search(r"(\d+(?:\.\d+)?)", raw)
            if m_r:
                try:
                    rating = float(m_r.group(1))
                except ValueError:
                    pass

        if rating == 0.0:
            star_count = soup.select_one("div.star-count, span.star-count")
            if star_count:
                m_r = re.search(r"(\d+(?:\.\d+)?)", star_count.get_text())
                if m_r:
                    try:
                        rating = float(m_r.group(1))
                    except ValueError:
                        pass

        # Chapter count
        chapter_count = 0
        table = soup.select_one("table#chapters")
        if table and table.get("data-chapters"):
            try:
                chapter_count = int(table["data-chapters"])
            except ValueError:
                pass

        if chapter_count == 0:
            ch_rows = soup.select("table#chapters tbody tr.chapter-row, table#chapters tbody tr")
            if ch_rows:
                # Filter out header rows if any
                chapter_count = sum(1 for r in ch_rows if not r.select_one("th"))

        if chapter_count == 0:
            m_ch = re.search(r"([\d,]+)\s*Chapters?", soup.get_text(), re.IGNORECASE)
            if m_ch:
                try:
                    chapter_count = int(m_ch.group(1).replace(",", ""))
                except ValueError:
                    pass

        return NovelDetails(
            title=title,
            url=url,
            author=author,
            cover_url=cover_url,
            synopsis=synopsis,
            source_site=self.site_name,
            genres=genres,
            tags=tags,
            chapter_count=chapter_count,
            rating=rating,
            status=status,
        )

    # ──────────────────────────────────────────
    # Chapter List
    # ──────────────────────────────────────────
    def get_chapter_list(self, url: str) -> list[ChapterInfo]:
        """Return an ordered list of chapters for the Royal Road novel at *url*."""
        logger.debug("Fetching chapter list from Royal Road: %s", url)
        soup = self._soup(url)

        rows = soup.select("table#chapters tbody tr")
        if not rows:
            rows = soup.select("table#chapters tr")

        chapters: list[ChapterInfo] = []
        ch_num = 1

        for row in rows:
            # Skip header rows containing <th>
            if row.select_one("th"):
                continue

            link = row.select_one("td:first-child a, a[href*='/chapter/']")
            if not link:
                # Some rows store the chapter URL in data-url attribute
                data_url = row.get("data-url", "").strip()
                if data_url and "/chapter/" in data_url:
                    href = data_url
                    first_td = row.select_one("td")
                    title = first_td.get_text(strip=True) if first_td else f"Chapter {ch_num}"
                else:
                    # Skip volume header rows or non-chapter rows
                    continue
            else:
                href = link.get("href", "").strip()
                title = link.get_text(strip=True)

            if not href:
                continue

            title = re.sub(r"\s+", " ", title).strip() or f"Chapter {ch_num}"
            ch_url = self._abs_url(self.base_url, href)

            chapters.append(
                ChapterInfo(
                    chapter_number=ch_num,
                    title=title,
                    url=ch_url,
                )
            )
            ch_num += 1

        return chapters

    # ──────────────────────────────────────────
    # Chapter Content
    # ──────────────────────────────────────────
    def get_chapter_content(self, url: str) -> str:
        """Fetch and clean the text content of a single chapter at *url*."""
        logger.debug("Fetching chapter content from Royal Road: %s", url)
        soup = self._soup(url)

        content_div = soup.select_one(
            "div.chapter-inner.chapter-content, "
            "div.chapter-content, "
            "div.chapter-inner"
        )
        if content_div is None:
            logger.warning("Chapter content container not found at %s", url)
            return ""

        # 1. Remove anti-piracy hidden elements via CSS detection
        # Royal Road injects hidden spans whose class is styled with 'display: none' in <style> blocks
        hidden_classes: set[str] = set()
        for style_tag in soup.find_all("style"):
            css_text = style_tag.string or style_tag.get_text()
            if not css_text:
                continue
            for m in re.finditer(r"\.([a-zA-Z0-9_-]+)\s*\{[^}]*display\s*:\s*none", css_text, re.IGNORECASE):
                hidden_classes.add(m.group(1))

        for cls in hidden_classes:
            for hidden_el in content_div.find_all(class_=cls):
                hidden_el.decompose()

        # 2. Remove any elements with inline display:none
        for hidden_el in content_div.find_all(style=re.compile(r"display\s*:\s*none", re.IGNORECASE)):
            hidden_el.decompose()

        # 3. Remove elements matching known anti-piracy watermark text
        for pattern in self._WATERMARK_PATTERNS:
            for node in content_div.find_all(string=pattern):
                parent = node.parent
                if parent and isinstance(parent, Tag) and parent != content_div:
                    parent.decompose()
                else:
                    node.extract()

        # 4. Remove non-content tags (scripts, styles, ads, author-note portlets)
        for tag in content_div.find_all(["script", "style", "iframe", "noscript"]):
            tag.decompose()
        for ad in content_div.select(".portlet, .ad, .advertisement, .ac"):
            ad.decompose()

        # 5. Extract clean formatted HTML preserving original publishing formatting
        return self._clean_html(content_div)
