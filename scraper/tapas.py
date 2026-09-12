"""
WebNovel Scraper — Tapas Scraper

Scrapes free novel episodes from https://tapas.io
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

from scraper.base import BaseScraper, ChapterInfo, NovelDetails, NovelSearchResult

logger = logging.getLogger(__name__)


class TapasScraper(BaseScraper):
    site_name = "tapas"
    base_url = "https://tapas.io"
    supported_genres = [
        "Fantasy", "Romance", "Science Fiction", "Action", "Comedy",
        "Drama", "Horror", "Mystery", "Slice of Life", "Thriller",
        "BL", "GL", "Fan-Fiction",
    ]

    # ── Search ────────────────────────────────
    def search(self, query: str, page: int = 1) -> list[NovelSearchResult]:
        url = f"{self.base_url}/search?q={quote_plus(query)}&t=novel"
        if page > 1:
            url += f"&page={page}"

        soup = self._soup(url)
        results: list[NovelSearchResult] = []
        seen_urls: set[str] = set()

        # Tapas search results are wrapped in li.search-item-wrap
        cards = soup.select("li.search-item-wrap, div.search-item-wrap")

        for card in cards:
            try:
                # Title and URL: inside div.title-section p.title a
                title_link = card.select_one("div.title-section p.title a, p.title a")
                if not title_link or not title_link.get("href"):
                    continue

                title = title_link.get_text(strip=True)
                href = title_link["href"]
                novel_url = self._abs_url(self.base_url, href)

                if not title or novel_url in seen_urls:
                    continue
                seen_urls.add(novel_url)

                # Author
                author_el = card.select_one("div.title-section p.sub-title a, p.sub-title a")
                author = author_el.get_text(strip=True) if author_el else "Unknown"

                # Cover
                img = card.select_one("div.item-thumb-wrap img, a.thumb-wrap img, img")
                cover = ""
                if img:
                    cover = img.get("data-src") or img.get("src") or ""

                # Synopsis
                desc_el = card.select_one("div.title-section p.desc, p.desc")
                synopsis = desc_el.get_text(strip=True) if desc_el else ""

                # Genres
                tag_links = card.select("div.title-section p.tag a, p.tag a")
                genres = [t.get_text(strip=True) for t in tag_links if t.get_text(strip=True)]

                results.append(NovelSearchResult(
                    title=title,
                    url=novel_url,
                    author=author,
                    cover_url=cover,
                    synopsis=synopsis,
                    source_site="tapas",
                    genres=genres,
                ))
            except Exception as exc:
                logger.debug("Failed to parse Tapas search card: %s", exc)
                continue

        return results

    # ── Novel Details ─────────────────────────
    def get_novel_details(self, url: str) -> NovelDetails:
        soup = self._soup(url)

        # Title
        title_el = soup.select_one("h1.series-title, h1.title, a.series__title")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            og = soup.find("meta", property="og:title")
            title = og["content"] if og else "Unknown"

        # Author
        author_el = soup.select_one("a.creator-name, a.name, span.author-name, a.link--creator")
        author = author_el.get_text(strip=True) if author_el else "Unknown"

        # Synopsis
        desc_el = soup.select_one("p.description, div.description, span.description, p.series-desc")
        synopsis = self._clean_text(desc_el) if desc_el else ""
        if not synopsis:
            og = soup.find("meta", property="og:description")
            synopsis = og["content"] if og else ""

        # Cover
        cover = ""
        og_img = soup.find("meta", property="og:image")
        if og_img:
            cover = og_img.get("content", "")
        if not cover:
            img = soup.select_one("img.series-thumb, img.thumb, div.series-header img")
            if img:
                cover = img.get("data-src") or img.get("src") or ""

        # Genres & Tags
        genre_els = soup.select("div.genre-btn, span.genre, a.genre-btn, div.info-tags span, a.link--genre")
        genres = [g.get_text(strip=True) for g in genre_els if g.get_text(strip=True)]

        # Episode count
        ep_list = self.get_chapter_list(url)
        chapter_count = len(ep_list)

        return NovelDetails(
            title=title,
            url=url,
            author=author,
            cover_url=cover,
            synopsis=synopsis,
            source_site="tapas",
            genres=genres,
            chapter_count=chapter_count,
            status="Ongoing",
        )

    # ── Chapter List ──────────────────────────
    def get_chapter_list(self, url: str) -> list[ChapterInfo]:
        """Fetch episodes for the series via series ID or HTML scraping."""
        chapters: list[ChapterInfo] = []

        # 1. Try extracting series ID from URL or page HTML
        series_id = ""
        id_match = re.search(r"/series/(\d+)", url)
        if id_match:
            series_id = id_match.group(1)

        soup = None
        if not series_id:
            soup = self._soup(url)
            # Find data-series-id or seriesId in HTML
            m = re.search(r'data-series-id="(\d+)"|series_id\s*[:=]\s*(\d+)|seriesId:\s*(\d+)', str(soup))
            if m:
                series_id = next(s for s in m.groups() if s)

        # 2. Query Tapas episodes endpoint if series_id is available
        if series_id:
            try:
                ep_url = f"{self.base_url}/series/{series_id}/episodes"
                resp = self.client.get(ep_url)
                if resp.status_code == 200:
                    data = resp.json()
                    episodes_data = data.get("data", {}).get("episodes", [])
                    for idx, ep in enumerate(episodes_data, 1):
                        # Only include free episodes
                        if not ep.get("free", True):
                            continue
                        ep_id = ep.get("id")
                        if not ep_id:
                            continue
                        ep_title = ep.get("title", f"Episode {idx}")
                        chapters.append(ChapterInfo(
                            chapter_number=idx,
                            title=ep_title,
                            url=f"{self.base_url}/episode/{ep_id}",
                        ))
                    if chapters:
                        return chapters
            except Exception as exc:
                logger.debug("Failed to fetch Tapas episodes API: %s", exc)

        # 3. Fallback: parse from HTML
        if soup is None:
            soup = self._soup(url)

        seen_urls: set[str] = set()
        ep_links = soup.select("a[href*='/episode/']")
        idx = 1
        for a in ep_links:
            href = a.get("href", "")
            full_url = self._abs_url(self.base_url, href)
            # Ignore canonical/rss/navigation links
            if "/episode/" not in full_url or full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            title = a.get_text(strip=True) or f"Episode {idx}"
            chapters.append(ChapterInfo(
                chapter_number=idx,
                title=title,
                url=full_url,
            ))
            idx += 1

        return chapters

    # ── Chapter Content ───────────────────────
    def get_chapter_content(self, url: str) -> str:
        soup = self._soup(url)

        content = (
            soup.select_one("article.viewer__body") or
            soup.select_one("div.body--content") or
            soup.select_one("div.viewer") or
            soup.select_one("div.ep-content") or
            soup.select_one("article")
        )

        if not content:
            return ""

        # Remove ads, navigation, modals, comments
        for tag in content.select("script, style, div.ad, div.viewer__ad, nav, div.viewer__comments, footer"):
            tag.decompose()

        return self._clean_text(content)
