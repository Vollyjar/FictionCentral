"""
WebNovel Scraper — Novelfire Scraper

Implementation of BaseScraper for Novelfire (https://novelfire.net).
Novelfire is a novel hosting site featuring independent original novels
and serialized fiction.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup, Tag

from scraper.base import BaseScraper, ChapterInfo, NovelDetails, NovelSearchResult

logger = logging.getLogger(__name__)


class NovelfireScraper(BaseScraper):
    """Scraper implementation for Novelfire (https://novelfire.net)."""

    site_name = "novelfire"
    base_url = "https://novelfire.net"

    supported_genres: list[str] = [
        "Action",
        "Adventure",
        "Comedy",
        "Cultivation",
        "Drama",
        "Fan-Fiction",
        "Fantasy",
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
        "Progression Fantasy",
        "Psychological",
        "Romance",
        "School Life",
        "Science Fiction",
        "Seinen",
        "Shoujo",
        "Shounen",
        "Slice of Life",
        "Supernatural",
        "Thriller",
        "Tragedy",
        "Wuxia",
        "Xianxia",
        "Xuanhuan",
    ]

    # ──────────────────────────────────────────
    # Search
    # ──────────────────────────────────────────
    def search(self, query: str, page: int = 1) -> list[NovelSearchResult]:
        """Search Novelfire for novels matching *query*."""
        query_clean = query.strip()
        if not query_clean:
            return []

        encoded = quote_plus(query_clean)
        if page > 1:
            search_url = f"{self.base_url}/search?keyword={encoded}&page={page}"
        else:
            search_url = f"{self.base_url}/search?keyword={encoded}"

        try:
            soup = self._soup(search_url)
        except Exception as exc:
            logger.warning("Novelfire search failed for '%s': %s", query, exc)
            return []

        card_selectors = [
            ".list-novel .row",
            ".books-list .book-item",
            ".novel-list .novel-item",
            ".search-results .novel-item",
            ".search-novel .novel-item",
            ".list-novel > div",
            "div.novel-item",
            "div.book-item",
            "li.novel-item",
            "li.book-item",
            ".grid-novel .novel-item",
        ]

        cards: list[Tag] = []
        for sel in card_selectors:
            found = soup.select(sel)
            if found:
                cards = found
                break

        # Fallback: find any element that has a novel link to /book/
        if not cards:
            seen_parents = set()
            for a in soup.select("a[href*='/book/']"):
                href = a.get("href", "")
                if re.search(r"/book/[^/?#]+/?$", href):
                    parent = a.find_parent("div")
                    if parent and id(parent) not in seen_parents:
                        seen_parents.add(id(parent))
                        cards.append(parent)

        results: list[NovelSearchResult] = []
        seen_urls: set[str] = set()

        for card in cards:
            # Title and URL
            title_el = card.select_one(
                "h3.novel-title a, h3.title a, h2 a, h3 a, h4 a, "
                ".novel-title a, .title a, a.title, "
                "a[href*='/book/']"
            )
            if not title_el:
                continue

            href = title_el.get("href", "")
            if not href or href == "#":
                continue

            novel_url = self._abs_url(self.base_url, href)
            # Ensure it is a book URL
            if not re.search(r"/book/[^/?#]+", novel_url):
                continue
            novel_url = re.sub(r"/chapters/?$", "", novel_url)

            if novel_url in seen_urls:
                continue
            seen_urls.add(novel_url)

            title = title_el.get_text(strip=True) or title_el.get("title", "").strip()
            img_el = card.select_one("img")
            if not title and img_el:
                title = img_el.get("alt", "").strip()
            if not title:
                continue

            # Cover image
            cover_url = ""
            if img_el:
                for attr in ("data-src", "data-original", "data-lazy-src", "src"):
                    src = img_el.get(attr)
                    if src and not src.startswith("data:"):
                        cover_url = self._abs_url(self.base_url, src.strip())
                        break

            # Author
            author = "Unknown"
            author_el = card.select_one(
                ".author a, span.author, .author, a[href*='/author/'], "
                ".writer, span.writer, .novel-item-author"
            )
            if author_el:
                author = author_el.get_text(strip=True)
            else:
                m = re.search(r"(?:Author|By)\s*[:：]\s*([^\n\r,;|]+)", card.get_text(), re.IGNORECASE)
                if m:
                    author = m.group(1).strip()
            author = re.sub(r"^(?:Author|By)\s*[:：]?\s*", "", author, flags=re.IGNORECASE).strip() or "Unknown"

            # Chapter count
            chapter_count = 0
            chap_el = card.select_one(
                ".chapters, .chapter-text, .total-chapters, span.chapter, "
                "a[href*='/chapter-'], span[class*='chapter']"
            )
            chap_text = chap_el.get_text() if chap_el else card.get_text()
            chap_match = re.search(r"(\d+)\s*(?:chapters?|ch|eps?)", chap_text, re.IGNORECASE)
            if not chap_match:
                chap_match = re.search(r"(?:chapter|ch\.?)\s*(\d+)", chap_text, re.IGNORECASE)
            if chap_match:
                try:
                    chapter_count = int(chap_match.group(1))
                except ValueError:
                    pass

            # Status
            status = "Unknown"
            status_el = card.select_one(".status, span.status, .label-status, .badge-status, .badge")
            if status_el:
                st = status_el.get_text().strip().lower()
                if "ongoing" in st:
                    status = "Ongoing"
                elif "complete" in st:
                    status = "Completed"
            if status == "Unknown":
                card_text = card.get_text()
                if re.search(r"\bcompleted\b", card_text, re.IGNORECASE):
                    status = "Completed"
                elif re.search(r"\bongoing\b", card_text, re.IGNORECASE):
                    status = "Ongoing"

            # Rating
            rating = 0.0
            rating_el = card.select_one(
                ".rating, .score, .rating-val, span[itemprop='ratingValue'], "
                ".novel-rating, .star-score"
            )
            if rating_el:
                r_match = re.search(r"(\d+(?:\.\d+)?)", rating_el.get_text())
                if r_match:
                    try:
                        rating = float(r_match.group(1))
                    except ValueError:
                        pass

            # Genres
            genres: list[str] = []
            genre_els = card.select(
                ".genres a, .genre a, a[href*='/genre/'], a[href*='/genres/'], "
                ".tag-item a, span.genre, .tags a"
            )
            for g in genre_els:
                gt = g.get_text(strip=True)
                if gt and gt not in genres:
                    genres.append(gt)

            # Synopsis
            synopsis = ""
            desc_el = card.select_one(
                ".description, .desc, .summary, .synopsis, p.text-muted, div.line-clamp"
            )
            if desc_el:
                synopsis = self._clean_text(desc_el)

            results.append(NovelSearchResult(
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
            ))

        return results

    # ──────────────────────────────────────────
    # Novel Details
    # ──────────────────────────────────────────
    def get_novel_details(self, url: str) -> NovelDetails:
        """Fetch full metadata for the novel at *url*."""
        soup = self._soup(url)

        # Title
        title = ""
        title_el = soup.select_one(
            "h1.novel-title, h1.title, h1.book-title, "
            "h1[itemprop='name'], .novel-info h1, div.info h1, h1"
        )
        if title_el:
            title = title_el.get_text(strip=True)
        if not title:
            og_title = soup.select_one("meta[property='og:title']")
            if og_title and og_title.get("content"):
                title = re.sub(
                    r"\s*[-|–—]\s*(?:Novel\s*Fire|Novelfire).*$",
                    "",
                    og_title["content"],
                    flags=re.IGNORECASE,
                ).strip()

        # Author
        author = "Unknown"
        author_el = soup.select_one(
            "span[itemprop='author'], a[href*='/author/'], "
            ".author a, .author, span.author, .novel-info .author"
        )
        if author_el:
            author = author_el.get_text(strip=True)
        else:
            for el in soup.select("ul.info-meta li, .novel-info li, .meta-data li, .info li, div.info-item"):
                t = el.get_text()
                if "author" in t.lower():
                    a_tag = el.find("a")
                    if a_tag:
                        author = a_tag.get_text(strip=True)
                    else:
                        m = re.search(r"author\s*[:：]\s*(.+)", t, re.IGNORECASE)
                        if m:
                            author = m.group(1).strip()
                    break
        author = re.sub(r"^(?:Author|By)\s*[:：]?\s*", "", author, flags=re.IGNORECASE).strip() or "Unknown"

        # Cover image
        cover_url = ""
        og_img = soup.select_one("meta[property='og:image']")
        if og_img and og_img.get("content"):
            cover_url = self._abs_url(self.base_url, og_img["content"].strip())

        if not cover_url:
            img_el = soup.select_one(
                ".book-cover img, .cover img, .novel-cover img, "
                "div.fixed-img img, div.thumb img, img[itemprop='image']"
            )
            if img_el:
                for attr in ("data-src", "data-original", "data-lazy-src", "src"):
                    src = img_el.get(attr)
                    if src and not src.startswith("data:"):
                        cover_url = self._abs_url(self.base_url, src.strip())
                        break

        # Synopsis
        synopsis = ""
        desc_el = soup.select_one(
            "div[itemprop='description'], .novel-desc, .description, "
            ".summary, #novel-description, .content-desc, .synopsis, "
            ".novel-detail-item .content"
        )
        if desc_el:
            synopsis = self._clean_text(desc_el)
        if not synopsis:
            og_desc = soup.select_one("meta[property='og:description'], meta[name='description']")
            if og_desc and og_desc.get("content"):
                synopsis = og_desc["content"].strip()

        # Genres and Tags
        genres: list[str] = []
        genre_els = soup.select(
            "a[href*='/genre/'], a[href*='/genres/'], .genres a, .genre a, .categories a"
        )
        for g in genre_els:
            gt = g.get_text(strip=True)
            if gt and gt not in genres:
                genres.append(gt)

        tags: list[str] = []
        tag_els = soup.select(
            "a[href*='/tag/'], a[href*='/tags/'], .tags a, .tag-item a"
        )
        for t in tag_els:
            tt = t.get_text(strip=True)
            if tt and tt not in tags and tt not in genres:
                tags.append(tt)

        # Status
        status = "Unknown"
        for el in soup.select(
            ".status, span.status, ul.info-meta li, .novel-info li, .meta-data li, .info li, div.info-item"
        ):
            t = el.get_text().lower()
            if "completed" in t:
                status = "Completed"
                break
            elif "ongoing" in t:
                status = "Ongoing"
                break

        # Rating
        rating = 0.0
        rating_el = soup.select_one(
            "span[itemprop='ratingValue'], .rating-val, .rating-average, "
            ".score, .rating, .novel-rating"
        )
        if rating_el:
            m = re.search(r"(\d+(?:\.\d+)?)", rating_el.get_text())
            if m:
                try:
                    rating = float(m.group(1))
                except ValueError:
                    pass

        # Chapter count
        chapter_count = 0
        for el in soup.select(
            "ul.info-meta li, .novel-info li, .meta-data li, .info li, "
            "div.info-item, .total-chapters, .chapters"
        ):
            t = el.get_text()
            if "chapter" in t.lower():
                m = re.search(r"(\d+)\s*(?:chapters?|ch|eps?)", t, re.IGNORECASE)
                if not m:
                    m = re.search(r"(?:chapter|ch\.?)\s*(\d+)", t, re.IGNORECASE)
                if m:
                    chapter_count = int(m.group(1))
                    break

        if chapter_count == 0:
            chap_links = soup.select("a[href*='/chapter-'], #list-chapter a, .list-chapter a, .chapter-list a")
            if chap_links:
                chapter_count = len(chap_links)

        return NovelDetails(
            title=title or "Unknown Title",
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
        """Return an ordered list of chapters for the novel at *url*."""
        slug_match = re.search(r"/book/([^/?#]+)", url)
        novel_slug = slug_match.group(1) if slug_match else ""

        # Check if URL already points to /chapters, otherwise derive it
        if "/chapters" in url:
            chapters_url = url
        else:
            chapters_url = f"{url.rstrip('/')}/chapters"

        soup: BeautifulSoup | None = None
        try:
            soup = self._soup(chapters_url)
        except Exception as exc:
            logger.debug("Could not fetch %s (%s); will try main novel page", chapters_url, exc)

        raw_chapters: list[tuple[int | None, str, str]] = []

        if soup is not None:
            raw_chapters = self._extract_chapters_from_soup(soup, novel_slug)

            # Check for pagination on chapter list
            max_page = self._find_max_page(soup)
            if max_page > 1:
                base_p_url = chapters_url.split("?")[0]
                for page_num in range(2, min(max_page + 1, 101)):
                    p_url = f"{base_p_url}?page={page_num}"
                    try:
                        p_soup = self._soup(p_url)
                        p_chaps = self._extract_chapters_from_soup(p_soup, novel_slug)
                        if not p_chaps:
                            break
                        raw_chapters.extend(p_chaps)
                    except Exception as p_exc:
                        logger.debug("Failed fetching chapter page %s: %s", p_url, p_exc)
                        break

        # If no chapters found via /chapters, try main novel page
        if not raw_chapters and chapters_url != url:
            try:
                main_soup = self._soup(url)
                raw_chapters = self._extract_chapters_from_soup(main_soup, novel_slug)
            except Exception as exc:
                logger.warning("Failed fetching novel page %s: %s", url, exc)

        if not raw_chapters:
            return []

        # Deduplicate chapters by URL while preserving order
        seen_urls: set[str] = set()
        deduped: list[tuple[int | None, str, str]] = []
        for num, title, ch_url in raw_chapters:
            if ch_url not in seen_urls:
                seen_urls.add(ch_url)
                deduped.append((num, title, ch_url))

        # Check if chapters are in descending order (e.g. latest chapter first)
        if len(deduped) >= 2:
            first_num = deduped[0][0]
            last_num = deduped[-1][0]
            if first_num is not None and last_num is not None and first_num > last_num:
                deduped.reverse()

        # Build final ChapterInfo list
        chapters: list[ChapterInfo] = []
        for idx, (num, title, ch_url) in enumerate(deduped, start=1):
            ch_num = num if num is not None else idx
            ch_title = title if title else f"Chapter {ch_num}"
            chapters.append(ChapterInfo(
                chapter_number=ch_num,
                title=ch_title,
                url=ch_url,
            ))

        return chapters

    def _extract_chapters_from_soup(
        self, soup: BeautifulSoup, novel_slug: str
    ) -> list[tuple[int | None, str, str]]:
        """Extract raw (chapter_num, title, url) tuples from a BeautifulSoup object."""
        container_selectors = [
            "#list-chapter",
            ".list-chapter",
            ".chapter-list",
            "ul.list-chapter",
            "#chapters",
            ".panel-chapters",
            ".list-chapters",
            ".chapters",
            "div[id*='chapter']",
            "div[class*='chapter-list']",
            "div.chp-list",
            ".content-list",
        ]

        ch_links: list[Tag] = []
        for sel in container_selectors:
            container = soup.select_one(sel)
            if container:
                links = container.select("a")
                if links:
                    ch_links = links
                    break

        if not ch_links:
            # Fallback: select all links matching the chapter pattern
            if novel_slug:
                pat = rf"/book/{re.escape(novel_slug)}/([^/?#]+)"
                ch_links = [
                    a for a in soup.select("a[href]")
                    if re.search(pat, a.get("href", ""))
                    and not re.search(r"/(?:chapters|reviews|comments)/?$", a.get("href", ""))
                ]
            else:
                ch_links = soup.select("a[href*='/chapter-'], a[href*='/c-'], a[href*='/ch-']")

        raw: list[tuple[int | None, str, str]] = []
        for a in ch_links:
            href = a.get("href", "")
            if not href or href == "#" or "javascript:" in href:
                continue

            # Freemium rule: skip locked or premium chapters
            if a.select_one(".lock, .fa-lock, .icon-lock, .locked, .vip-tag"):
                continue
            classes = " ".join(a.get("class", []))
            if "locked" in classes or "vip" in classes:
                continue

            full_url = self._abs_url(self.base_url, href)

            # Skip the novel overview or /chapters link itself
            if re.search(r"/book/[^/?#]+/?$", full_url) or full_url.rstrip("/").endswith("/chapters"):
                continue

            title = a.get_text(strip=True) or a.get("title", "").strip()
            num = self._extract_chapter_number(title, full_url)

            raw.append((num, title, full_url))

        return raw

    def _extract_chapter_number(self, text: str, url: str = "") -> int | None:
        """Extract a numeric chapter number from title text or URL."""
        # 1. Search in title text
        m = re.search(r"(?:chapter|ch\.?)\s*(\d+)", text, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass

        # Pure starting number like "12. Chapter Title"
        m = re.search(r"^\s*(\d+)\s*[:.\-]", text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass

        # 2. Search in URL
        if url:
            m = re.search(r"chapter-?(\d+)", url, re.IGNORECASE)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    pass

            m = re.search(r"/c(\d+)(?:-|$)", url, re.IGNORECASE)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    pass

            m = re.search(r"-(\d+)$", url)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    pass

        return None

    def _find_max_page(self, soup: BeautifulSoup) -> int:
        """Detect the maximum page number from pagination links, if any."""
        max_page = 1
        for a in soup.select(".pagination a, ul.pagination li a, .pager a, div.pages a, a[href*='page=']"):
            href = a.get("href", "")
            m = re.search(r"[?&]page=(\d+)", href)
            if m:
                try:
                    max_page = max(max_page, int(m.group(1)))
                except ValueError:
                    pass
            text = a.get_text(strip=True)
            if text.isdigit():
                try:
                    max_page = max(max_page, int(text))
                except ValueError:
                    pass
        return max_page

    # ──────────────────────────────────────────
    # Chapter Content
    # ──────────────────────────────────────────
    def get_chapter_content(self, url: str) -> str:
        """Fetch the text content of a single chapter at *url*."""
        soup = self._soup(url)

        # Find main reading div
        content_el: Tag | None = None
        content_selectors = [
            "#chapter-content",
            ".chapter-content",
            "#chapter-text",
            ".chapter-text",
            ".reading-content",
            "#reading-content",
            ".content-inner",
            "div.chapter-body",
            ".entry-content",
            "#content",
            ".text-left",
            ".reader-content",
            "div[class*='chapter-content']",
            "div[id*='chapter-content']",
            "div.content",
        ]
        for sel in content_selectors:
            found = soup.select_one(sel)
            if found:
                content_el = found
                break

        if content_el is None:
            content_el = soup.select_one("article") or soup.find("body")

        if content_el is None:
            return ""

        # Decompose unwanted elements before extracting text
        unwanted_selectors = [
            "script",
            "style",
            "noscript",
            "iframe",
            ".ads",
            ".ad",
            ".advertisement",
            ".ad-container",
            ".adsbygoogle",
            ".chapter-nav",
            ".chap-nav",
            ".navigation",
            ".btn-group",
            ".btn",
            ".report-chapter",
            ".social-share",
            ".share-buttons",
            ".alert",
            "div[class*='ad-']",
            "div[id*='ad-']",
            "div[class*='advert']",
        ]
        for sel in unwanted_selectors:
            for tag in content_el.select(sel):
                tag.decompose()

        text = self._clean_text(content_el)

        # Remove domain promotion and error-reporting watermark lines
        cleaned_lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if re.search(
                r"^(?:read\s+(?:latest\s+)?chapters?\s+at|visit)\s+novelfire\.net",
                stripped,
                re.IGNORECASE,
            ):
                continue
            if re.search(
                r"^if\s+you\s+(?:find|notice)\s+any\s+errors.*(?:report|let\s+us\s+know)",
                stripped,
                re.IGNORECASE,
            ):
                continue
            if re.search(r"^chapter\s+\d+.*novelfire\.net", stripped, re.IGNORECASE):
                continue
            cleaned_lines.append(line)

        result = "\n".join(cleaned_lines).strip()
        return result if result else text
