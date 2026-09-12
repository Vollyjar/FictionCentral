"""
WebNovel Scraper — Webnovel Site Scraper

Implementation for https://www.webnovel.com.
Supports searching, metadata retrieval, table-of-contents catalog extraction,
and chapter text retrieval with support for REST API endpoints and fallback
to HTML parsing. Filters out paywalled/locked/coin-gated chapters.
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from scraper.base import BaseScraper, ChapterInfo, NovelDetails, NovelSearchResult

logger = logging.getLogger(__name__)


class WebnovelScraper(BaseScraper):
    """Scraper implementation for Webnovel (webnovel.com)."""

    site_name: str = "webnovel"
    base_url: str = "https://www.webnovel.com"
    supported_genres: list[str] = [
        "Fantasy",
        "Romance",
        "Cultivation",
        "Fan-Fiction",
        "Action",
        "Adventure",
        "Sci-fi",
        "Science Fiction",
        "Urban",
        "LitRPG",
        "Xianxia",
        "Xuanhuan",
        "Wuxia",
        "Isekai",
        "Progression Fantasy",
        "Comedy",
        "Drama",
        "Horror",
        "Mystery",
        "Supernatural",
        "Martial Arts",
        "Historical",
        "School Life",
        "Slice of Life",
        "Psychological",
        "Harem",
        "Mature",
    ]

    # ──────────────────────────────────────────
    # Abstract interface implementation
    # ──────────────────────────────────────────

    def search(self, query: str, page: int = 1) -> list[NovelSearchResult]:
        """Search Webnovel for novels matching *query*."""
        # 1. Try search REST API first
        api_results = self._search_api(query, page)
        if api_results:
            return api_results

        # 2. Fallback to HTML search page
        return self._search_html(query, page)

    def get_novel_details(self, url: str) -> NovelDetails:
        """Fetch full metadata for the novel at *url*."""
        book_id = self._extract_book_id(url)

        # 1. Try REST API if book ID is identified
        if book_id:
            details = self._get_novel_details_api(book_id, url)
            if details and details.title:
                return details

        # 2. Fallback to HTML scraping
        return self._get_novel_details_html(url, book_id)

    def get_chapter_list(self, url: str) -> list[ChapterInfo]:
        """Return an ordered list of free chapters for the novel at *url*.

        Only scrape free chapters; skip locked/coin-gated ones.
        """
        book_id = self._extract_book_id(url)
        if not book_id:
            logger.error("Could not determine book ID from URL: %s", url)
            return []

        # 1. Try catalog REST API
        chapters = self._get_chapter_list_api(book_id)
        if chapters:
            return chapters

        # 2. Fallback to HTML catalog page
        return self._get_chapter_list_html(url, book_id)

    def get_chapter_content(self, url: str) -> str:
        """Fetch the text content of a single free chapter at *url*.

        Raises ValueError if chapter is locked behind paywall or empty.
        """
        book_id = self._extract_book_id(url)
        chapter_id = self._extract_chapter_id(url)

        # 1. Try content REST API
        if book_id and chapter_id:
            content = self._get_chapter_content_api(book_id, chapter_id, url)
            if content:
                return content

        # 2. Fallback to HTML chapter page
        return self._get_chapter_content_html(url)

    # ──────────────────────────────────────────
    # Search implementations
    # ──────────────────────────────────────────

    def _search_api(self, query: str, page: int = 1) -> list[NovelSearchResult]:
        """Query Webnovel search REST API endpoint."""
        api_url = (
            f"https://www.webnovel.com/go/pcm/search/result?"
            f"searchType=1&keywords={quote_plus(query)}&pageIndex={page}"
        )
        headers = {
            "Referer": f"{self.base_url}/search",
            "Accept": "application/json, text/plain, */*",
        }
        try:
            resp = self.client.get(api_url, headers=headers)
            if resp.status_code != 200:
                logger.warning("Webnovel search API returned status %d", resp.status_code)
                return []

            data = resp.json()
            if not isinstance(data, dict):
                return []

            data_block = data.get("data") or {}
            book_info = data_block.get("bookInfo") or {}
            items = (
                book_info.get("bookItems")
                or data_block.get("bookItems")
                or data_block.get("items")
                or data_block.get("books")
                or []
            )

            results: list[NovelSearchResult] = []
            for item in items:
                if not isinstance(item, dict):
                    continue

                book_id = str(item.get("bookId") or item.get("id") or item.get("book_id") or "")
                title = str(item.get("bookName") or item.get("title") or item.get("name") or "").strip()
                if not title:
                    continue

                author = str(item.get("authorName") or item.get("author") or "Unknown").strip()
                synopsis = str(item.get("description") or item.get("synopsis") or item.get("intro") or "").strip()

                cover_raw = str(item.get("coverId") or item.get("coverUrl") or "")
                cover_url = self._build_cover_url(cover_raw, book_id)

                genres: list[str] = []
                category = item.get("categoryName") or item.get("category") or item.get("type")
                if category:
                    genres.append(str(category).strip())

                tag_list = item.get("tagInfo") or item.get("tagList") or item.get("tags") or []
                if isinstance(tag_list, list):
                    for t in tag_list:
                        if isinstance(t, str) and t.strip() and t.strip() not in genres:
                            genres.append(t.strip())
                        elif isinstance(t, dict):
                            tname = t.get("tagName") or t.get("name") or t.get("tag")
                            if tname and str(tname).strip() not in genres:
                                genres.append(str(tname).strip())

                try:
                    chapter_count = int(
                        item.get("totalChapterNum")
                        or item.get("chapterNum")
                        or item.get("chapterCount")
                        or 0
                    )
                except (ValueError, TypeError):
                    chapter_count = 0

                try:
                    rating = float(
                        item.get("score")
                        or item.get("totalScore")
                        or item.get("rating")
                        or 0.0
                    )
                except (ValueError, TypeError):
                    rating = 0.0

                raw_status = item.get("bookStatus") or item.get("status") or item.get("isFinished")
                if raw_status in (2, "2", "Completed", "completed", "Finished"):
                    status = "Completed"
                elif raw_status in (1, "1", "Ongoing", "ongoing"):
                    status = "Ongoing"
                else:
                    status = "Unknown"

                book_url = f"{self.base_url}/book/{book_id}" if book_id else ""
                if not book_url:
                    continue

                results.append(
                    NovelSearchResult(
                        title=title,
                        url=book_url,
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

        except Exception as exc:
            logger.warning("Webnovel search API error: %s", exc)
            return []

    def _search_html(self, query: str, page: int = 1) -> list[NovelSearchResult]:
        """Fallback search using HTML page and embedded scripts."""
        search_url = f"{self.base_url}/search?keywords={quote_plus(query)}&pageIndex={page}"
        try:
            soup = self._soup(search_url)
        except Exception as exc:
            logger.error("Webnovel search HTML request failed: %s", exc)
            return []

        # Check script tags for embedded JSON data
        embedded = self._extract_json_from_scripts(soup)
        for data in embedded:
            data_block = data.get("data") or data
            book_info = data_block.get("bookInfo") or {}
            items = book_info.get("bookItems") or data_block.get("bookItems") or []
            if items and isinstance(items, list):
                results: list[NovelSearchResult] = []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    book_id = str(item.get("bookId") or item.get("id") or "")
                    title = str(item.get("bookName") or item.get("title") or "").strip()
                    if not title:
                        continue
                    author = str(item.get("authorName") or item.get("author") or "Unknown").strip()
                    synopsis = str(item.get("description") or item.get("synopsis") or "").strip()
                    cover_url = self._build_cover_url(str(item.get("coverId") or item.get("coverUrl") or ""), book_id)
                    book_url = f"{self.base_url}/book/{book_id}" if book_id else ""
                    if not book_url:
                        continue
                    results.append(
                        NovelSearchResult(
                            title=title,
                            url=book_url,
                            author=author,
                            cover_url=cover_url,
                            synopsis=synopsis,
                            source_site=self.site_name,
                        )
                    )
                if results:
                    return results

        # Fallback to DOM parsing
        results: list[NovelSearchResult] = []
        item_nodes = soup.select(
            ".search-result-container li, ul.search-result-items li, "
            ".book-item, .search-list li, .j_bookList li"
        )

        if not item_nodes:
            # Last resort: find /book/ links on page
            seen_urls: set[str] = set()
            for a in soup.find_all("a", href=re.compile(r"/book/(?:[^/?#]+_)?\d+")):
                href = a.get("href", "")
                full_url = self._abs_url(self.base_url, href)
                # Ignore chapter links or duplicates
                if full_url in seen_urls or full_url.count("/") > 5:
                    continue
                seen_urls.add(full_url)
                title = self._clean_text(a)
                if title and len(title) > 2:
                    results.append(
                        NovelSearchResult(
                            title=title,
                            url=full_url,
                            author="Unknown",
                            source_site=self.site_name,
                        )
                    )
            return results

        for node in item_nodes:
            title_el = node.select_one("h3 a, h4 a, .book-name, a.book-title, a[href*='/book/']")
            if not title_el:
                continue
            title = self._clean_text(title_el)
            if not title:
                continue
            href = title_el.get("href", "")
            book_url = self._abs_url(self.base_url, href)

            author_el = node.select_one(".author, .author-name, span[class*='author']")
            author = self._clean_text(author_el) or "Unknown"

            synopsis_el = node.select_one("p.desc, .synopsis, p[class*='desc'], p[class*='intro']")
            synopsis = self._clean_text(synopsis_el)

            img = node.select_one("img")
            cover_url = ""
            if img:
                cover_url = img.get("src") or img.get("data-src") or ""
                if cover_url.startswith("//"):
                    cover_url = "https:" + cover_url

            genres = [
                self._clean_text(g)
                for g in node.select(".tag, .genre, .category, .tag-item")
                if self._clean_text(g)
            ]

            results.append(
                NovelSearchResult(
                    title=title,
                    url=book_url,
                    author=author,
                    cover_url=cover_url,
                    synopsis=synopsis,
                    source_site=self.site_name,
                    genres=genres,
                )
            )

        return results

    # ──────────────────────────────────────────
    # Novel details implementations
    # ──────────────────────────────────────────

    def _get_novel_details_api(self, book_id: str, original_url: str) -> NovelDetails | None:
        """Fetch novel details from REST API endpoint."""
        api_urls = [
            f"https://www.webnovel.com/go/pcm/book/get-book-detail?bookId={book_id}",
            f"https://www.webnovel.com/go/pcm/book/detail?bookId={book_id}",
        ]
        for api_url in api_urls:
            try:
                resp = self.client.get(
                    api_url,
                    headers={
                        "Referer": original_url,
                        "Accept": "application/json",
                    },
                )
                if resp.status_code != 200:
                    continue

                data = resp.json()
                if not isinstance(data, dict):
                    continue

                book_info = data.get("data", {}).get("bookInfo") or data.get("data", {})
                title = str(book_info.get("bookName") or book_info.get("title") or "").strip()
                if not title:
                    continue

                author = str(book_info.get("authorName") or book_info.get("author") or "Unknown").strip()
                synopsis = str(book_info.get("description") or book_info.get("synopsis") or "").strip()

                cover_raw = str(book_info.get("coverId") or book_info.get("coverUrl") or "")
                cover_url = self._build_cover_url(cover_raw, book_id)

                genres: list[str] = []
                category = book_info.get("categoryName") or book_info.get("category")
                if category:
                    genres.append(str(category).strip())

                tags: list[str] = []
                tag_list = book_info.get("tagInfo") or book_info.get("tagList") or book_info.get("tags") or []
                if isinstance(tag_list, list):
                    for t in tag_list:
                        if isinstance(t, str) and t.strip():
                            tags.append(t.strip())
                            if t.strip() not in genres:
                                genres.append(t.strip())
                        elif isinstance(t, dict):
                            tname = t.get("tagName") or t.get("name")
                            if tname and str(tname).strip():
                                t_str = str(tname).strip()
                                tags.append(t_str)
                                if t_str not in genres:
                                    genres.append(t_str)

                try:
                    chapter_count = int(
                        book_info.get("totalChapterNum")
                        or book_info.get("chapterNum")
                        or book_info.get("chapterCount")
                        or 0
                    )
                except (ValueError, TypeError):
                    chapter_count = 0

                try:
                    rating = float(book_info.get("score") or book_info.get("rating") or 0.0)
                except (ValueError, TypeError):
                    rating = 0.0

                raw_status = book_info.get("bookStatus") or book_info.get("status") or book_info.get("isFinished")
                if raw_status in (2, "2", "Completed", "completed", "Finished"):
                    status = "Completed"
                elif raw_status in (1, "1", "Ongoing", "ongoing"):
                    status = "Ongoing"
                else:
                    status = "Unknown"

                return NovelDetails(
                    title=title,
                    url=original_url,
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
            except Exception as exc:
                logger.debug("API detail check failed for %s: %s", api_url, exc)

        return None

    def _get_novel_details_html(self, url: str, book_id: str | None = None) -> NovelDetails:
        """Extract novel details from HTML page and embedded JSON-LD/state."""
        soup = self._soup(url)

        title = ""
        author = "Unknown"
        synopsis = ""
        cover_url = ""
        genres: list[str] = []
        tags: list[str] = []
        chapter_count = 0
        rating = 0.0
        status = "Unknown"

        # 1. Parse JSON-LD and embedded script tags
        embedded = self._extract_json_from_scripts(soup)
        for data in embedded:
            # JSON-LD Book schema
            if data.get("@type") in ("Book", "Novel", "CreativeWork") or "Book" in str(data.get("@type", "")):
                if not title and data.get("name"):
                    title = str(data["name"]).strip()
                if author == "Unknown" and data.get("author"):
                    auth_data = data["author"]
                    if isinstance(auth_data, dict):
                        author = auth_data.get("name", "Unknown")
                    elif isinstance(auth_data, str):
                        author = auth_data
                    elif isinstance(auth_data, list) and auth_data:
                        first = auth_data[0]
                        author = first.get("name", "Unknown") if isinstance(first, dict) else str(first)
                if not synopsis and data.get("description"):
                    synopsis = str(data["description"]).strip()
                if not cover_url and data.get("image"):
                    cover_url = str(data["image"]).strip()
                if rating == 0.0 and data.get("aggregateRating"):
                    try:
                        rating = float(data["aggregateRating"].get("ratingValue", 0.0))
                    except (ValueError, TypeError):
                        pass
                if data.get("genre"):
                    g = data["genre"]
                    if isinstance(g, list):
                        genres.extend([str(x).strip() for x in g if str(x).strip() not in genres])
                    elif isinstance(g, str) and g.strip() not in genres:
                        genres.append(g.strip())

            # __INITIAL_DATA__ or state with bookInfo
            book_info = data.get("bookInfo") or data.get("data", {}).get("bookInfo") or {}
            if isinstance(book_info, dict) and book_info.get("bookName"):
                if not title:
                    title = str(book_info.get("bookName")).strip()
                if author == "Unknown" and book_info.get("authorName"):
                    author = str(book_info.get("authorName")).strip()
                if not synopsis and book_info.get("description"):
                    synopsis = str(book_info.get("description")).strip()
                if not cover_url:
                    cover_raw = str(book_info.get("coverId") or book_info.get("coverUrl") or "")
                    cover_url = self._build_cover_url(cover_raw, book_id or "")
                if chapter_count == 0:
                    try:
                        chapter_count = int(book_info.get("totalChapterNum", 0))
                    except (ValueError, TypeError):
                        pass
                if rating == 0.0:
                    try:
                        rating = float(book_info.get("score", 0.0))
                    except (ValueError, TypeError):
                        pass

        # 2. OpenGraph meta tags fallback
        if not title:
            og_title = soup.select_one("meta[property='og:title']")
            if og_title and og_title.get("content"):
                raw_title = og_title["content"].strip()
                raw_title = re.sub(r"\s*[-|]\s*Webnovel.*$", "", raw_title, flags=re.IGNORECASE)
                title = raw_title.strip()

        if not synopsis:
            og_desc = soup.select_one("meta[property='og:description'], meta[name='description']")
            if og_desc and og_desc.get("content"):
                synopsis = og_desc["content"].strip()

        if not cover_url:
            og_img = soup.select_one("meta[property='og:image']")
            if og_img and og_img.get("content"):
                cover_url = og_img["content"].strip()

        if author == "Unknown":
            og_author = soup.select_one(
                "meta[name='author'], meta[property='books:author'], meta[property='book:author']"
            )
            if og_author and og_author.get("content"):
                author = og_author["content"].strip()

        # 3. DOM selectors fallback
        if not title:
            title_el = soup.select_one("h1.book-title, h1.detail-title, .book-info h1, .detail_title, h1")
            if title_el:
                title = self._clean_text(title_el)

        if author == "Unknown":
            author_el = soup.select_one(".author-name, .author, .writer, a[href*='/author/'], span[class*='author']")
            if author_el:
                raw_auth = self._clean_text(author_el)
                author = re.sub(r"^(?:Author|By)\s*[:：]\s*", "", raw_auth, flags=re.IGNORECASE).strip()

        if not synopsis:
            syn_el = soup.select_one(".synopsis, .j_synopsis, .book-desc, .detail-desc, .desc, .book-intro")
            if syn_el:
                synopsis = self._clean_text(syn_el)

        if not cover_url:
            cover_img = soup.select_one(".book-cover img, .detail-thumb img, .g_thumb img, img[class*='cover']")
            if cover_img:
                cover_url = cover_img.get("src") or cover_img.get("data-src") or ""
                if cover_url.startswith("//"):
                    cover_url = "https:" + cover_url

        if not cover_url and book_id:
            cover_url = self._build_cover_url("", book_id)

        # Tags and Genres from DOM
        tag_els = soup.select(".tag-item, .tags-wrap a, .book-tags a, .j_tag, .cate a, a[href*='/genre/']")
        for el in tag_els:
            t_text = self._clean_text(el)
            if t_text and t_text not in tags:
                tags.append(t_text)
                if t_text not in genres:
                    genres.append(t_text)

        # Chapter count from DOM
        if chapter_count == 0:
            ch_el = soup.select_one(".chapter-num, .total-chapters, .j_chapter_count, span[class*='chapter']")
            if ch_el:
                ch_text = self._clean_text(ch_el)
                m = re.search(r"(\d+)", ch_text)
                if m:
                    chapter_count = int(m.group(1))

        # Rating from DOM
        if rating == 0.0:
            rating_el = soup.select_one(".score, .rating, .j_score, span[class*='score']")
            if rating_el:
                r_text = self._clean_text(rating_el)
                m = re.search(r"(\d+(?:\.\d+)?)", r_text)
                if m:
                    rating = float(m.group(1))

        # Status from page text
        page_text = soup.get_text()
        if re.search(r"\bCompleted\b", page_text, re.IGNORECASE):
            status = "Completed"
        elif re.search(r"\bOngoing\b", page_text, re.IGNORECASE):
            status = "Ongoing"

        if not title:
            title = f"Webnovel {book_id}" if book_id else "Unknown Novel"

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
    # Chapter list implementations
    # ──────────────────────────────────────────

    def _get_chapter_list_api(self, book_id: str) -> list[ChapterInfo]:
        """Query Webnovel catalog REST API endpoints."""
        csrf = self._get_csrf_token()
        csrf_param = f"_csrfToken={csrf}&" if csrf else ""
        endpoints = [
            f"https://www.webnovel.com/go/pcm/chapter/get-chapter-list?{csrf_param}bookId={book_id}",
            f"https://www.webnovel.com/go/pcm/book/get-catalog?{csrf_param}bookId={book_id}",
            f"https://www.webnovel.com/go/pcm/book/get-chapter-list?{csrf_param}bookId={book_id}",
        ]
        for endpoint in endpoints:
            try:
                resp = self.client.get(
                    endpoint,
                    headers={
                        "Referer": f"{self.base_url}/book/{book_id}",
                        "Accept": "application/json",
                    },
                )
                if resp.status_code != 200:
                    continue

                data = resp.json()
                if not isinstance(data, dict):
                    continue

                data_block = data.get("data") or {}
                if isinstance(data_block, dict) and (
                    data_block.get("volumeItems")
                    or data_block.get("chapterItems")
                    or data_block.get("chapters")
                ):
                    chapters = self._parse_catalog_data(data_block, book_id)
                    if chapters:
                        return chapters
            except Exception as exc:
                logger.debug("Webnovel catalog API failed for %s: %s", endpoint, exc)

        return []

    def _get_chapter_list_html(self, url: str, book_id: str) -> list[ChapterInfo]:
        """Extract free chapter list from catalog HTML page or embedded data."""
        catalog_urls = [
            f"{self.base_url}/book/{book_id}/catalog",
            url,
        ]

        for page_url in catalog_urls:
            try:
                soup = self._soup(page_url)
            except Exception as exc:
                logger.debug("Failed to fetch %s for chapters: %s", page_url, exc)
                continue

            # 1. Check embedded script JSON
            embedded = self._extract_json_from_scripts(soup)
            for data in embedded:
                data_block = data.get("data") or data
                chapters = self._parse_catalog_data(data_block, book_id)
                if chapters:
                    return chapters

            # 2. Check DOM elements
            item_nodes = soup.select(
                ".j_catalog_list li, .catalog-content li, .volume-item li, "
                "li.chapter-item, div.chapter-item"
            )
            if item_nodes:
                chapters: list[ChapterInfo] = []
                for node in item_nodes:
                    # Skip locked chapters
                    is_locked = bool(
                        node.select(".lock, .vip, .icon-lock, .j_lock, svg[class*='lock'], i[class*='lock']")
                        or node.get("data-lock") in ("1", "true")
                        or node.get("data-vip") in ("1", "true")
                        or any("lock" in c.lower() or "vip" in c.lower() for c in node.get("class", []))
                    )
                    if is_locked:
                        continue

                    a_tag = node.select_one("a[href*='/book/']")
                    if not a_tag:
                        continue

                    href = a_tag.get("href", "")
                    ch_url = self._abs_url(self.base_url, href)

                    # Extract clean title: prefer title attribute or inner strong/name tags over full link text
                    ch_name = (
                        a_tag.get("title", "").strip()
                        or (
                            self._clean_text(a_tag.select_one("strong, .chapter-name, .name"))
                            if a_tag.select_one("strong, .chapter-name, .name")
                            else ""
                        )
                        or self._clean_text(a_tag)
                        or f"Chapter {len(chapters) + 1}"
                    )
                    # Strip any accidental multiline noise, leading numbers, or trailing timestamps
                    ch_name = re.sub(r"^\d+\s*[\r\n]+", "", ch_name).strip()
                    ch_name = re.sub(
                        r"[\r\n]+\s*\d+\s+(?:years?|months?|weeks?|days?|hours?|mins?|minutes?|seconds?)\s+ago\s*$",
                        "",
                        ch_name,
                        flags=re.IGNORECASE,
                    ).strip()
                    ch_name = re.sub(r"\s+", " ", ch_name).strip()

                    ch_num = len(chapters) + 1

                    chapters.append(
                        ChapterInfo(
                            chapter_number=ch_num,
                            title=ch_name,
                            url=ch_url,
                        )
                    )

                if chapters:
                    return chapters

        return []

    def _parse_catalog_data(self, data_block: dict, book_id: str) -> list[ChapterInfo]:
        """Parse volumeItems / chapterItems, skipping locked/VIP chapters."""
        volume_items = data_block.get("volumeItems") or []
        chapter_items = (
            data_block.get("chapterItems")
            or data_block.get("chapters")
            or []
        )

        raw_chapters: list[dict] = []
        if volume_items and isinstance(volume_items, list):
            for vol in volume_items:
                if not isinstance(vol, dict):
                    continue
                vol_chaps = vol.get("chapterItems") or vol.get("chapters") or []
                if isinstance(vol_chaps, list):
                    raw_chapters.extend(vol_chaps)
        elif chapter_items and isinstance(chapter_items, list):
            raw_chapters.extend(chapter_items)

        chapters: list[ChapterInfo] = []
        for idx, item in enumerate(raw_chapters, start=1):
            if not isinstance(item, dict):
                continue

            # Skip locked chapters (VIP or paid)
            if self._is_chapter_locked(item):
                continue

            ch_id = str(item.get("chapterId") or item.get("id") or "").strip()
            if not ch_id:
                continue

            ch_name = str(
                item.get("chapterName")
                or item.get("name")
                or item.get("title")
                or f"Chapter {idx}"
            ).strip()

            ch_num = len(chapters) + 1

            ch_url = f"{self.base_url}/book/{book_id}/{ch_id}"
            chapters.append(
                ChapterInfo(
                    chapter_number=ch_num,
                    title=ch_name,
                    url=ch_url,
                )
            )

        return chapters

    # ──────────────────────────────────────────
    # Chapter content implementations
    # ──────────────────────────────────────────

    def _get_chapter_content_api(self, book_id: str, chapter_id: str, original_url: str) -> str | None:
        """Fetch chapter text content from REST API endpoint."""
        csrf = self._get_csrf_token()
        csrf_param = f"_csrfToken={csrf}&" if csrf else ""
        endpoint = (
            f"https://www.webnovel.com/go/pcm/chapter/getContent?"
            f"{csrf_param}bookId={book_id}&chapterId={chapter_id}"
        )
        try:
            resp = self.client.get(
                endpoint,
                headers={
                    "Referer": original_url,
                    "Accept": "application/json",
                },
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            if not isinstance(data, dict):
                return None

            ch_data = (
                data.get("data", {}).get("chapterInfo")
                or data.get("data")
                or {}
            )
            if not isinstance(ch_data, dict):
                return None

            # Check if chapter is locked
            if self._is_chapter_locked(ch_data):
                raise ValueError(f"Chapter is locked behind paywall / requires coins: {original_url}")

            content_raw = (
                ch_data.get("contents")
                or ch_data.get("content")
                or ch_data.get("paragraphs")
            )

            if isinstance(content_raw, list):
                raw_items = [
                    (p.get("content") if isinstance(p, dict) else str(p)).strip()
                    for p in content_raw
                    if (p.get("content") if isinstance(p, dict) else str(p)).strip()
                ]
                if raw_items:
                    has_html = any("<p" in item for item in raw_items)
                    combined = "".join(raw_items) if has_html else "\n\n".join(raw_items)
                    if "<p>" in combined or "<br" in combined or "<div" in combined:
                        return self._clean_html(BeautifulSoup(combined, "lxml"))
                    return combined.strip()

            elif isinstance(content_raw, str) and content_raw.strip():
                if "<p>" in content_raw or "<br" in content_raw or "<div>" in content_raw:
                    return self._clean_html(BeautifulSoup(content_raw, "lxml"))
                return content_raw.strip()

        except ValueError:
            raise
        except Exception as exc:
            logger.debug("Chapter content API failed for %s: %s", endpoint, exc)

        return None

    def _get_chapter_content_html(self, url: str) -> str:
        """Extract free chapter content from HTML page."""
        soup = self._soup(url)

        # 1. Check for locked paywall markers
        lock_markers = soup.select(
            ".j_chapter_lock, .locked-mask, .unlock-box, .coins-wrap, "
            ".cha-content-lock, .paywall, .vip-limit-box, .lock-status"
        )

        # 2. Check embedded script data
        embedded = self._extract_json_from_scripts(soup)
        for data in embedded:
            ch_info = (
                data.get("chapterInfo")
                or data.get("chapter", {}).get("chapterInfo")
                or data.get("data", {}).get("chapterInfo")
                or {}
            )
            if isinstance(ch_info, dict) and ch_info:
                if self._is_chapter_locked(ch_info):
                    raise ValueError(f"Chapter is locked behind paywall / requires coins: {url}")

                content_raw = ch_info.get("contents") or ch_info.get("content") or ch_info.get("paragraphs")
                if isinstance(content_raw, list):
                    raw_items = [
                        (p.get("content") if isinstance(p, dict) else str(p)).strip()
                        for p in content_raw
                        if (p.get("content") if isinstance(p, dict) else str(p)).strip()
                    ]
                    if raw_items:
                        has_html = any("<p" in item for item in raw_items)
                        combined = "".join(raw_items) if has_html else "\n\n".join(raw_items)
                        if "<p>" in combined or "<br" in combined or "<div" in combined:
                            return self._clean_html(BeautifulSoup(combined, "lxml"))
                        return combined.strip()

                elif isinstance(content_raw, str) and content_raw.strip():
                    if "<p>" in content_raw or "<br" in content_raw or "<div>" in content_raw:
                        return self._clean_html(BeautifulSoup(content_raw, "lxml"))
                    return content_raw.strip()

        # 3. Locate content container in DOM
        container = soup.select_one(
            "div.chapter_content, div.cha-content, div.cha-words, "
            "div.cha-paragraph, div.chapter-entity, div[class*='cha-content'], "
            "div[class*='chapter_content'], div.content-text, .chapter-body, .entry-content"
        )

        if container is None:
            if lock_markers:
                raise ValueError(f"Chapter is locked behind paywall / requires coins: {url}")
            raise ValueError(f"Could not find chapter content container at {url}")

        # Remove ads, anti-piracy, and author notes
        for junk in container.find_all(["script", "style", "button", "iframe", "noscript"]):
            junk.decompose()
        for junk in container.select(
            ".pirate, .cha-pirate, .j_chapter_lock, .locked-mask, .unlock-box, "
            ".coins-wrap, .ad-box, .advertisement, .cha-bts, .cha-author-say, "
            ".cha-tit, .cha-hd, .cha-info"
        ):
            junk.decompose()

        # Extract text by paragraphs
        p_tags = container.find_all("p")
        if p_tags:
            paragraphs = []
            for p in p_tags:
                p_text = p.get_text(strip=True)
                if p_text:
                    paragraphs.append(p_text)
            content = "\n\n".join(paragraphs)
        else:
            content = self._clean_text(container)

        # Strip any watermark header
        content = re.sub(r"^[^\w]*Webnovel[^\w]*\n+", "", content, flags=re.IGNORECASE).strip()

        # Validate extracted text against locked chapter previews
        content_lower = content.lower()
        is_preview_or_locked = (
            bool(lock_markers)
            or "unlock this chapter" in content_lower
            or "coins to unlock" in content_lower
            or "go to webnovel app to unlock" in content_lower
            or "this chapter is locked" in content_lower
        )
        if is_preview_or_locked and len(content) < 600:
            raise ValueError(f"Chapter is locked behind paywall / requires coins: {url}")

        if not content.strip():
            raise ValueError(f"Empty chapter content retrieved from {url}")

        return content.strip()

    # ──────────────────────────────────────────
    # Helper utilities
    # ──────────────────────────────────────────

    def _get_csrf_token(self) -> str:
        """Get or initialize the Webnovel _csrfToken session cookie."""
        try:
            token = self.client.cookies.get("_csrfToken")
            if not token:
                self.client.get(self.base_url)
                token = self.client.cookies.get("_csrfToken")
            return token or ""
        except Exception:
            return ""

    @staticmethod
    def _extract_book_id(url: str) -> str | None:
        """Extract numeric or slug-based book ID from a Webnovel URL."""
        # Match /book/<slug_>123456789
        m = re.search(r"/book/(?:[^/?#/_]+_)?(\d+)(?:[/?#]|$)", url)
        if m:
            return m.group(1)
        # Match ?bookId=123456789
        m = re.search(r"[?&]bookId=(\d+)", url)
        if m:
            return m.group(1)
        # Match any /book/<identifier>
        m = re.search(r"/book/([^/?#]+)", url)
        if m:
            val = m.group(1)
            if "_" in val:
                parts = val.rsplit("_", 1)
                if parts[1].isdigit():
                    return parts[1]
            return val
        return None

    @staticmethod
    def _extract_chapter_id(url: str) -> str | None:
        """Extract chapter ID from a Webnovel chapter URL."""
        # Match /book/<book>/<chapter_slug_>123456789
        m = re.search(r"/book/[^/?#]+/(?:[^/?#/_]+_)?(\d+)(?:[/?#]|$)", url)
        if m:
            return m.group(1)
        # Match ?chapterId=123456789
        m = re.search(r"[?&]chapterId=(\d+)", url)
        if m:
            return m.group(1)
        # Match /book/<book>/<chapter_slug_or_id>
        m = re.search(r"/book/[^/?#]+/([^/?#]+)", url)
        if m:
            val = m.group(1)
            if "_" in val:
                parts = val.rsplit("_", 1)
                if parts[1].isdigit():
                    return parts[1]
            return val
        return None

    @staticmethod
    def _build_cover_url(cover_id_or_url: str, book_id: str = "") -> str:
        """Construct a full image URL for a novel cover."""
        if not cover_id_or_url and book_id:
            return f"https://img.webnovel.com/bookcover/{book_id}/300/300.jpg"
        if not cover_id_or_url:
            return ""
        if cover_id_or_url.startswith(("http://", "https://")):
            return cover_id_or_url
        if cover_id_or_url.startswith("//"):
            return "https:" + cover_id_or_url
        # If numeric or alphanumeric cover ID
        return f"https://img.webnovel.com/bookcover/{cover_id_or_url}/300/300.jpg"

    @staticmethod
    def _is_chapter_locked(item: dict) -> bool:
        """Return True if a chapter item indicates it is locked / requires coins / VIP."""
        if item.get("isVip") in (1, "1", True):
            return True
        if item.get("vip") in (1, "1", True):
            return True
        price = item.get("price")
        if price is not None:
            try:
                if int(price) > 0:
                    return True
            except (ValueError, TypeError):
                pass
        if item.get("isLock") in (1, "1", True) or item.get("isLocked") is True:
            return True
        vip_status = item.get("vipStatus")
        if vip_status is not None:
            try:
                if int(vip_status) > 0:
                    return True
            except (ValueError, TypeError):
                pass
        user_level = item.get("userLevel")
        if user_level is not None:
            try:
                if int(user_level) > 0:
                    return True
            except (ValueError, TypeError):
                pass
        if item.get("isAuth") in (0, "0", False):
            return True
        return False

    @staticmethod
    def _extract_json_from_scripts(soup: BeautifulSoup) -> list[dict]:
        """Extract embedded JSON blobs from script tags."""
        json_objects: list[dict] = []
        for script in soup.find_all("script"):
            text = script.string or script.get_text()
            if not text:
                continue
            text = text.strip()
            # 1. JSON-LD scripts
            if script.get("type") == "application/ld+json":
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        json_objects.append(parsed)
                    elif isinstance(parsed, list):
                        json_objects.extend([x for x in parsed if isinstance(x, dict)])
                except Exception:
                    pass
                continue

            # 2. Window state variables and chapInfo
            for var_name in ("chapInfo", "__INITIAL_DATA__", "__INITIAL_STATE__", "g_data", "_data"):
                if var_name in text:
                    m = re.search(rf"(?:var\s+)?{var_name}\s*=\s*({{.*?}})(?:;|\n|$)", text, re.DOTALL)
                    if m:
                        raw_json = m.group(1)
                        # Fix invalid JS escapes like \ or \'
                        clean_json = re.sub(r'\\(?![/\\\"bfnrtu]|u[0-9a-fA-F]{4})', '', raw_json)
                        try:
                            parsed = json.loads(clean_json)
                            if isinstance(parsed, dict):
                                json_objects.append(parsed)
                        except Exception:
                            try:
                                parsed = json.loads(raw_json)
                                if isinstance(parsed, dict):
                                    json_objects.append(parsed)
                            except Exception:
                                pass

        return json_objects
