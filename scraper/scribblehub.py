"""
WebNovel Scraper — Scribble Hub Scraper

Scrapes novels from Scribble Hub (https://www.scribblehub.com).
Specializes in original/independent web novels, niche fantasy, romance, LitRPG,
and fan fiction.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup, Tag

from scraper.base import BaseScraper, ChapterInfo, NovelDetails, NovelSearchResult

logger = logging.getLogger(__name__)


class ScribbleHubScraper(BaseScraper):
    """Scraper implementation for Scribble Hub (https://www.scribblehub.com)."""

    site_name: str = "scribblehub"
    base_url: str = "https://www.scribblehub.com"
    supported_genres: list[str] = [
        "Action",
        "Adult",
        "Adventure",
        "Boys Love",
        "Comedy",
        "Drama",
        "Ecchi",
        "Fanfiction",
        "Fantasy",
        "Gender Bender",
        "Girls Love",
        "Harem",
        "Historical",
        "Horror",
        "Isekai",
        "Josei",
        "LitRPG",
        "Martial Arts",
        "Mature",
        "Mecha",
        "Mystery",
        "Psychological",
        "Romance",
        "School Life",
        "Sci-fi",
        "Seinen",
        "Shoujo",
        "Shounen",
        "Slice of Life",
        "Smut",
        "Sports",
        "Supernatural",
        "Tragedy",
    ]

    # ──────────────────────────────────────────
    # 1. Search
    # ──────────────────────────────────────────
    def search(self, query: str, page: int = 1) -> list[NovelSearchResult]:
        """Search Scribble Hub for novels matching *query*."""
        query_str = (query or "").strip()
        if not query_str:
            return []

        page_num = max(1, page)
        encoded_query = quote_plus(query_str)
        if page_num > 1:
            url = f"{self.base_url}/?s={encoded_query}&post_type=fict&paged={page_num}"
        else:
            url = f"{self.base_url}/?s={encoded_query}&post_type=fict"

        logger.debug("Searching Scribble Hub: %s", url)
        try:
            soup = self._soup(url)
        except Exception as exc:
            logger.warning("Scribble Hub search blocked or failed: %s", exc)
            return []

        results: list[NovelSearchResult] = []

        boxes = soup.select("div.search_main_box")
        for box in boxes:
            try:
                # Title and URL: div.search_title a
                title_elem = box.select_one("div.search_title a, h2 a, a.search_title")
                if not title_elem:
                    continue
                title = self._clean_text(title_elem)
                href = title_elem.get("href", "")
                if not href:
                    continue
                novel_url = self._abs_url(self.base_url, href)

                # Author: span.search_author a or profile link or auth_name_fic
                author_elem = box.select_one(
                    "span.search_author a, div.search_author a, a[href*='/profile/'], "
                    "span.auth_name_fic a, span.auth_name_fic"
                )
                author = self._clean_text(author_elem) if author_elem else "Unknown"

                # Cover: div.search_img img
                img_elem = box.select_one("div.search_img img, img")
                cover_url = ""
                if img_elem:
                    raw_cover = (
                        img_elem.get("data-src")
                        or img_elem.get("src")
                        or img_elem.get("data-original")
                        or ""
                    )
                    if raw_cover.startswith("data:") and img_elem.get("data-src"):
                        raw_cover = img_elem["data-src"]
                    if raw_cover:
                        cover_url = self._abs_url(self.base_url, raw_cover)

                # Synopsis / summary
                desc_elem = box.select_one(
                    "div.search_body, div.search_desc, div.synopsis, div.search_text"
                )
                synopsis = self._clean_text(desc_elem) if desc_elem else ""

                # Genres: div.search_genre span
                genre_elems = box.select("div.search_genre span, div.search_genre a")
                genres = [
                    self._clean_text(g)
                    for g in genre_elems
                    if self._clean_text(g)
                ]

                # Stats: div.search_stats (chapters, views, rating, status)
                stats_elem = box.select_one("div.search_stats")
                stats_text = stats_elem.get_text(" ", strip=True) if stats_elem else ""

                chapter_count = self._parse_chapter_count(stats_text)
                rating = self._parse_rating(stats_elem, stats_text)
                status = self._parse_status(stats_text)

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
            except Exception as exc:
                logger.warning("Error parsing search result box on Scribble Hub: %s", exc)
                continue

        return results

    # ──────────────────────────────────────────
    # 2. Novel Details
    # ──────────────────────────────────────────
    def get_novel_details(self, url: str) -> NovelDetails:
        """Fetch full metadata for the novel at *url*."""
        logger.debug("Fetching novel details: %s", url)
        soup = self._soup(url)

        # Title: div.fic_title
        title_elem = soup.select_one("div.fic_title, h1.fic_title, h1")
        title = self._clean_text(title_elem) if title_elem else ""
        if not title:
            # Fallback to page title tag
            page_title = soup.find("title")
            title = page_title.get_text(strip=True) if page_title else "Untitled"
            title = re.sub(r"\s*[-|]\s*Scribble\s*Hub.*$", "", title, flags=re.IGNORECASE)

        # Author: span.auth_name_fic
        auth_elem = soup.select_one("span.auth_name_fic a, span.auth_name_fic, .auth_name_fic")
        author = self._clean_text(auth_elem) if auth_elem else "Unknown"

        # Synopsis: div.wi_fic_desc
        desc_elem = soup.select_one("div.wi_fic_desc, div.fic_description, div.synopsis")
        synopsis = self._clean_text(desc_elem) if desc_elem else ""

        # Cover: div.fic_image img
        cover_elem = soup.select_one("div.fic_image img, .fic_image img, img.fic_image")
        cover_url = ""
        if cover_elem:
            raw_cover = (
                cover_elem.get("data-src")
                or cover_elem.get("src")
                or cover_elem.get("data-original")
                or ""
            )
            if raw_cover.startswith("data:") and cover_elem.get("data-src"):
                raw_cover = cover_elem["data-src"]
            if raw_cover:
                cover_url = self._abs_url(self.base_url, raw_cover)

        # Genres: ul.genre_tags li a
        genre_elems = soup.select(
            "ul.genre_tags li a, a.fic_genre, span.wi_fic_genre a, .genre_tags a"
        )
        genres: list[str] = []
        for g in genre_elems:
            name = self._clean_text(g)
            if name and name not in genres:
                genres.append(name)

        # Tags: ul.stag_tags li a, div.wi_fic_show_tags a
        tag_elems = soup.select(
            "ul.stag_tags li a, div.wi_fic_show_tags a, a.stag_tag, ul.tags li a, .stag_tags a"
        )
        tags: list[str] = []
        for t in tag_elems:
            name = self._clean_text(t)
            if name and name not in tags:
                tags.append(name)

        # Stats: div.fic_stats (rating, chapters, status)
        stats_elem = soup.select_one("div.fic_stats, .fic_stats")
        stats_text = stats_elem.get_text(" ", strip=True) if stats_elem else ""

        chapter_count = self._parse_chapter_count(stats_text)

        # Rating: check itemprop="ratingValue", span#rate_fic, or stats text
        rating = 0.0
        itemprop_elem = soup.select_one("[itemprop='ratingValue']")
        if itemprop_elem:
            val_str = itemprop_elem.get("content") or itemprop_elem.get_text(strip=True)
            try:
                rating = float(val_str)
            except ValueError:
                rating = 0.0
        if rating == 0.0:
            rating = self._parse_rating(stats_elem, stats_text)

        # Status: span.att_completed, etc.
        status = "Unknown"
        status_elem = soup.select_one(
            "span.att_completed, span.completed, span.ongoing, span.hiatus, .fic_status"
        )
        if status_elem:
            st = status_elem.get_text(strip=True).capitalize()
            if st in ("Completed", "Ongoing", "Hiatus"):
                status = st
        if status == "Unknown":
            status = self._parse_status(stats_text)

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
    # 3. Chapter List
    # ──────────────────────────────────────────
    def get_chapter_list(self, url: str) -> list[ChapterInfo]:
        """Return an ordered list of chapters for the novel at *url*."""
        logger.debug("Fetching chapter list: %s", url)
        soup = self._soup(url)

        raw_chapters: list[tuple[str, str]] = []
        seen_urls: set[str] = set()

        # Extract chapters on the initial page: div.toc_list with ol li a
        self._extract_chapters_from_soup(soup, raw_chapters, seen_urls)

        # Handle TOC pagination if present
        post_id = self._extract_post_id(soup, url)
        max_page = self._extract_toc_max_page(soup)

        if post_id and max_page > 1:
            logger.debug(
                "Scribble Hub novel has %d TOC pages for post_id %s",
                max_page,
                post_id,
            )
            for p in range(2, max_page + 1):
                try:
                    page_html = self._fetch_toc_page(post_id, p, referer=url)
                    page_soup = BeautifulSoup(page_html, "lxml")
                    self._extract_chapters_from_soup(page_soup, raw_chapters, seen_urls)
                except Exception as exc:
                    logger.warning(
                        "Failed to fetch TOC page %d for post %s: %s",
                        p,
                        post_id,
                        exc,
                    )
                    break

        if not raw_chapters:
            logger.warning("No chapters found for Scribble Hub novel at %s", url)
            return []

        # Detect order: if newest-first (descending), reverse to chronological order
        if self._is_descending(raw_chapters):
            logger.debug("Reversing descending TOC to chronological order")
            raw_chapters.reverse()

        # Assign 1-indexed sequential chapter numbers
        chapter_list: list[ChapterInfo] = []
        for idx, (ch_title, ch_url) in enumerate(raw_chapters, start=1):
            title = ch_title or f"Chapter {idx}"
            chapter_list.append(
                ChapterInfo(
                    chapter_number=idx,
                    title=title,
                    url=ch_url,
                )
            )

        return chapter_list

    # ──────────────────────────────────────────
    # 4. Chapter Content
    # ──────────────────────────────────────────
    def get_chapter_content(self, url: str) -> str:
        """Fetch the text content of a single chapter at *url*."""
        logger.debug("Fetching chapter content: %s", url)
        soup = self._soup(url)

        # Chapter page: div#chp_raw
        content_elem = soup.select_one("div#chp_raw")
        if not content_elem:
            content_elem = soup.select_one(
                "div.chp_raw, div#chp_contents, div.chapter-content, div.entry-content, div.chapter_content"
            )

        if not content_elem:
            raise ValueError(f"Could not find chapter content element at {url}")

        # Decompose scripts, styles, ads, and widgets
        for unwanted in content_elem.select(
            "script, style, .code-block, .ads, .ad, .advertisement, .share-buttons, .chp_ad"
        ):
            unwanted.decompose()

        return self._clean_html(content_elem)

    # ──────────────────────────────────────────
    # Helper methods
    # ──────────────────────────────────────────
    def _extract_chapters_from_soup(
        self,
        soup: BeautifulSoup,
        raw_chapters: list[tuple[str, str]],
        seen_urls: set[str],
    ) -> None:
        """Extract (title, url) tuples from a TOC soup into raw_chapters."""
        # Primary selector from instructions: div.toc_list with ol li a
        links = soup.select("div.toc_list ol li a, div.toc_list li.toc_w a, ol.toc_ol li a")
        if not links:
            # Fallback selectors
            links = soup.select("div.toc_list li a, div.toc_list a[href*='/read/'], li.toc_w a")

        for a in links:
            href = a.get("href", "").strip()
            if not href or href == "#":
                continue
            abs_url = self._abs_url(self.base_url, href)
            if abs_url in seen_urls:
                continue
            seen_urls.add(abs_url)
            title = self._clean_text(a)
            raw_chapters.append((title, abs_url))

    def _extract_post_id(self, soup: BeautifulSoup, url: str) -> str:
        """Find the WordPress post ID for the series."""
        post_elem = soup.select_one("input#mypostid, input[name='mypostid']")
        if post_elem and post_elem.get("value"):
            return post_elem["value"].strip()

        # URL format: /series/{id}/{slug}/
        m = re.search(r"/series/(\d+)", url)
        if m:
            return m.group(1)
        return ""

    def _extract_toc_max_page(self, soup: BeautifulSoup) -> int:
        """Find the highest TOC page number from pagination links if present."""
        page_elems = soup.select(
            "div.toc_pagination a.page-numbers, div.toc_pagination a, div.wi_fic_pagination a, .toc_page"
        )
        max_page = 1
        for elem in page_elems:
            txt = elem.get_text(strip=True)
            if txt.isdigit():
                max_page = max(max_page, int(txt))
            href = elem.get("href", "")
            m = re.search(r"paged=(\d+)", href)
            if m:
                max_page = max(max_page, int(m.group(1)))
        return max_page

    def _fetch_toc_page(self, post_id: str, page_num: int, referer: str) -> str:
        """Fetch a paginated TOC slice via Scribble Hub's AJAX endpoint."""
        ajax_url = f"{self.base_url}/wp-admin/admin-ajax.php"
        headers = {
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
        }
        data = {
            "action": "wi_getreleases_pagination",
            "pagenum": str(page_num),
            "mypostid": str(post_id),
        }
        resp = self.client.post(ajax_url, data=data, headers=headers)
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def _is_descending(chapters: list[tuple[str, str]]) -> bool:
        """Determine if raw chapters are ordered newest-first (descending)."""
        if len(chapters) < 2:
            return False

        def _get_ch_num(text: str) -> float | None:
            m = re.search(r"(?:chapter|ch\.?)\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
            if m:
                return float(m.group(1))
            m = re.search(r"^(\d+(?:\.\d+)?)\b", text.strip())
            if m:
                return float(m.group(1))
            return None

        first_nums = [_get_ch_num(c[0]) for c in chapters[:5]]
        first_nums = [n for n in first_nums if n is not None]

        last_nums = [_get_ch_num(c[0]) for c in chapters[-5:]]
        last_nums = [n for n in last_nums if n is not None]

        if first_nums and last_nums:
            avg_first = sum(first_nums) / len(first_nums)
            avg_last = sum(last_nums) / len(last_nums)
            return avg_first > avg_last

        return False

    @staticmethod
    def _parse_rating(elem: Tag | None, text: str) -> float:
        """Extract rating (0.00 - 5.00) from star elements or text."""
        if elem:
            star_elem = elem.select_one("i.fa-star, .fa-star, span#rate_fic, .rate_star")
            if star_elem and star_elem.parent:
                star_text = star_elem.parent.get_text(strip=True)
                m = re.search(r"(\d+(?:\.\d+)?)", star_text)
                if m:
                    try:
                        val = float(m.group(1))
                        if 0.0 <= val <= 5.0:
                            return round(val, 2)
                    except ValueError:
                        pass

        if text:
            m = re.search(
                r"(?:Rating|★)\s*[:]?\s*(\d+(?:\.\d+)?)",
                text,
                re.IGNORECASE,
            )
            if m:
                try:
                    val = float(m.group(1))
                    if 0.0 <= val <= 5.0:
                        return round(val, 2)
                except ValueError:
                    pass

        return 0.0

    @staticmethod
    def _parse_chapter_count(text: str) -> int:
        """Extract chapter count from stats text."""
        if not text:
            return 0
        m = re.search(r"([\d,]+)\s*(?:Chapters?|Chs?|Ch\b)", text, re.IGNORECASE)
        if not m:
            m = re.search(r"Chapters?\s*[:\n]?\s*([\d,]+)", text, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                pass
        return 0

    @staticmethod
    def _parse_status(text: str) -> str:
        """Extract novel release status (Completed, Hiatus, Ongoing, Unknown)."""
        if not text:
            return "Unknown"
        lower = text.lower()
        if "completed" in lower:
            return "Completed"
        if "hiatus" in lower:
            return "Hiatus"
        if "ongoing" in lower:
            return "Ongoing"
        return "Unknown"
