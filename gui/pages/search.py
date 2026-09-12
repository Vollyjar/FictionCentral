"""
WebNovel Scraper — Search Page

Allows searching across all supported sites with genre filtering.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import customtkinter as ctk

from gui.styles import COLORS, FONTS, PADDING

if TYPE_CHECKING:
    from gui.app import App


# Site display names for the dropdown
SITE_OPTIONS = [
    "All Sites",
    "Royal Road",
    "Scribble Hub",
    "FanFiction.net",
    "Archive of Our Own",
    "Webnovel",
    "Wattpad",
    "Tapas",
    "Inkitt",
    "Novelfire",
    "SpaceBattles / SV",
]

SITE_KEY_MAP = {
    "All Sites": "all",
    "Royal Road": "royalroad",
    "Scribble Hub": "scribblehub",
    "FanFiction.net": "fanfiction",
    "Archive of Our Own": "ao3",
    "Webnovel": "webnovel",
    "Wattpad": "wattpad",
    "Tapas": "tapas",
    "Inkitt": "inkitt",
    "Novelfire": "novelfire",
    "SpaceBattles / SV": "spacebattles",
}


class SearchPage(ctk.CTkFrame):
    """Search page with search bar, site selector, and results grid."""

    def __init__(self, parent: ctk.CTkFrame, app: "App") -> None:
        super().__init__(parent, fg_color=COLORS["bg_content"])
        self.app = app
        self._results: list[dict] = []

        self._build_ui()

    def _build_ui(self) -> None:
        # ── Top container ──
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=PADDING * 2, pady=(PADDING * 2, PADDING))

        # Title
        ctk.CTkLabel(
            top,
            text="🔍 Search & Direct Link Fetcher",
            font=FONTS["heading"],
            text_color=COLORS["fg_primary"],
        ).pack(anchor="w")

        # ── 1. Dedicated Direct Link Search Bar ──
        link_box = ctk.CTkFrame(top, fg_color=COLORS["bg_card"], corner_radius=10)
        link_box.pack(fill="x", pady=(PADDING, 6))

        link_inner = ctk.CTkFrame(link_box, fg_color="transparent")
        link_inner.pack(fill="x", padx=PADDING, pady=PADDING)

        ctk.CTkLabel(
            link_inner,
            text="🔗 Direct Link Search (Paste Book, Novel, or Fanfiction URL):",
            font=FONTS["subheading"],
            text_color=COLORS["accent"],
            anchor="w",
        ).pack(anchor="w", pady=(0, 6))

        link_row = ctk.CTkFrame(link_inner, fg_color="transparent")
        link_row.pack(fill="x")

        self._link_entry = ctk.CTkEntry(
            link_row,
            placeholder_text="Paste link (Royal Road, FanFiction, AO3, Webnovel, Wattpad, Scribble Hub, SpaceBattles…)",
            font=FONTS["body"],
            height=40,
            corner_radius=8,
        )
        self._link_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._link_entry.bind("<Return>", lambda e: self._on_fetch_link())

        self._paste_btn = ctk.CTkButton(
            link_row, text="📋 Paste", font=FONTS["button"], width=80,
            height=40, corner_radius=8, fg_color=COLORS["bg_sidebar"],
            hover_color=COLORS["bg_card"],
            command=self._on_paste_link,
        )
        self._paste_btn.pack(side="left", padx=(0, 8))

        self._fetch_link_btn = ctk.CTkButton(
            link_row, text="🔗 Fetch by Link", font=FONTS["button"], width=130,
            height=40, corner_radius=8, fg_color=COLORS["accent"],
            command=self._on_fetch_link,
        )
        self._fetch_link_btn.pack(side="left")

        # ── 2. Title & Keyword Search Bar ──
        title_box = ctk.CTkFrame(top, fg_color="transparent")
        title_box.pack(fill="x", pady=(2, 0))

        ctk.CTkLabel(
            title_box,
            text="🔤 Search by Title / Keyword:",
            font=FONTS["body_small"],
            text_color=COLORS["fg_secondary"],
            anchor="w",
        ).pack(anchor="w", pady=(0, 4))

        search_row = ctk.CTkFrame(title_box, fg_color="transparent")
        search_row.pack(fill="x")

        self._search_entry = ctk.CTkEntry(
            search_row, placeholder_text="Search by title, author, or keyword…",
            font=FONTS["body"], height=38, corner_radius=8,
        )
        self._search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._search_entry.bind("<Return>", lambda e: self._on_search())

        self._site_dropdown = ctk.CTkComboBox(
            search_row, values=SITE_OPTIONS, width=180, height=38,
            font=FONTS["body"], state="readonly",
        )
        self._site_dropdown.set("All Sites")
        self._site_dropdown.pack(side="left", padx=(0, 8))

        self._search_btn = ctk.CTkButton(
            search_row, text="🔍 Search", font=FONTS["button"], width=100,
            height=38, corner_radius=8,
            command=self._on_search,
        )
        self._search_btn.pack(side="left")

        # ── Status label ──
        self._status = ctk.CTkLabel(
            self,
            text="",
            font=FONTS["body_small"],
            text_color=COLORS["fg_muted"],
        )
        self._status.pack(anchor="w", padx=PADDING * 2)

        # ── Scrollable results area ──
        self._results_frame = ctk.CTkScrollableFrame(
            self, fg_color=COLORS["bg_content"], corner_radius=0,
        )
        self._results_frame.pack(fill="both", expand=True, padx=PADDING, pady=PADDING)

    # ──────────────────────────────────────────
    # Direct Link Search logic
    # ──────────────────────────────────────────
    def _on_paste_link(self) -> None:
        try:
            clipboard_text = self.clipboard_get().strip()
            if clipboard_text:
                self._link_entry.delete(0, "end")
                self._link_entry.insert(0, clipboard_text)
                self._on_fetch_link()
            else:
                self._status.configure(text="Clipboard is empty.")
        except Exception:
            self._status.configure(text="Could not read clipboard text.")

    def _on_fetch_link(self) -> None:
        raw_url = self._link_entry.get().strip()
        if not raw_url:
            self._status.configure(text="Please paste or enter a direct novel / fanfiction link.")
            return

        self._status.configure(text=f"Analyzing link: {raw_url}…")
        self._fetch_link_btn.configure(state="disabled")
        self._search_btn.configure(state="disabled")

        # Clear old results
        for widget in self._results_frame.winfo_children():
            widget.destroy()

        thread = threading.Thread(target=self._fetch_link_worker, args=(raw_url,), daemon=True)
        thread.start()

    def _fetch_link_worker(self, raw_url: str) -> None:
        from scraper import registry
        from scraper.base import NovelSearchResult

        normalized_url = registry.normalize_novel_url(raw_url)
        scraper = registry.get_scraper_for_url(normalized_url)

        if not scraper:
            err = (
                "❌ Unsupported site or invalid link. Supported: "
                "Royal Road, Scribble Hub, FanFiction.net, AO3, Webnovel, "
                "Wattpad, Tapas, Inkitt, Novelfire, SpaceBattles / SV"
            )
            self.after(0, lambda msg=err: self._status.configure(text=msg))
            self.after(0, lambda: self._fetch_link_btn.configure(state="normal"))
            self.after(0, lambda: self._search_btn.configure(state="normal"))
            return

        try:
            site_name = scraper.site_name.capitalize()
            self.after(0, lambda s=site_name: self._status.configure(text=f"⏳ Fetching novel details from {s}…"))
            details = scraper.get_novel_details(normalized_url)

            # If chapter count wasn't parsed from metadata, try getting chapter list
            chapter_count = details.chapter_count
            if chapter_count <= 0:
                try:
                    chaps = scraper.get_chapter_list(normalized_url)
                    chapter_count = len(chaps)
                except Exception:
                    pass

            result = NovelSearchResult(
                title=details.title or "Untitled",
                url=details.url or normalized_url,
                author=details.author or "Unknown",
                cover_url=details.cover_url or "",
                synopsis=details.synopsis or "",
                source_site=details.source_site or scraper.site_name,
                genres=details.genres or [],
                chapter_count=chapter_count,
                rating=details.rating or 0.0,
                status=details.status or "Unknown",
            )

            self.after(0, lambda r=result: self._display_results([r]))
        except Exception as exc:
            err_msg = str(exc)
            self.after(0, lambda msg=err_msg: self._status.configure(text=f"❌ Failed to fetch novel: {msg}"))
        finally:
            self.after(0, lambda: self._fetch_link_btn.configure(state="normal"))
            self.after(0, lambda: self._search_btn.configure(state="normal"))

    # ──────────────────────────────────────────
    # Title / Keyword Search logic
    # ──────────────────────────────────────────
    def _on_search(self) -> None:
        query = self._search_entry.get().strip()
        if not query:
            return

        # Check if user accidentally entered a URL into the title search bar
        if query.startswith(("http://", "https://", "www.")) or any(
            site in query.lower() for site in [
                "royalroad.com", "scribblehub.com", "fanfiction.net", "archiveofourown.org",
                "webnovel.com", "wattpad.com", "tapas.io", "inkitt.com", "novelfire.net",
                "spacebattles.com", "sufficientvelocity.com", "fichub.net"
            ]
        ):
            self._link_entry.delete(0, "end")
            self._link_entry.insert(0, query)
            self._on_fetch_link()
            return

        site_key = SITE_KEY_MAP.get(self._site_dropdown.get(), "all")
        self._status.configure(text=f"Searching '{query}' on {self._site_dropdown.get()}…")
        self._search_btn.configure(state="disabled")
        self._fetch_link_btn.configure(state="disabled")

        # Clear old results
        for widget in self._results_frame.winfo_children():
            widget.destroy()

        # Run search in background thread
        thread = threading.Thread(target=self._search_worker, args=(query, site_key), daemon=True)
        thread.start()

    def _search_worker(self, query: str, site_key: str) -> None:
        from scraper import registry
        results = []
        try:
            if site_key == "all":
                scrapers = registry.get_all_scrapers()
            else:
                scraper = registry.get_scraper(site_key)
                scrapers = [scraper] if scraper else []

            for scraper in scrapers:
                try:
                    site_results = scraper.search(query, page=1)
                    for r in site_results:
                        r.source_site = r.source_site or scraper.site_name
                    results.extend(site_results)
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).warning("Search failed on %s: %s", scraper.site_name, exc)

        except Exception as exc:
            err_msg = str(exc)
            self.after(0, lambda msg=err_msg: self._status.configure(text=f"Error: {msg}"))
            self.after(0, lambda: self._search_btn.configure(state="normal"))
            self.after(0, lambda: self._fetch_link_btn.configure(state="normal"))
            return

        self.after(0, lambda: self._display_results(results))

    def _display_results(self, results: list) -> None:
        self._search_btn.configure(state="normal")
        self._fetch_link_btn.configure(state="normal")

        if not results:
            self._status.configure(text="No results found.")
            return

        if len(results) == 1:
            r = results[0]
            self._status.configure(
                text=f"✅ Loaded '{r.title}' by {r.author} ({r.chapter_count} chapters) • {r.source_site}"
            )
        else:
            self._status.configure(text=f"Found {len(results)} result(s)")

        for r in results:
            self._create_result_card(r)

    def _create_result_card(self, result) -> None:
        """Create a single result card in the results frame."""
        card = ctk.CTkFrame(self._results_frame, fg_color=COLORS["bg_card"],
                            corner_radius=10, height=130)
        card.pack(fill="x", padx=4, pady=4)
        card.pack_propagate(False)

        # Inner layout
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=PADDING, pady=PADDING)

        # Left: text info
        text_frame = ctk.CTkFrame(inner, fg_color="transparent")
        text_frame.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            text_frame,
            text=result.title,
            font=FONTS["subheading"],
            text_color=COLORS["fg_primary"],
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            text_frame,
            text=f"by {result.author}  •  {result.source_site}",
            font=FONTS["body_small"],
            text_color=COLORS["fg_secondary"],
            anchor="w",
        ).pack(anchor="w")

        info_parts = []
        if result.chapter_count > 0:
            info_parts.append(f"{result.chapter_count} chapters")
        if result.rating > 0:
            info_parts.append(f"★ {result.rating:.1f}")
        if result.status != "Unknown":
            info_parts.append(result.status)
        if result.genres:
            info_parts.append(", ".join(result.genres[:3]))
        if info_parts:
            ctk.CTkLabel(
                text_frame,
                text="  •  ".join(info_parts),
                font=FONTS["body_small"],
                text_color=COLORS["fg_muted"],
                anchor="w",
            ).pack(anchor="w", pady=(4, 0))

        # Right: action buttons
        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(side="right", padx=(PADDING, 0))

        ctk.CTkButton(
            btn_frame, text="Details", font=FONTS["button"], width=110,
            height=28, corner_radius=6, fg_color=COLORS["accent"],
            command=lambda r=result: self._show_details(r),
        ).pack(pady=(0, 3))

        ctk.CTkButton(
            btn_frame, text="Add to Library", font=FONTS["button"], width=110,
            height=28, corner_radius=6, fg_color=COLORS["success"],
            command=lambda r=result: self._add_to_library(r),
        ).pack(pady=(0, 3))

        ctk.CTkButton(
            btn_frame, text="⬇️ Download", font=FONTS["button"], width=110,
            height=28, corner_radius=6, fg_color=COLORS["warning"],
            command=lambda r=result: self._add_and_download(r),
        ).pack()

    def _show_details(self, result) -> None:
        """Open a detail dialog for a search result."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(result.title)
        dialog.geometry("600x500")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        pad = PADDING * 2

        ctk.CTkLabel(
            dialog,
            text=result.title,
            font=FONTS["heading"],
            text_color=COLORS["fg_primary"],
            wraplength=550,
        ).pack(padx=pad, pady=(pad, 4))
        ctk.CTkLabel(
            dialog,
            text=f"by {result.author}  •  {result.source_site}",
            font=FONTS["body"],
            text_color=COLORS["fg_secondary"],
        ).pack(padx=pad)

        if result.synopsis:
            synopsis_box = ctk.CTkTextbox(
                dialog,
                font=FONTS["body"],
                height=200,
                wrap="word",
                activate_scrollbars=True,
            )
            synopsis_box.pack(fill="x", padx=pad, pady=PADDING)
            synopsis_box.insert("1.0", result.synopsis)
            synopsis_box.configure(state="disabled")

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(pady=PADDING)

        ctk.CTkButton(
            btn_row,
            text="Add to Library & Download",
            font=FONTS["button"],
            fg_color=COLORS["success"],
            corner_radius=8,
            command=lambda: self._add_and_download(result, dialog),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row,
            text="Close",
            font=FONTS["button"],
            fg_color=COLORS["fg_muted"],
            corner_radius=8,
            command=dialog.destroy,
        ).pack(side="left", padx=4)

    def _add_to_library(self, result) -> None:
        """Save a novel to the local library."""
        from database.db import get_session
        from database.models import Novel
        import json

        with get_session() as session:
            existing = session.query(Novel).filter_by(source_url=result.url).first()
            if existing:
                existing.is_in_library = True
                session.commit()
                self._status.configure(text=f"'{result.title}' is already in your library.")
                return

            novel = Novel(
                title=result.title,
                author=result.author,
                source_site=result.source_site,
                source_url=result.url,
                synopsis=result.synopsis,
                cover_url=result.cover_url,
                genres_json=json.dumps(result.genres),
                rating=result.rating,
                total_chapters=result.chapter_count,
                status=result.status,
                is_in_library=True,
            )
            session.add(novel)
            session.commit()
            self._status.configure(text=f"Added '{result.title}' to library!")

    def _add_and_download(self, result, dialog=None) -> None:
        """Add to library and start downloading."""
        self._add_to_library(result)
        if dialog:
            dialog.destroy()

        # Trigger download in background
        thread = threading.Thread(target=self._start_download, args=(result,), daemon=True)
        thread.start()

    def _start_download(self, result) -> None:
        from scraper import registry
        from database.db import get_session
        from database.models import Novel

        scraper = registry.get_scraper_for_url(result.url)
        if not scraper:
            self.after(0, lambda: self._status.configure(text="No scraper available for this site."))
            return

        try:
            chapters = scraper.get_chapter_list(result.url)
        except Exception as exc:
            err_msg = str(exc)
            self.after(0, lambda msg=err_msg: self._status.configure(text=f"Failed to get chapters: {msg}"))
            return

        with get_session() as session:
            novel = session.query(Novel).filter_by(source_url=result.url).first()
            if novel:
                novel.total_chapters = len(chapters)
                session.commit()
                self.app.download_engine.enqueue(
                    novel_id=novel.id,
                    novel_title=novel.title,
                    source_url=novel.source_url,
                    scraper=scraper,
                    chapters=chapters,
                )
                self.after(0, lambda: self._status.configure(
                    text=f"Started downloading '{novel.title}' ({len(chapters)} chapters)"))
