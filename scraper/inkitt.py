"""
WebNovel Scraper — Inkitt Scraper

Scrapes free stories from https://www.inkitt.com
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

from scraper.base import BaseScraper, ChapterInfo, NovelDetails, NovelSearchResult

logger = logging.getLogger(__name__)


class InkittScraper(BaseScraper):
    site_name = "inkitt"
    base_url = "https://www.inkitt.com"
    supported_genres = [
        "Fantasy", "Romance", "Science Fiction", "Thriller", "Mystery",
        "Horror", "Action", "Adventure", "Drama", "Comedy",
        "Paranormal", "Fan-Fiction", "Young Adult", "Historical",
    ]

    # ── Search ────────────────────────────────
    def search(self, query: str, page: int = 1) -> list[NovelSearchResult]:
        results: list[NovelSearchResult] = []

        # Use Inkitt's blended search API
        try:
            api_url = f"{self.base_url}/api/2/search/blended?q={quote_plus(query)}"
            resp = self.client.get(api_url)
            if resp.status_code == 200:
                data = resp.json()
                sections = data.get("results", [])
                for sec in sections:
                    if sec.get("type") == "story":
                        for s in sec.get("items", []):
                            story_id = s.get("id")
                            title = s.get("title", "")
                            if not story_id or not title:
                                continue

                            story_url = f"{self.base_url}/stories/{story_id}"
                            synopsis = s.get("teaser", "")
                            cover = s.get("small_cover_url", s.get("cover_url", ""))
                            author = "Unknown"
                            user = s.get("user")
                            if isinstance(user, dict):
                                author = user.get("username") or user.get("name", "Unknown")
                            elif s.get("user_id"):
                                author = f"User {s['user_id']}"

                            status = "Ongoing"
                            if s.get("story_status") == "completed":
                                status = "Completed"

                            results.append(NovelSearchResult(
                                title=title,
                                url=story_url,
                                author=author,
                                cover_url=cover,
                                synopsis=synopsis,
                                source_site="inkitt",
                                status=status,
                            ))
                if results:
                    return results
        except Exception as exc:
            logger.debug("Inkitt blended search API failed: %s", exc)

        return results

    # ── Novel Details ─────────────────────────
    def get_novel_details(self, url: str) -> NovelDetails:
        soup = self._soup(url)

        # Title and Author from <title> or <h1>
        title = ""
        author = "Unknown"
        if soup.title and soup.title.string:
            # Format is typically "Title by Author at Inkitt"
            t_text = soup.title.string.strip()
            m = re.search(r"^(.*?)\s+by\s+(.*?)\s+at\s+Inkitt", t_text, re.I)
            if m:
                title = m.group(1).strip()
                author = m.group(2).strip()

        if not title:
            h1 = soup.select_one("h1")
            title = h1.get_text(strip=True) if h1 else "Untitled"

        # Synopsis
        desc_el = soup.select_one("div.story-teaser, div.description, p.teaser, div.summary")
        synopsis = self._clean_text(desc_el) if desc_el else ""
        if not synopsis:
            og = soup.find("meta", property="og:description")
            synopsis = og["content"] if og else ""

        # Cover
        cover = ""
        og_img = soup.find("meta", property="og:image")
        if og_img:
            cover = og_img.get("content", "")

        # Chapter list
        chapters = self.get_chapter_list(url)

        return NovelDetails(
            title=title,
            url=url,
            author=author,
            cover_url=cover,
            synopsis=synopsis,
            source_site="inkitt",
            chapter_count=len(chapters),
            genres=["Fantasy", "Romance"],
            status="Ongoing",
        )

    # ── Chapter List ──────────────────────────
    def get_chapter_list(self, url: str) -> list[ChapterInfo]:
        soup = self._soup(url)
        chapters: list[ChapterInfo] = []
        seen: set[str] = set()

        # Story links like /stories/535205/chapters/1
        ch_links = soup.select("a[href*='/chapters/']")
        for a in ch_links:
            href = a.get("href", "")
            ch_url = self._abs_url(self.base_url, href)
            if ch_url in seen or "/chapters/" not in ch_url:
                continue
            seen.add(ch_url)

            # Extract chapter number
            num_match = re.search(r"/chapters/(\d+)", ch_url)
            ch_num = int(num_match.group(1)) if num_match else len(chapters) + 1
            title = a.get_text(strip=True) or f"Chapter {ch_num}"

            chapters.append(ChapterInfo(
                chapter_number=ch_num,
                title=title,
                url=ch_url,
            ))

        # Sort by chapter number
        chapters.sort(key=lambda c: c.chapter_number)
        return chapters

    # ── Chapter Content ───────────────────────
    def get_chapter_content(self, url: str) -> str:
        soup = self._soup(url)

        # Content container or paragraph collection
        content_container = (
            soup.select_one("div.chapter-content") or
            soup.select_one("div.story-text") or
            soup.select_one("article") or
            soup.select_one("main")
        )

        if content_container:
            for tag in content_container.select("script, style, nav, div.ad, footer, header"):
                tag.decompose()
            p_tags = content_container.select("p")
            if p_tags:
                paragraphs = [p.get_text(strip=True) for p in p_tags if p.get_text(strip=True)]
                return "\n\n".join(paragraphs)
            return self._clean_text(content_container)

        # Fallback to all <p> tags on page
        p_tags = soup.select("p")
        if p_tags:
            return "\n\n".join(p.get_text(strip=True) for p in p_tags if len(p.get_text(strip=True)) > 20)

        return ""
