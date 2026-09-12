"""
WebNovel Scraper — FanFiction.net Scraper Implementation

Target site: FanFiction.net (https://www.fanfiction.net)
Key: fanfiction
Access: Free

Features:
  • Direct HTML parsing fallback
  • Automated FicHub API integration to reliably bypass Cloudflare Turnstile
  • Exact publishing formatting preservation (italics, bolding, scene breaks, blockquotes)
  • Direct story URL / ID search resolution
"""
from __future__ import annotations

import io
import logging
import re
import zipfile
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from scraper.base import BaseScraper, ChapterInfo, NovelDetails, NovelSearchResult

logger = logging.getLogger(__name__)


class FanFictionScraper(BaseScraper):
    """Scraper implementation for FanFiction.net with automated FicHub fallback."""

    site_name: str = "fanfiction"
    base_url: str = "https://www.fanfiction.net"

    # Cache for FicHub story metadata and downloaded story EPUBs during batch chapter fetching
    _fichub_cache: dict[str, dict] = {}
    _epub_cache: dict[str, zipfile.ZipFile] = {}

    supported_genres: list[str] = [
        "Fan-Fiction", "Action", "Adventure", "Angst", "Comedy",
        "Crime", "Drama", "Family", "Fantasy", "Friendship",
        "Horror", "Hurt/Comfort", "Mystery", "Parody", "Romance",
        "Science Fiction", "Supernatural", "Suspense", "Tragedy",
        "Western", "Crossover",
    ]

    def _extract_story_id(self, text: str) -> str:
        m = re.search(r"/s/(\d+)|(?:^|\s)(\d{4,10})(?:$|\s)", text.strip())
        if m:
            return m.group(1) or m.group(2)
        return ""

    def _fetch_fichub(self, story_url_or_id: str) -> dict | None:
        """Query the community FicHub API to resolve story metadata and content (cached)."""
        target_url = story_url_or_id.strip()
        story_id = self._extract_story_id(target_url)
        if story_id and story_id in self._fichub_cache:
            return self._fichub_cache[story_id]

        if re.match(r"^\d+$", target_url):
            target_url = f"{self.base_url}/s/{target_url}/1/"
        elif target_url.startswith("/s/"):
            target_url = f"{self.base_url}{target_url}"

        try:
            api_url = f"https://fichub.net/api/v0/epub?q={target_url}"
            resp = requests.get(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("meta"):
                    if story_id:
                        self._fichub_cache[story_id] = data
                    return data
        except Exception as exc:
            logger.debug("FicHub API lookup failed for %s: %s", target_url, exc)
        return None

    def _get_fichub_zip(self, epub_rel_url: str) -> zipfile.ZipFile | None:
        """Download or retrieve cached FicHub EPUB zip archive."""
        if epub_rel_url in self._epub_cache:
            return self._epub_cache[epub_rel_url]

        try:
            full_url = f"https://fichub.net{epub_rel_url}" if epub_rel_url.startswith("/") else epub_rel_url
            resp = requests.get(full_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            if resp.status_code == 200:
                zf = zipfile.ZipFile(io.BytesIO(resp.content))
                self._epub_cache[epub_rel_url] = zf
                return zf
        except Exception as exc:
            logger.warning("Failed to download FicHub EPUB archive: %s", exc)
        return None

    # ── Custom HTTP Fetching ──────────────────
    def _soup(self, url: str) -> BeautifulSoup:
        headers = {
            "Referer": "https://www.fanfiction.net/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = self.client.get(url, headers=headers)
        if resp.status_code == 403:
            raise ConnectionError(f"Cloudflare protection (HTTP 403) from FanFiction.net for {url}")
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    # ── Search ────────────────────────────────
    def search(self, query: str, page: int = 1) -> list[NovelSearchResult]:
        q = (query or "").strip()
        if not q:
            return []

        # 1. If query is a FanFiction story URL or ID, resolve via FicHub directly
        story_id_match = re.search(r"/s/(\d+)|(?:^|\s)(\d{4,10})(?:$|\s)", q)
        if story_id_match:
            sid = story_id_match.group(1) or story_id_match.group(2)
            fichub_data = self._fetch_fichub(sid)
            if fichub_data:
                meta = fichub_data.get("meta", {})
                title = meta.get("title") or f"Story {sid}"
                author = meta.get("author") or "Unknown"
                synopsis = meta.get("description") or ""
                cover_url = meta.get("coverUrl") or ""
                chapter_count = meta.get("chapters", 1)
                genres = meta.get("genres") or ["Fan-Fiction"]
                status = "Completed" if meta.get("status") == "complete" else "Ongoing"
                story_url = f"{self.base_url}/s/{sid}/1/"

                return [NovelSearchResult(
                    title=title,
                    url=story_url,
                    author=author,
                    cover_url=cover_url,
                    synopsis=synopsis,
                    source_site="fanfiction",
                    genres=genres,
                    chapter_count=chapter_count,
                    status=status,
                )]

        # 2. Try direct site search
        params: dict[str, str | int] = {"keywords": q, "type": "story"}
        if page > 1:
            params["ppage"] = page

        search_url = f"{self.base_url}/search/?{urlencode(params)}"
        try:
            soup = self._soup(search_url)
            items = soup.select("div.z-list")
            results = []
            for item in items:
                title_el = item.select_one("a.stitle, a[href*='/s/']")
                if not title_el:
                    continue
                title = self._clean_text(title_el)
                raw_url = title_el.get("href", "").strip()
                url = self._abs_url(self.base_url, raw_url)
                author_el = item.select_one("a[href^='/u/']")
                author = self._clean_text(author_el) if author_el else "Unknown"
                desc_el = item.select_one("div.z-indent")
                synopsis = self._clean_text(desc_el) if desc_el else ""

                results.append(NovelSearchResult(
                    title=title,
                    url=url,
                    author=author,
                    synopsis=synopsis,
                    source_site="fanfiction",
                ))
            if results:
                return results
        except Exception as exc:
            logger.debug("Direct FanFiction search blocked: %s", exc)

        return []

    # ── Novel Details ─────────────────────────
    def get_novel_details(self, url: str) -> NovelDetails:
        # 1. Try FicHub first (bypasses Cloudflare automatically)
        fichub_data = self._fetch_fichub(url)
        if fichub_data:
            meta = fichub_data.get("meta", {})
            title = meta.get("title") or "Unknown Title"
            author = meta.get("author") or "Unknown"
            synopsis = meta.get("description") or ""
            cover_url = meta.get("coverUrl") or ""
            chapter_count = meta.get("chapters", 1)
            status = "Completed" if meta.get("status") == "complete" else "Ongoing"
            genres = meta.get("genres") or ["Fan-Fiction"]

            return NovelDetails(
                title=title,
                url=url,
                author=author,
                cover_url=cover_url,
                synopsis=synopsis,
                source_site="fanfiction",
                genres=genres,
                chapter_count=chapter_count,
                status=status,
            )

        # 2. Fallback to direct HTML parsing
        soup = self._soup(url)
        profile = soup.select_one("div#profile_top")
        title_el = profile.select_one("b.xcontrast_txt") if profile else None
        title = self._clean_text(title_el) if title_el else "Unknown Title"

        author_el = profile.select_one("a[href^='/u/']") if profile else None
        author = self._clean_text(author_el) if author_el else "Unknown"

        synopsis_el = profile.select_one("div.xcontrast_txt") if profile else None
        synopsis = self._clean_text(synopsis_el) if synopsis_el else ""

        options = soup.select("select#chap_select option")
        chapter_count = len(options) if options else 1

        return NovelDetails(
            title=title,
            url=url,
            author=author,
            synopsis=synopsis,
            source_site="fanfiction",
            genres=["Fan-Fiction"],
            chapter_count=chapter_count,
            status="Ongoing",
        )

    # ── Chapter List ──────────────────────────
    def get_chapter_list(self, url: str) -> list[ChapterInfo]:
        story_id_match = re.search(r"/s/(\d+)", url)
        story_id = story_id_match.group(1) if story_id_match else ""

        # 1. Try FicHub chapter count
        fichub_data = self._fetch_fichub(url)
        if fichub_data:
            meta = fichub_data.get("meta", {})
            ch_count = meta.get("chapters", 1)
            chapters = []
            for i in range(1, ch_count + 1):
                ch_url = f"{self.base_url}/s/{story_id}/{i}/" if story_id else f"{url}#{i}"
                chapters.append(ChapterInfo(
                    chapter_number=i,
                    title=f"Chapter {i}",
                    url=ch_url,
                ))
            return chapters

        # 2. Fallback to direct HTML TOC
        soup = self._soup(url)
        options = soup.select("select#chap_select option")
        chapters = []
        if options:
            for idx, opt in enumerate(options, 1):
                raw_title = self._clean_text(opt)
                ch_title = re.sub(r"^\d+[\.\-\s:]+", "", raw_title).strip() or f"Chapter {idx}"
                ch_url = f"{self.base_url}/s/{story_id}/{idx}/" if story_id else url
                chapters.append(ChapterInfo(
                    chapter_number=idx,
                    title=ch_title,
                    url=ch_url,
                ))
        else:
            chapters.append(ChapterInfo(chapter_number=1, title="Chapter 1", url=url))

        return chapters

    # ── Chapter Content ───────────────────────
    def get_chapter_content(self, url: str) -> str:
        # Extract chapter number
        m = re.search(r"/s/\d+/(\d+)", url)
        ch_num = int(m.group(1)) if m else 1

        # 1. Try FicHub EPUB chapter extraction (rich formatting preserved)
        fichub_data = self._fetch_fichub(url)
        if fichub_data and fichub_data.get("epub_url"):
            epub_rel = fichub_data["epub_url"]
            zf = self._get_fichub_zip(epub_rel)
            if zf:
                candidate_names = [
                    f"EPUB/chap_{ch_num}.xhtml",
                    f"chap_{ch_num}.xhtml",
                    f"OEBPS/chapter_{ch_num}.xhtml",
                    f"chapter_{ch_num}.xhtml",
                ]
                for name in candidate_names:
                    if name in zf.namelist():
                        raw_xhtml = zf.read(name).decode("utf-8", errors="replace")
                        soup = BeautifulSoup(raw_xhtml, "html.parser")
                        body = soup.body if soup.body else soup
                        # Clean while preserving italics, bold, dividers, etc.
                        return self._clean_html(body)

        # 2. Direct scraping fallback
        soup = self._soup(url)
        content_el = soup.select_one("div#storytext.storytextp, div#storytext, div.storytextp")
        if content_el:
            return self._clean_html(content_el)

        raise ValueError(f"Could not retrieve chapter content for {url}")
