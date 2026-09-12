"""
WebNovel Scraper — Archive of Our Own (AO3) Scraper

Implements scraping for Archive of Our Own (https://archiveofourown.org):
  • Search works by query with pagination
  • Retrieve novel metadata and tags
  • Extract full chapter listings (single and multi-chapter works)
  • Scrape chapter content with adult content & TOS acceptance handling
  • Strictly respects AO3 rate limiting (minimum 2-second delay)
"""
from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from scraper.base import BaseScraper, ChapterInfo, NovelDetails, NovelSearchResult
from utils.http import ResilientClient

logger = logging.getLogger(__name__)

# Genre keyword mapping for normalizing AO3 tags into standard genres
GENRE_MAP: dict[str, str] = {
    "fanfiction": "Fan-Fiction",
    "fan fiction": "Fan-Fiction",
    "fantasy": "Fantasy",
    "science fiction": "Science Fiction",
    "sci-fi": "Science Fiction",
    "romance": "Romance",
    "litrpg": "LitRPG",
    "progression fantasy": "Progression Fantasy",
    "isekai": "Isekai",
    "cultivation": "Cultivation",
    "xianxia": "Xianxia",
    "xuanhuan": "Xuanhuan",
    "wuxia": "Wuxia",
    "action": "Action",
    "adventure": "Adventure",
    "comedy": "Comedy",
    "humor": "Comedy",
    "drama": "Drama",
    "horror": "Horror",
    "mystery": "Mystery",
    "thriller": "Thriller",
    "slice of life": "Slice of Life",
    "tragedy": "Tragedy",
    "historical": "Historical",
    "supernatural": "Supernatural",
    "paranormal": "Supernatural",
    "martial arts": "Martial Arts",
    "mecha": "Mecha",
    "psychological": "Psychological",
    "school life": "School Life",
    "mature": "Mature",
    "explicit": "Mature",
    "erotica": "Mature",
}


class AO3Scraper(BaseScraper):
    """Scraper implementation for Archive of Our Own (ao3)."""

    site_name: str = "ao3"
    base_url: str = "https://archiveofourown.org"
    # In-memory cache for full work parsed chapters: work_id -> {key: cleaned_html}
    _full_work_cache: dict[str, dict[str, str]] = {}
    _full_work_attempted: set[str] = set()

    supported_genres: list[str] = [
        "Fan-Fiction",
        "Fantasy",
        "Science Fiction",
        "Romance",
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
        "Psychological",
        "Mature",
    ]

    def __init__(self, client: ResilientClient | None = None) -> None:
        super().__init__(client=client)

        # Pre-seed session cookies with view_adult=true to bypass adult warnings
        try:
            if hasattr(self.client, "_session"):
                self.client._session.cookies.set(
                    "view_adult", "true", domain="archiveofourown.org"
                )
        except Exception as exc:
            logger.debug("Could not pre-set session cookie on client: %s", exc)

    # ──────────────────────────────────────────
    # Internal Request & Rate Limiting Helpers
    # ──────────────────────────────────────────
    def _rate_limit(self) -> None:
        """Rate limiting is enforced centrally by ResilientClient."""
        pass

    def _prepare_url(self, url: str) -> str:
        """Ensure view_adult=true is present in work and chapter URLs."""
        if "/works/" in url:
            parsed = urlparse(url)
            query_dict = parse_qs(parsed.query)
            if "view_adult" not in query_dict:
                query_dict["view_adult"] = ["true"]
                new_query = urlencode(query_dict, doseq=True)
                return urlunparse(parsed._replace(query=new_query))
        return url

    def _handle_tos_and_adult(
        self, original_url: str, soup: BeautifulSoup, depth: int = 0
    ) -> BeautifulSoup:
        """Detect and handle adult content confirmation and Terms of Service prompts."""
        if depth > 3:
            return soup

        # 1. Adult warning "Proceed" button or link (only within caution / interstitial containers)
        proceed_link = soup.select_one(
            "div.caution a[href*='view_adult=true'], "
            "p.caution a[href*='view_adult=true'], "
            "div.warning a[href*='view_adult=true'], "
            "ul.actions li a[href*='view_adult=true']"
        )
        if proceed_link and proceed_link.get("href"):
            proceed_url = self._abs_url(self.base_url, proceed_link["href"])
            logger.debug("Encountered adult warning on AO3; following proceed link: %s", proceed_url)
            self._rate_limit()
            next_soup = super()._soup(proceed_url)
            return self._handle_tos_and_adult(proceed_url, next_soup, depth + 1)

        # 2. Terms of Service acceptance form
        tos_form = soup.find("form", id=re.compile(r"tos", re.I)) or soup.find(
            "form", action=re.compile(r"tos|agree", re.I)
        )
        if tos_form and tos_form.get("action"):
            form_action = self._abs_url(self.base_url, tos_form["action"])
            form_data: dict[str, str] = {}
            for inp in tos_form.find_all("input"):
                name = inp.get("name")
                if not name:
                    continue
                inp_type = inp.get("type", "").lower()
                val = inp.get("value", "")
                if inp_type == "checkbox":
                    val = inp.get("value", "1") or "1"
                form_data[name] = val
            if "agree" not in form_data:
                form_data["agree"] = "1"

            logger.info("Encountered TOS prompt on AO3; submitting agreement form to: %s", form_action)
            self._rate_limit()
            self.client.post(form_action, data=form_data)

            # Re-fetch the target page after agreeing to TOS
            self._rate_limit()
            next_soup = super()._soup(original_url)
            return self._handle_tos_and_adult(original_url, next_soup, depth + 1)

        return soup

    def _soup(self, url: str) -> BeautifulSoup:
        """Fetch *url* with rate-limiting, adult/TOS bypass, and return parsed BeautifulSoup."""
        url = self._prepare_url(url)
        self._rate_limit()
        soup = super()._soup(url)
        return self._handle_tos_and_adult(url, soup)

    # ──────────────────────────────────────────
    # Abstract BaseScraper Implementation
    # ──────────────────────────────────────────
    def search(self, query: str, page: int = 1) -> list[NovelSearchResult]:
        """Search AO3 works matching *query* with pagination support."""
        if not query.strip():
            return []

        query_params = {
            "work_search[query]": query.strip(),
            "page": str(page),
        }
        search_url = f"{self.base_url}/works/search?{urlencode(query_params)}"
        self._rate_limit()
        soup = super()._soup(search_url)

        blurbs = soup.select(
            "ol.work.index li.work.blurb, ol.work.index li.blurb, li.work.blurb, li.blurb.group"
        )
        if not blurbs:
            # Fallback for alternative blurb index layout
            blurbs = soup.select("li.blurb")

        results: list[NovelSearchResult] = []
        seen_urls: set[str] = set()

        for blurb in blurbs:
            try:
                heading = blurb.select_one("h4.heading")
                if not heading:
                    continue

                title_link = heading.select_one("a[href*='/works/']") or heading.find("a")
                if not title_link or not title_link.get("href"):
                    continue

                raw_href = title_link["href"]
                work_url = self._abs_url(self.base_url, raw_href)

                # Canonicalize work URL to /works/{work_id}
                work_id_match = re.search(r"/works/(\d+)", work_url)
                if work_id_match:
                    work_url = f"{self.base_url}/works/{work_id_match.group(1)}"

                if work_url in seen_urls:
                    continue
                seen_urls.add(work_url)

                title = self._clean_text(title_link) or "Untitled"

                # Author(s)
                author_links = heading.select("a[rel*='author']")
                if author_links:
                    author = ", ".join(
                        self._clean_text(a) for a in author_links if self._clean_text(a)
                    )
                else:
                    heading_text = heading.get_text()
                    if "Anonymous" in heading_text:
                        author = "Anonymous"
                    else:
                        author = "Unknown"

                # Synopsis
                summary_elem = blurb.select_one(
                    "blockquote.summary, div.summary blockquote, blockquote.userstuff"
                )
                synopsis = self._clean_text(summary_elem)

                # Tags & Genres
                tag_elements = blurb.select(
                    "ul.tags li a.tag, h5.fandoms a.tag, ul.tags li a, ul.tags li"
                )
                tags: list[str] = []
                for t_el in tag_elements:
                    t_text = self._clean_text(t_el)
                    if t_text and t_text not in tags:
                        tags.append(t_text)

                genres: list[str] = ["Fan-Fiction"]
                for tag in tags:
                    norm = tag.lower()
                    for key, g_val in GENRE_MAP.items():
                        if key in norm and g_val not in genres:
                            genres.append(g_val)

                # Chapter count and status from stats
                chapter_count = 1
                status = "Unknown"

                stats_dl = blurb.select_one("dl.stats")
                if stats_dl:
                    chapters_dd = stats_dl.select_one("dd.chapters")
                    if chapters_dd:
                        ch_text = chapters_dd.get_text(strip=True)
                        if "/" in ch_text:
                            parts = ch_text.split("/")
                            cur_str = re.sub(r"[^\d]", "", parts[0])
                            tot_str = parts[1].strip()
                            if cur_str.isdigit():
                                chapter_count = int(cur_str)
                            if tot_str == "?":
                                status = "Ongoing"
                            elif tot_str.isdigit():
                                tot_val = int(re.sub(r"[^\d]", "", tot_str))
                                if tot_val > 0 and chapter_count >= tot_val:
                                    status = "Completed"
                                else:
                                    status = "Ongoing"
                        else:
                            num = re.sub(r"[^\d]", "", ch_text)
                            if num.isdigit():
                                chapter_count = int(num)

                # Direct completion indicator badges
                if blurb.select_one(".complete-yes"):
                    status = "Completed"
                elif blurb.select_one(".complete-no"):
                    status = "Ongoing"

                results.append(
                    NovelSearchResult(
                        title=title,
                        url=work_url,
                        author=author,
                        cover_url="",
                        synopsis=synopsis,
                        source_site=self.site_name,
                        genres=genres,
                        chapter_count=chapter_count,
                        rating=0.0,
                        status=status,
                    )
                )
            except Exception as exc:
                logger.debug("Error parsing AO3 search result blurb: %s", exc)
                continue

        return results

    def get_novel_details(self, url: str) -> NovelDetails:
        """Fetch full metadata for the novel at *url*."""
        work_id_match = re.search(r"/works/(\d+)", url)
        canonical_url = (
            f"{self.base_url}/works/{work_id_match.group(1)}"
            if work_id_match
            else url
        )

        soup = self._soup(canonical_url)

        # Title
        title_elem = soup.select_one("h2.title, .preface .title, h2.heading")
        title = self._clean_text(title_elem) or "Untitled"

        # Author
        author_links = soup.select("h3.byline a[rel*='author'], h3.byline a")
        if author_links:
            author = ", ".join(
                self._clean_text(a) for a in author_links if self._clean_text(a)
            )
        else:
            byline_elem = soup.select_one("h3.byline")
            byline_text = self._clean_text(byline_elem) if byline_elem else ""
            if "Anonymous" in byline_text:
                author = "Anonymous"
            else:
                author = "Unknown"

        # Synopsis
        summary_elem = soup.select_one(
            "div.summary blockquote, div.summary .userstuff, .preface .summary blockquote"
        )
        synopsis = self._clean_text(summary_elem)

        # Tags from dl.work.meta.group
        tags: list[str] = []
        meta_selectors = [
            "dd.fandom a.tag",
            "dd.rating a.tag",
            "dd.warning a.tag",
            "dd.relationship a.tag",
            "dd.character a.tag",
            "dd.freeform a.tag",
        ]
        for sel in meta_selectors:
            for tag_a in soup.select(sel):
                t_text = self._clean_text(tag_a)
                if t_text and t_text not in tags:
                    tags.append(t_text)

        # Fallback to general tag links within metadata
        if not tags:
            for tag_a in soup.select("dl.work.meta.group dd a.tag, dl.meta dd a.tag"):
                t_text = self._clean_text(tag_a)
                if t_text and t_text not in tags:
                    tags.append(t_text)

        # Genres mapped from tags
        genres: list[str] = ["Fan-Fiction"]
        for tag in tags:
            norm = tag.lower()
            for key, g_val in GENRE_MAP.items():
                if key in norm and g_val not in genres:
                    genres.append(g_val)

        # Chapter count and status
        chapter_count = 1
        status = "Unknown"

        chapters_dd = soup.select_one("dd.chapters")
        if chapters_dd:
            ch_text = chapters_dd.get_text(strip=True)
            if "/" in ch_text:
                parts = ch_text.split("/")
                cur_str = re.sub(r"[^\d]", "", parts[0])
                tot_str = parts[1].strip()
                if cur_str.isdigit():
                    chapter_count = int(cur_str)
                if tot_str == "?":
                    status = "Ongoing"
                elif tot_str.isdigit():
                    tot_val = int(re.sub(r"[^\d]", "", tot_str))
                    if tot_val > 0 and chapter_count >= tot_val:
                        status = "Completed"
                    else:
                        status = "Ongoing"
            else:
                num = re.sub(r"[^\d]", "", ch_text)
                if num.isdigit():
                    chapter_count = int(num)

        if soup.select_one(".complete-yes"):
            status = "Completed"
        elif soup.select_one(".complete-no"):
            status = "Ongoing"
        elif chapter_count == 1 and status == "Unknown":
            if chapters_dd and "1/1" in chapters_dd.get_text():
                status = "Completed"

        return NovelDetails(
            title=title,
            url=canonical_url,
            author=author,
            cover_url="",
            synopsis=synopsis,
            source_site=self.site_name,
            genres=genres,
            tags=tags,
            chapter_count=chapter_count,
            rating=0.0,
            status=status,
        )

    def get_chapter_list(self, url: str) -> list[ChapterInfo]:
        """Return an ordered list of chapters for the work at *url*."""
        work_id_match = re.search(r"/works/(\d+)", url)
        work_id = work_id_match.group(1) if work_id_match else ""
        canonical_work_url = (
            f"{self.base_url}/works/{work_id}" if work_id else url
        )

        soup = self._soup(canonical_work_url)
        chapters: list[ChapterInfo] = []

        # 1. Try chapter dropdown (select#selected_id option)
        options = soup.select("select#selected_id option")
        if options:
            ch_num = 1
            for opt in options:
                val = opt.get("value", "").strip()
                if not val or val in ("selected", "0"):
                    continue
                if val.isdigit() and work_id:
                    ch_url = f"{self.base_url}/works/{work_id}/chapters/{val}"
                elif "/chapters/" in val:
                    ch_url = self._abs_url(self.base_url, val)
                else:
                    continue

                raw_title = opt.get_text(strip=True)
                chapters.append(
                    ChapterInfo(
                        chapter_number=ch_num,
                        title=raw_title or f"Chapter {ch_num}",
                        url=ch_url,
                    )
                )
                ch_num += 1

        # 2. Try chapter index links on current page (ul.chapter.index li a)
        if not chapters:
            index_links = soup.select(
                "ul.chapter.index li a, ol.chapter.index li a, .chapter.index li a"
            )
            if index_links:
                for idx, a in enumerate(index_links, 1):
                    href = a.get("href", "")
                    if "/chapters/" in href:
                        chapters.append(
                            ChapterInfo(
                                chapter_number=idx,
                                title=a.get_text(strip=True) or f"Chapter {idx}",
                                url=self._abs_url(self.base_url, href),
                            )
                        )

        # 3. If multi-chapter work but index not on current page, check /navigate TOC
        if not chapters and work_id:
            chapters_dd = soup.select_one("dd.chapters")
            ch_text = chapters_dd.get_text(strip=True) if chapters_dd else ""
            multi_chapter = False
            if "/" in ch_text:
                cur_str = re.sub(r"[^\d]", "", ch_text.split("/")[0])
                if cur_str.isdigit() and int(cur_str) > 1:
                    multi_chapter = True
            elif not chapters_dd:
                multi_chapter = True

            if multi_chapter:
                try:
                    nav_url = f"{self.base_url}/works/{work_id}/navigate"
                    nav_soup = self._soup(nav_url)
                    nav_links = nav_soup.select(
                        "ol.chapter.index li a, ul.chapter.index li a, ol.index li a, a[href*='/chapters/']"
                    )
                    seen_urls: set[str] = set()
                    idx = 1
                    for a in nav_links:
                        href = a.get("href", "")
                        if f"/works/{work_id}/chapters/" in href or (
                            href.startswith("/works/") and "/chapters/" in href
                        ):
                            full_ch_url = self._abs_url(self.base_url, href)
                            if full_ch_url not in seen_urls:
                                seen_urls.add(full_ch_url)
                                chapters.append(
                                    ChapterInfo(
                                        chapter_number=idx,
                                        title=a.get_text(strip=True) or f"Chapter {idx}",
                                        url=full_ch_url,
                                    )
                                )
                                idx += 1
                except Exception as exc:
                    logger.debug("Failed to fetch /navigate chapter list for %s: %s", work_id, exc)

        # 4. Fallback for single-chapter works (oneshots)
        if not chapters:
            title_elem = soup.select_one("h2.title, .preface .title, h2.heading")
            work_title = self._clean_text(title_elem) or "Chapter 1"
            chapters.append(
                ChapterInfo(
                    chapter_number=1,
                    title=work_title,
                    url=canonical_work_url,
                )
            )

        return chapters

    def get_chapter_content(self, url: str) -> str:
        """Fetch the text content of a single chapter at *url*, with full-work caching."""
        work_match = re.search(r"/works/(\d+)", url)
        work_id = work_match.group(1) if work_match else ""
        chap_match = re.search(r"/chapters/(\d+)", url)
        chapter_id = chap_match.group(1) if chap_match else ""

        # 1. Check in-memory full work cache first (instant return)
        if work_id and work_id in self._full_work_cache:
            cache = self._full_work_cache[work_id]
            if chapter_id and chapter_id in cache:
                return cache[chapter_id]
            if url in cache:
                return cache[url]
            clean_url = url.split("?")[0]
            if clean_url in cache:
                return cache[clean_url]

        # 2. If not yet attempted for this work, try single-request full work batch fetch
        if work_id and work_id not in self._full_work_attempted:
            self._full_work_attempted.add(work_id)
            try:
                full_url = f"{self.base_url}/works/{work_id}?view_adult=true&view_full_work=true"
                logger.debug("Attempting AO3 full work batch fetch: %s", full_url)
                full_soup = self._soup(full_url)
                chapter_divs = full_soup.select("div#chapters > div.chapter")

                if chapter_divs:
                    cache: dict[str, str] = {}
                    for idx, ch_div in enumerate(chapter_divs, 1):
                        content_elem = ch_div.select_one("div.userstuff[role='article']")
                        if not content_elem:
                            content_elem = ch_div.select_one("div.userstuff")
                        if not content_elem:
                            continue

                        html = self._clean_html(content_elem)
                        cache[str(idx)] = html
                        cache[f"chapter-{idx}"] = html

                        # Extract chapter link if present in heading
                        heading = ch_div.select_one("h3.title")
                        a_link = heading.find("a") if heading else None
                        if a_link and a_link.get("href"):
                            ch_href = a_link["href"]
                            cache[ch_href] = html
                            abs_ch_url = self._abs_url(self.base_url, ch_href)
                            cache[abs_ch_url] = html
                            cache[abs_ch_url.split("?")[0]] = html
                            m_cid = re.search(r"/chapters/(\d+)", ch_href)
                            if m_cid:
                                cache[m_cid.group(1)] = html

                    self._full_work_cache[work_id] = cache
                    logger.info("Cached %d chapters from AO3 full-work for work %s", len(chapter_divs), work_id)

                    if chapter_id and chapter_id in cache:
                        return cache[chapter_id]
                    if url in cache:
                        return cache[url]
                    clean_url = url.split("?")[0]
                    if clean_url in cache:
                        return cache[clean_url]
                    if str(1) in cache and not chapter_id:
                        return cache[str(1)]
            except Exception as exc:
                logger.debug("AO3 full work fetch unavailable for %s: %s", work_id, exc)

        # 3. Direct single-chapter fallback
        soup = self._soup(url)

        # If URL contains a fragment anchor (e.g. #chapter-1)
        parsed = urlparse(url)
        content_elem: Tag | None = None
        if parsed.fragment:
            fragment_target = soup.find(id=parsed.fragment)
            if fragment_target and isinstance(fragment_target, Tag):
                content_elem = fragment_target.select_one(
                    "div.userstuff[role='article'], div.userstuff"
                )

        if not content_elem:
            content_elem = soup.select_one("div.userstuff[role='article']")
        if not content_elem:
            content_elem = soup.select_one("div#chapters div.chapter div.userstuff")
        if not content_elem:
            content_elem = soup.select_one("div#chapters div.userstuff")
        if not content_elem:
            content_elem = soup.select_one("div.userstuff:not(.summary):not(.notes)")
        if not content_elem:
            content_elem = soup.select_one("div.userstuff")
        if not content_elem:
            content_elem = soup.select_one("#workskin")

        if not content_elem:
            return ""

        return self._clean_html(content_elem)
