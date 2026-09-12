"""
WebNovel Scraper — Wattpad Implementation

Site: Wattpad (https://www.wattpad.com)
Key: wattpad
Access: Freemium
Best for: Romance, young adult, drama, original fiction

Uses Wattpad's public REST APIs when possible (v4 search, v3 story details,
and apiv2 storytext), falling back to HTML parsing if API requests fail.
Only scrapes free/publicly available chapters, skipping paywalled content.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from scraper.base import BaseScraper, ChapterInfo, NovelDetails, NovelSearchResult

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Tag to canonical genre mapping
# ──────────────────────────────────────────────
TAG_TO_GENRE: dict[str, str] = {
    "action": "Action",
    "action-adventure": "Action",
    "adventure": "Adventure",
    "angst": "Drama",
    "bl": "Romance",
    "boyxboy": "Romance",
    "chicklit": "Romance",
    "college": "School Life",
    "comedy": "Comedy",
    "contemporary": "Drama",
    "cultivation": "Cultivation",
    "dark": "Psychological",
    "darkfantasy": "Fantasy",
    "drama": "Drama",
    "fanfic": "Fan-Fiction",
    "fanfiction": "Fan-Fiction",
    "fan-fiction": "Fan-Fiction",
    "fantasy": "Fantasy",
    "fiction": "Drama",
    "gl": "Romance",
    "girlxgirl": "Romance",
    "highschool": "School Life",
    "historical": "Historical",
    "historicalfiction": "Historical",
    "horror": "Horror",
    "humor": "Comedy",
    "isekai": "Isekai",
    "lgbt": "Romance",
    "lgbtq": "Romance",
    "litrpg": "LitRPG",
    "love": "Romance",
    "lovestory": "Romance",
    "magic": "Fantasy",
    "mature": "Mature",
    "mystery": "Mystery",
    "newadult": "Mature",
    "paranormal": "Supernatural",
    "psychological": "Psychological",
    "progression": "Progression Fantasy",
    "romance": "Romance",
    "romantic": "Romance",
    "school": "School Life",
    "schoollife": "School Life",
    "sci-fi": "Science Fiction",
    "sciencefiction": "Science Fiction",
    "scifi": "Science Fiction",
    "sliceoflife": "Slice of Life",
    "slice-of-life": "Slice of Life",
    "supernatural": "Supernatural",
    "suspense": "Thriller",
    "teen": "School Life",
    "teenfiction": "School Life",
    "thriller": "Thriller",
    "tragedy": "Tragedy",
    "urbanfantasy": "Fantasy",
    "vampire": "Supernatural",
    "werewolf": "Supernatural",
    "ya": "School Life",
    "youngadult": "School Life",
}


class WattpadScraper(BaseScraper):
    """Scraper implementation for Wattpad (wattpad.com)."""

    site_name: str = "wattpad"
    base_url: str = "https://www.wattpad.com"
    supported_genres: list[str] = [
        "Romance",
        "Drama",
        "Fantasy",
        "Fan-Fiction",
        "Science Fiction",
        "Action",
        "Adventure",
        "Mystery",
        "Thriller",
        "Horror",
        "Supernatural",
        "Slice of Life",
        "Historical",
        "Comedy",
        "Tragedy",
        "School Life",
        "Mature",
        "Psychological",
        "LitRPG",
        "Progression Fantasy",
        "Isekai",
        "Cultivation",
    ]

    # ──────────────────────────────────────────
    # Public interface methods
    # ──────────────────────────────────────────

    def search(self, query: str, page: int = 1) -> list[NovelSearchResult]:
        """Search Wattpad for stories matching *query* (1-indexed page)."""
        clean_query = query.strip()
        if not clean_query:
            return []

        limit = 20
        offset = max(0, (page - 1) * limit)

        # 1. Try public v4 API endpoint
        try:
            results = self._search_api(clean_query, limit=limit, offset=offset)
            if results:
                return results
        except Exception as exc:
            logger.warning("Wattpad API search failed for '%s': %s", clean_query, exc)

        # 2. Fall back to HTML search page
        try:
            return self._search_html(clean_query, page=page)
        except Exception as exc:
            logger.error("Wattpad HTML search fallback failed for '%s': %s", clean_query, exc)
            return []

    def get_novel_details(self, url: str) -> NovelDetails:
        """Fetch full metadata for the story at *url*."""
        story_id = self._resolve_story_id(url)

        # 1. Try public v3 story API endpoint
        if story_id:
            try:
                return self._get_novel_details_api(story_id, original_url=url)
            except Exception as exc:
                logger.warning(
                    "Wattpad API get_novel_details failed for story %s: %s", story_id, exc
                )

        # 2. Fall back to HTML scraping
        return self._get_novel_details_html(url, story_id=story_id)

    def get_chapter_list(self, url: str) -> list[ChapterInfo]:
        """Return an ordered list of free/public parts (chapters) for *url*."""
        story_id = self._resolve_story_id(url)

        # 1. Try public v3 story API endpoint
        if story_id:
            try:
                chapters = self._get_chapter_list_api(story_id)
                if chapters:
                    return chapters
            except Exception as exc:
                logger.warning(
                    "Wattpad API get_chapter_list failed for story %s: %s", story_id, exc
                )

        # 2. Fall back to HTML scraping
        return self._get_chapter_list_html(url)

    def get_chapter_content(self, url: str) -> str:
        """Fetch the text content of a single chapter/part at *url*."""
        part_id = self._extract_part_id(url)

        # 1. Try public apiv2 storytext API endpoint
        if part_id:
            try:
                content = self._get_chapter_content_api(part_id)
                if content:
                    return content
            except Exception as exc:
                logger.warning(
                    "Wattpad API get_chapter_content failed for part %s: %s", part_id, exc
                )

        # 2. Fall back to HTML scraping
        return self._get_chapter_content_html(url)

    # ──────────────────────────────────────────
    # API Implementation
    # ──────────────────────────────────────────

    def _search_api(self, query: str, limit: int = 20, offset: int = 0) -> list[NovelSearchResult]:
        """Query Wattpad's v4 search API."""
        encoded_query = quote_plus(query)
        api_url = f"{self.base_url}/v4/stories?query={encoded_query}&limit={limit}&offset={offset}"

        resp = self.client.get(api_url, headers={"Accept": "application/json"})
        resp.raise_for_status()

        data = resp.json()
        raw_stories = data.get("stories", [])
        if not isinstance(raw_stories, list):
            return []

        results: list[NovelSearchResult] = []
        for item in raw_stories:
            if not isinstance(item, dict):
                continue

            # Skip paid/paywalled stories
            if self._is_paid_story(item):
                continue

            title = str(item.get("title", "")).strip()
            if not title:
                continue

            story_id = str(item.get("id", "")).strip()
            story_url = item.get("url") or f"{self.base_url}/story/{story_id}"
            story_url = self._abs_url(self.base_url, story_url)

            user_obj = item.get("user")
            author = "Unknown"
            if isinstance(user_obj, dict):
                author = user_obj.get("name") or user_obj.get("fullname") or "Unknown"

            cover_url = item.get("cover") or ""
            synopsis = str(item.get("description", "")).strip()

            tags = item.get("tags") or []
            genres = self._extract_genres(tags)

            num_parts = item.get("numParts") or 0
            completed = bool(item.get("completed", False))
            status = "Completed" if completed else "Ongoing"

            results.append(
                NovelSearchResult(
                    title=title,
                    url=story_url,
                    author=author,
                    cover_url=cover_url,
                    synopsis=synopsis,
                    source_site=self.site_name,
                    genres=genres,
                    chapter_count=int(num_parts),
                    rating=0.0,
                    status=status,
                )
            )

        return results

    def _get_novel_details_api(self, story_id: str, original_url: str = "") -> NovelDetails:
        """Fetch full story metadata using Wattpad's v3 story API."""
        fields = (
            "id,title,description,url,cover,user(name,fullname),tags,"
            "completed,numParts,readCount,voteCount,categories,rating,"
            "parts(id,title,url,isPaywalled,paid)"
        )
        api_url = f"{self.base_url}/api/v3/stories/{story_id}?fields={fields}"

        resp = self.client.get(api_url, headers={"Accept": "application/json"})
        resp.raise_for_status()

        data = resp.json()
        title = str(data.get("title", "")).strip()
        story_url = data.get("url") or original_url or f"{self.base_url}/story/{story_id}"
        story_url = self._abs_url(self.base_url, story_url)

        user_obj = data.get("user")
        author = "Unknown"
        if isinstance(user_obj, dict):
            author = user_obj.get("fullname") or user_obj.get("name") or "Unknown"

        cover_url = data.get("cover") or ""
        synopsis = str(data.get("description", "")).strip()

        tags_raw = data.get("tags") or []
        tags = [str(t).strip() for t in tags_raw if t]
        genres = self._extract_genres(tags)

        # Filter out paid parts when counting chapters
        parts = data.get("parts") or []
        free_parts = [p for p in parts if not self._is_paid_part(p)]
        num_parts = len(free_parts) if parts else (data.get("numParts") or 0)

        completed = bool(data.get("completed", False))
        status = "Completed" if completed else "Ongoing"

        return NovelDetails(
            title=title,
            url=story_url,
            author=author,
            cover_url=cover_url,
            synopsis=synopsis,
            source_site=self.site_name,
            genres=genres,
            tags=tags,
            chapter_count=int(num_parts),
            rating=0.0,
            status=status,
        )

    def _get_chapter_list_api(self, story_id: str) -> list[ChapterInfo]:
        """Fetch the free chapter list using Wattpad's v3 story API."""
        fields = "id,title,numParts,parts(id,title,url,isPaywalled,paid)"
        api_url = f"{self.base_url}/api/v3/stories/{story_id}?fields={fields}"

        resp = self.client.get(api_url, headers={"Accept": "application/json"})
        resp.raise_for_status()

        data = resp.json()
        parts = data.get("parts", [])
        if not isinstance(parts, list):
            return []

        chapters: list[ChapterInfo] = []
        chapter_idx = 1

        for part in parts:
            if not isinstance(part, dict):
                continue

            # Only include free chapters
            if self._is_paid_part(part):
                continue

            part_id = part.get("id")
            if not part_id:
                continue

            title = str(part.get("title", "")).strip() or f"Part {chapter_idx}"
            part_url = part.get("url") or f"{self.base_url}/{part_id}"
            part_url = self._abs_url(self.base_url, str(part_url))

            chapters.append(
                ChapterInfo(
                    chapter_number=chapter_idx,
                    title=title,
                    url=part_url,
                )
            )
            chapter_idx += 1

        return chapters

    def _get_chapter_content_api(self, part_id: str) -> str:
        """Fetch chapter HTML via Wattpad's apiv2 storytext endpoint and clean it."""
        api_url = f"{self.base_url}/apiv2/storytext?id={part_id}"

        resp = self.client.get(api_url)
        resp.raise_for_status()

        raw_html = resp.text.strip()
        if not raw_html:
            return ""

        # Parse and clean HTML paragraphs
        soup = BeautifulSoup(raw_html, "lxml")
        return self._clean_text(soup)

    # ──────────────────────────────────────────
    # HTML Fallback Implementation
    # ──────────────────────────────────────────

    def _search_html(self, query: str, page: int = 1) -> list[NovelSearchResult]:
        """HTML fallback for searching stories on wattpad.com."""
        encoded_query = quote_plus(query)
        url = f"{self.base_url}/search/{encoded_query}"
        if page > 1:
            url = f"{url}?page={page}"

        soup = self._soup(url)
        results: list[NovelSearchResult] = []

        # Find story cards
        card_items = soup.select("ul.list-group li.list-group-item")
        if not card_items:
            card_items = soup.select("div.feed-item-new, div.story-card-data")

        for item in card_items:
            # Check if marked as paid/coin
            item_text = item.get_text()
            if "paid story" in item_text.lower() or "wattpad originals" in item_text.lower():
                # Some wattpad originals may be paid, check for paid badge
                if item.select_one(".paid-tag, [class*='paid'], [class*='coin']"):
                    continue

            link_el = item.select_one("a.story-card, a[href*='/story/']")
            if not link_el or not link_el.get("href"):
                continue

            href = link_el["href"]
            story_url = self._abs_url(self.base_url, href)

            title_el = item.select_one(".title, .story-info .title, h5")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                sr_only = item.select_one("span.sr-only")
                title = sr_only.get_text(strip=True) if sr_only else "Untitled"

            author_el = item.select_one("a.username, .author, a[href*='/user/']")
            author = "Unknown"
            if author_el:
                author = author_el.get_text(strip=True).removeprefix("by ").strip()

            cover_el = item.select_one(".cover img, img")
            cover_url = cover_el.get("src", "") if cover_el else ""

            desc_el = item.select_one(".description, .story-description")
            synopsis = self._clean_text(desc_el)

            status = "Ongoing"
            if item.select_one(".completed, .tag-item, [class*='complete']"):
                badge_text = item.select_one(".completed, .tag-item, [class*='complete']").get_text()
                if "complete" in badge_text.lower():
                    status = "Completed"

            chapter_count = 0
            m = re.search(r"Parts\s+(\d+)", item_text, re.IGNORECASE)
            if not m:
                m = re.search(r"(\d+)\s*(?:parts?|chapters?)", item_text, re.IGNORECASE)
            if m:
                try:
                    chapter_count = int(m.group(1))
                except ValueError:
                    chapter_count = 0

            results.append(
                NovelSearchResult(
                    title=title,
                    url=story_url,
                    author=author,
                    cover_url=cover_url,
                    synopsis=synopsis,
                    source_site=self.site_name,
                    genres=[],
                    chapter_count=chapter_count,
                    rating=0.0,
                    status=status,
                )
            )

        return results

    def _get_novel_details_html(self, url: str, story_id: str | None = None) -> NovelDetails:
        """HTML fallback for fetching story details."""
        soup = self._soup(url)

        title = ""
        author = "Unknown"
        cover_url = ""
        synopsis = ""
        tags: list[str] = []
        status = "Ongoing"
        chapter_count = 0

        # Try JSON-LD article metadata first
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                ld_data = json.loads(script.string or "{}")
                if isinstance(ld_data, dict):
                    if "@type" in ld_data and ld_data["@type"] in ("Article", "Book", "CreativeWork"):
                        title = title or ld_data.get("headline") or ld_data.get("name") or ""
                        desc = ld_data.get("description")
                        if desc:
                            synopsis = synopsis or desc
                        author_obj = ld_data.get("author")
                        if isinstance(author_obj, dict):
                            author = author_obj.get("name") or author
                        elif isinstance(author_obj, str):
                            author = author_obj
                        about = ld_data.get("about")
                        if about and isinstance(about, str):
                            tags.append(about)
            except Exception:
                pass

        # Try Remix context loaderData
        remix_match = re.search(r"window\.__remixContext\s*=\s*(\{.*?\});\s*</script>", str(soup))
        if remix_match:
            try:
                remix_data = json.loads(remix_match.group(1))
                loader_data = remix_data.get("state", {}).get("loaderData", {})
                for _, route_val in loader_data.items():
                    if isinstance(route_val, dict) and "story" in route_val:
                        s_data = route_val["story"]
                        title = title or s_data.get("title")
                        synopsis = synopsis or s_data.get("description")
                        cover_url = cover_url or s_data.get("cover")
                        user_val = s_data.get("user")
                        if isinstance(user_val, dict):
                            author = user_val.get("fullname") or user_val.get("name") or author
                        tags = tags or s_data.get("tags", [])
                        if s_data.get("completed"):
                            status = "Completed"
                        chapter_count = s_data.get("numParts") or len(s_data.get("parts", []))
            except Exception:
                pass

        # Fallback to OpenGraph and DOM elements
        if not title:
            title_el = (
                soup.select_one('h1[data-testid="title"]')
                or soup.select_one("h1.story-title")
                or soup.select_one("h1")
            )
            if title_el:
                title = title_el.get_text(strip=True)

        if not title:
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = og_title["content"].strip()

        if author == "Unknown":
            author_el = (
                soup.select_one('a[href*="/user/"]')
                or soup.select_one("span.author")
                or soup.select_one(".author-info a")
            )
            if author_el:
                author = author_el.get_text(strip=True).removeprefix("by ").strip()

        if not cover_url:
            cover_el = (
                soup.select_one('img[data-testid="image"]')
                or soup.select_one(".story-cover img")
                or soup.select_one("img.cover")
            )
            if cover_el and cover_el.get("src"):
                cover_url = cover_el["src"]

        if not cover_url:
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                cover_url = og_img["content"]

        if not synopsis:
            desc_el = (
                soup.select_one("div.description")
                or soup.select_one("div.story-description")
                or soup.select_one("pre.description-text")
            )
            synopsis = self._clean_text(desc_el)

        if not synopsis:
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                synopsis = og_desc["content"].strip()

        if not tags:
            tag_elements = soup.select('a[href*="/tag/"], ul.tag-items a, .story-tags a')
            tags = [el.get_text(strip=True) for el in tag_elements if el.get_text(strip=True)]

        if status == "Ongoing":
            complete_badge = soup.select_one(".tag-item, .completed, [class*='complete']")
            if complete_badge and "complete" in complete_badge.get_text().lower():
                status = "Completed"

        if chapter_count == 0:
            part_links = soup.select("ul.table-of-contents a, div.story-parts a")
            chapter_count = len(part_links)

        genres = self._extract_genres(tags)

        return NovelDetails(
            title=title or "Untitled",
            url=url,
            author=author,
            cover_url=cover_url,
            synopsis=synopsis,
            source_site=self.site_name,
            genres=genres,
            tags=tags,
            chapter_count=chapter_count,
            rating=0.0,
            status=status,
        )

    def _get_chapter_list_html(self, url: str) -> list[ChapterInfo]:
        """HTML fallback for extracting the table of contents."""
        soup = self._soup(url)
        chapters: list[ChapterInfo] = []

        # Look for table of contents links
        links = soup.select("ul.table-of-contents a, div.story-parts a, .story-parts-list a")
        if not links:
            # Match any link with pattern /{part_id}-{slug}
            all_links = soup.find_all("a", href=True)
            links = [
                a
                for a in all_links
                if re.search(r"/\d+-[a-zA-Z0-9-]+", a["href"])
                and "/story/" not in a["href"]
                and "/user/" not in a["href"]
                and "support.wattpad.com" not in a["href"]
            ]

        seen_urls: set[str] = set()
        chapter_idx = 1

        for a in links:
            href = a.get("href", "")
            if not href:
                continue

            full_url = self._abs_url(self.base_url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Skip paid/locked parts if indicated by classes or icons
            parent = a.parent
            if parent and (
                parent.select_one(".lock-icon, [class*='lock'], [class*='coin'], [class*='paid']")
            ):
                continue

            title = a.get_text(strip=True) or f"Part {chapter_idx}"

            chapters.append(
                ChapterInfo(
                    chapter_number=chapter_idx,
                    title=title,
                    url=full_url,
                )
            )
            chapter_idx += 1

        return chapters

    def _get_chapter_content_html(self, url: str) -> str:
        """HTML fallback for extracting chapter text."""
        soup = self._soup(url)

        # 1. Try prompt recommended selectors
        selectors = [
            "div.story-part pre",
            "div.panel-reading",
            "div.story-text",
            "div.part-content",
            "pre",
        ]
        for sel in selectors:
            container = soup.select_one(sel)
            if container:
                text = self._clean_text(container)
                if text and len(text) > 100:
                    return text

        # 2. Try paragraph collection (Wattpad uses data-p-id on paragraphs)
        p_tags = soup.select("p[data-p-id]")
        if p_tags:
            paragraphs: list[str] = []
            for p in p_tags:
                clean_p = self._clean_text(p)
                if clean_p:
                    paragraphs.append(clean_p)
            if paragraphs:
                return "\n\n".join(paragraphs)

        return ""

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────

    def _resolve_story_id(self, url_or_id: str) -> str | None:
        """Extract story ID directly or resolve it from a chapter/part URL."""
        story_id = self._extract_story_id(url_or_id)
        if story_id:
            return story_id

        # If it's a part URL, fetch the page to find the story link
        part_id = self._extract_part_id(url_or_id)
        if part_id:
            try:
                soup = self._soup(url_or_id)
                # Look for link pointing back to the story
                story_link = soup.select_one("a[href*='/story/']")
                if story_link and story_link.get("href"):
                    return self._extract_story_id(story_link["href"])
            except Exception as exc:
                logger.debug("Failed to resolve story ID from part URL %s: %s", url_or_id, exc)

        return None

    @staticmethod
    def _extract_story_id(url_or_id: str) -> str | None:
        """Extract the numeric story ID from a URL or raw ID string."""
        clean = url_or_id.strip()
        if clean.isdigit():
            return clean

        m = re.search(r"/story/(\d+)", clean)
        if m:
            return m.group(1)

        return None

    @staticmethod
    def _extract_part_id(url_or_id: str) -> str | None:
        """Extract the numeric part (chapter) ID from a URL or raw ID string."""
        clean = url_or_id.strip()
        if clean.isdigit():
            return clean

        # Matches https://www.wattpad.com/1234567-slug or /1234567 or ?id=1234567
        m = re.search(r"wattpad\.com/(\d+)(?:-|$|\?)", clean)
        if m:
            return m.group(1)

        m = re.search(r"[?&]id=(\d+)", clean)
        if m:
            return m.group(1)

        m = re.search(r"/(\d+)(?:-[^/?#]*)?(?:$|\?)", clean)
        if m:
            return m.group(1)

        return None

    @staticmethod
    def _is_paid_story(story_data: dict[str, Any]) -> bool:
        """Check if a story requires payment or coins."""
        # Direct boolean flags
        for flag in ("isPaywalled", "paywalled", "is_paid", "paid", "isPaid"):
            if story_data.get(flag) is True:
                return True

        # readerBrowseEligibility field
        eligibility = story_data.get("readerBrowseEligibility")
        if isinstance(eligibility, dict) and eligibility.get("isPaywalled") is True:
            return True

        # paidModel field
        paid_model = story_data.get("paidModel")
        if paid_model not in (None, False, "", 0, "free"):
            return True

        # Tags check
        tags = [str(t).lower() for t in story_data.get("tags", []) if t]
        paid_tags = {"paid", "paidstory", "paidstories", "paidprogram", "wattpadpaid"}
        if any(pt in tags for pt in paid_tags):
            return True

        # Title check
        title = str(story_data.get("title", "")).lower()
        if "[paid]" in title or "(paid)" in title:
            return True

        return False

    @staticmethod
    def _is_paid_part(part_data: dict[str, Any]) -> bool:
        """Check if an individual chapter part requires payment."""
        for flag in ("isPaywalled", "paywalled", "is_paid", "paid", "isPaid", "isLocked", "locked"):
            if part_data.get(flag) is True:
                return True

        paid_model = part_data.get("paidModel")
        if paid_model not in (None, False, "", 0, "free"):
            return True

        return False

    @classmethod
    def _extract_genres(cls, tags: list[str]) -> list[str]:
        """Map Wattpad tags to canonical supported genres, preserving order."""
        found: list[str] = []
        seen: set[str] = set()

        for tag in tags:
            clean = str(tag).strip().lower().replace(" ", "").replace("-", "")
            # Check direct map or simplified
            genre = TAG_TO_GENRE.get(clean) or TAG_TO_GENRE.get(str(tag).strip().lower())
            if genre and genre not in seen:
                seen.add(genre)
                found.append(genre)

        return found
