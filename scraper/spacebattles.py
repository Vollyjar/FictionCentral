"""
WebNovel Scraper — SpaceBattles / Sufficient Velocity Scraper

Scrapes forum-based fiction from XenForo sites using threadmarks.
Supports both forums.spacebattles.com and forums.sufficientvelocity.com.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from scraper.base import BaseScraper, ChapterInfo, NovelDetails, NovelSearchResult

logger = logging.getLogger(__name__)


class SpaceBattlesScraper(BaseScraper):
    site_name = "spacebattles"
    base_url = "https://forums.spacebattles.com"
    sv_base_url = "https://forums.sufficientvelocity.com"
    supported_genres = [
        "Fan-Fiction", "Science Fiction", "Fantasy", "Action", "Adventure",
        "Alternate History", "Crossover", "Supernatural", "Horror",
        "Mystery", "Drama", "Comedy", "Worm", "Naruto", "RWBY",
        "Harry Potter", "Star Wars", "Marvel", "DC", "Isekai",
    ]

    _DOMAINS = {
        "forums.spacebattles.com": "https://forums.spacebattles.com",
        "forums.sufficientvelocity.com": "https://forums.sufficientvelocity.com",
    }

    # Cache for reader mode parsed posts: thread_id -> {post_id_or_url: clean_html}
    _reader_cache: dict[str, dict[str, str]] = {}

    def _get_base_for_url(self, url: str) -> str:
        domain = urlparse(url).netloc.lower()
        return self._DOMAINS.get(domain, self.base_url)

    def _extract_thread_id(self, url: str) -> str:
        match = re.search(r"/threads/(?:[^/]*\.)?(\d+)", url)
        return match.group(1) if match else ""

    # ── Search ────────────────────────────────
    def search(self, query: str, page: int = 1) -> list[NovelSearchResult]:
        results: list[NovelSearchResult] = []

        # Use Sufficient Velocity / XenForo tokenized search (fast, reliable, unblocked)
        for base in [self.sv_base_url, self.base_url]:
            try:
                # 1. Fetch search page to acquire _xfToken
                search_page_url = f"{base}/search/"
                resp = self.client.get(search_page_url)
                if resp.status_code != 200:
                    continue

                soup0 = BeautifulSoup(resp.text, "lxml")
                token_el = soup0.find("input", attrs={"name": "_xfToken"})
                token = token_el.get("value", "") if token_el else ""

                # 2. POST search query
                data = {
                    "keywords": query,
                    "c[title_only]": 1,
                    "type": "thread",
                    "_xfToken": token,
                }
                search_action_url = f"{base}/search/search"
                post_resp = self.client.post(search_action_url, data=data)
                if post_resp.status_code != 200:
                    continue

                soup = BeautifulSoup(post_resp.text, "lxml")
                items = soup.select("li.block-row, div.contentRow")

                for item in items:
                    title_el = item.select_one(
                        "div.contentRow-main h3.contentRow-title a, "
                        "h3.contentRow-title a, div.contentRow-title a"
                    )
                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    href = title_el.get("href", "")
                    thread_url = self._abs_url(base, href)
                    if "/threads/" not in thread_url:
                        continue

                    # Author
                    author = item.get("data-author", "")
                    if not author:
                        author_el = item.select_one("a.username, span.username")
                        author = author_el.get_text(strip=True) if author_el else "Unknown"

                    # Cover / Avatar
                    img_el = item.select_one("span.contentRow-figure img, img")
                    cover = ""
                    if img_el:
                        cover = self._abs_url(base, img_el.get("src", ""))

                    # Snippet
                    snippet_el = item.select_one("div.contentRow-snippet, div.contentRow-minor")
                    synopsis = snippet_el.get_text(" ", strip=True)[:300] if snippet_el else ""

                    site_label = "spacebattles" if "spacebattles" in base else "sufficient_velocity"
                    results.append(NovelSearchResult(
                        title=title,
                        url=thread_url,
                        author=author,
                        cover_url=cover,
                        synopsis=synopsis,
                        source_site=site_label,
                        genres=["Fan-Fiction", "Science Fiction"],
                    ))

                if results:
                    break

            except Exception as exc:
                logger.debug("XenForo search on %s failed: %s", base, exc)
                continue

        return results

    # ── Novel Details ─────────────────────────
    def get_novel_details(self, url: str) -> NovelDetails:
        soup = self._soup(url)

        # Title
        title_el = soup.select_one("h1.p-title-value")
        title = ""
        if title_el:
            for badge in title_el.select("span.label, a.label"):
                badge.decompose()
            title = title_el.get_text(strip=True)
        if not title:
            og = soup.find("meta", property="og:title")
            title = og["content"] if og else "Unknown"

        # Author
        author_el = soup.select_one(
            "a.username[data-user-id], "
            "section.message:first-of-type a.username, "
            "article.message:first-of-type a.username"
        )
        author = author_el.get_text(strip=True) if author_el else "Unknown"

        # Synopsis
        first_post = soup.select_one(
            "article.message--post:first-of-type div.bbWrapper, "
            "div.message-body:first-of-type div.bbWrapper"
        )
        synopsis = ""
        if first_post:
            text = self._clean_text(first_post)
            synopsis = text[:500] + ("…" if len(text) > 500 else "")

        # Chapter count from reader mode or threadmarks
        chapters = self.get_chapter_list(url)
        chapter_count = len(chapters)

        domain = urlparse(url).netloc.lower()
        site_label = "spacebattles" if "spacebattles" in domain else "sufficient_velocity"

        return NovelDetails(
            title=title,
            url=url,
            author=author,
            synopsis=synopsis,
            source_site=site_label,
            genres=["Fan-Fiction", "Science Fiction"],
            chapter_count=chapter_count,
            status="Ongoing",
        )

    # ── Chapter List ──────────────────────────
    def get_chapter_list(self, url: str) -> list[ChapterInfo]:
        base = self._get_base_for_url(url)
        thread_id = self._extract_thread_id(url)
        chapters: list[ChapterInfo] = []
        seen_urls: set[str] = set()

        # Try reader mode first (contains all threadmarked posts with titles)
        reader_url = f"{base}/threads/{thread_id}/reader/"
        try:
            resp = self.client.get(reader_url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                articles = soup.select("article.message")
                post_cache = self._reader_cache.setdefault(thread_id, {})
                for idx, art in enumerate(articles, 1):
                    # Title
                    label = art.select_one("span.threadmarkLabel, div.message-cell--threadmark-header")
                    ch_title = label.get_text(strip=True) if label else f"Chapter {idx}"

                    # URL / Anchor
                    post_id = art.get("data-content", "").replace("post-", "")
                    if not post_id:
                        ch_url = f"{reader_url}#post-{idx}"
                        post_key = str(idx)
                    else:
                        ch_url = f"{base}/threads/{thread_id}/reader/#post-{post_id}"
                        post_key = post_id

                    # Pre-cache post body if present
                    body = art.select_one("div.bbWrapper")
                    if body:
                        clean_content = self._clean_html(body)
                        post_cache[post_key] = clean_content
                        post_cache[ch_url] = clean_content

                    if ch_url not in seen_urls:
                        seen_urls.add(ch_url)
                        chapters.append(ChapterInfo(
                            chapter_number=idx,
                            title=ch_title,
                            url=ch_url,
                        ))

                if chapters:
                    return chapters
        except Exception as exc:
            logger.debug("Failed reader mode chapter list on %s: %s", base, exc)

        # Fallback: single chapter
        chapters.append(ChapterInfo(
            chapter_number=1,
            title="Full Thread",
            url=url,
        ))
        return chapters

    # ── Chapter Content ───────────────────────
    def get_chapter_content(self, url: str) -> str:
        thread_id = self._extract_thread_id(url)
        post_id_match = re.search(r"post-(\d+)", url)
        post_id = post_id_match.group(1) if post_id_match else ""

        # 1. Check in-memory reader cache first (instant return)
        if thread_id and thread_id in self._reader_cache:
            cache = self._reader_cache[thread_id]
            if post_id and post_id in cache:
                return cache[post_id]
            if url in cache:
                return cache[url]

        soup = self._soup(url)

        content = None
        if post_id:
            post = soup.find(attrs={"data-content": f"post-{post_id}"})
            if post:
                content = post.select_one("div.bbWrapper")
            if not content:
                post = soup.select_one(f"article#post-{post_id} div.bbWrapper")
                content = post

        if not content:
            content = soup.select_one(
                "article.message--post:first-of-type div.bbWrapper, "
                "div.message-body:first-of-type div.bbWrapper, "
                "article.message div.bbWrapper"
            )

        if not content:
            return ""

        cleaned = self._clean_html(content)
        if thread_id:
            cache = self._reader_cache.setdefault(thread_id, {})
            if post_id:
                cache[post_id] = cleaned
            cache[url] = cleaned

        return cleaned
