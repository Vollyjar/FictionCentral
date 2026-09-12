"""
WebNovel Scraper — Recommendations Page

Genre-based discovery with filtering across all supported sites.
"""
from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING

import customtkinter as ctk

from config import PREFERRED_GENRES, ALL_GENRES
from database.db import get_session
from database.models import Novel
from gui.styles import COLORS, FONTS, PADDING

if TYPE_CHECKING:
    from gui.app import App


class RecommendationsPage(ctk.CTkFrame):
    """Genre-filtered recommendations and discovery."""

    def __init__(self, parent: ctk.CTkFrame, app: "App") -> None:
        super().__init__(parent, fg_color=COLORS["bg_content"])
        self.app = app
        self._selected_genres: set[str] = set(PREFERRED_GENRES)
        self._build_ui()

    def _build_ui(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=PADDING * 2, pady=(PADDING * 2, PADDING))

        ctk.CTkLabel(
            header, text="⭐ Discover", font=FONTS["heading"],
            text_color=COLORS["fg_primary"]
        ).pack(anchor="w")
        ctk.CTkLabel(
            header, text="Find novels matching your favourite genres",
            font=FONTS["body_small"],
            text_color=COLORS["fg_muted"]
        ).pack(anchor="w")

        # Genre checkboxes
        genre_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_sidebar"], corner_radius=10)
        genre_frame.pack(fill="x", padx=PADDING * 2, pady=PADDING)

        ctk.CTkLabel(
            genre_frame, text="Genres:", font=FONTS["body"],
            text_color=COLORS["fg_primary"]
        ).pack(anchor="w", padx=PADDING, pady=(PADDING, 4))

        checks_frame = ctk.CTkFrame(genre_frame, fg_color="transparent")
        checks_frame.pack(fill="x", padx=PADDING, pady=(0, PADDING))

        self._genre_vars: dict[str, ctk.BooleanVar] = {}
        col = 0
        row = 0
        max_cols = 5

        for genre in ALL_GENRES:
            var = ctk.BooleanVar(value=genre in self._selected_genres)
            self._genre_vars[genre] = var
            cb = ctk.CTkCheckBox(
                checks_frame, text=genre, variable=var,
                font=FONTS["body_small"],
                command=self._on_genre_toggle
            )
            cb.grid(row=row, column=col, padx=4, pady=2, sticky="w")
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        # Action buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=PADDING * 2, pady=(0, PADDING))

        ctk.CTkButton(
            btn_row, text="Search Library", font=FONTS["button"],
            corner_radius=8, fg_color=COLORS["accent"],
            command=self._search_library
        ).pack(side="left", padx=(0, 8))

        self._discover_btn = ctk.CTkButton(
            btn_row, text="Discover Online", font=FONTS["button"],
            corner_radius=8, fg_color=COLORS["success"],
            command=self._discover_online
        )
        self._discover_btn.pack(side="left")

        # Status
        self._status = ctk.CTkLabel(
            self, text="", font=FONTS["body_small"],
            text_color=COLORS["fg_muted"]
        )
        self._status.pack(anchor="w", padx=PADDING * 2)

        # Results
        self._results_frame = ctk.CTkScrollableFrame(self, fg_color=COLORS["bg_content"])
        self._results_frame.pack(fill="both", expand=True, padx=PADDING, pady=PADDING)

    def _on_genre_toggle(self) -> None:
        self._selected_genres = {g for g, var in self._genre_vars.items() if var.get()}

    def _search_library(self) -> None:
        """Filter novels in the library by selected genres."""
        for widget in self._results_frame.winfo_children():
            widget.destroy()

        if not self._selected_genres:
            self._status.configure(text="Select at least one genre.")
            return

        with get_session() as session:
            novels = session.query(Novel).filter(Novel.is_in_library == True).all()  # noqa: E712

            matches = []
            for novel in novels:
                novel_genres = set(g.lower() for g in novel.genres)
                selected_lower = set(g.lower() for g in self._selected_genres)
                if novel_genres & selected_lower:
                    matches.append(novel)

            if not matches:
                self._status.configure(text="No library novels match the selected genres.")
                return

            # Sort by rating descending
            matches.sort(key=lambda n: n.rating, reverse=True)
            self._status.configure(text=f"Found {len(matches)} matching novel(s) in library")

            for novel in matches:
                self._create_recommendation_card(novel)

    def _discover_online(self) -> None:
        """Search popular novels online matching selected genres."""
        if not self._selected_genres:
            self._status.configure(text="Select at least one genre.")
            return

        self._discover_btn.configure(state="disabled")
        self._status.configure(text="Searching online…")

        for widget in self._results_frame.winfo_children():
            widget.destroy()

        thread = threading.Thread(target=self._discover_worker, daemon=True)
        thread.start()

    def _discover_worker(self) -> None:
        from scraper import registry
        results = []
        # Pick the first selected genre as search query
        genre_query = next(iter(self._selected_genres), "fantasy")

        for scraper in registry.get_all_scrapers():
            try:
                site_results = scraper.search(genre_query, page=1)
                for r in site_results:
                    r.source_site = r.source_site or scraper.site_name
                results.extend(site_results)
            except Exception:
                continue

        self.after(0, lambda: self._show_discover_results(results))

    def _show_discover_results(self, results: list) -> None:
        self._discover_btn.configure(state="normal")
        if not results:
            self._status.configure(text="No online results found.")
            return

        self._status.configure(text=f"Found {len(results)} result(s) online")

        for r in results[:30]:  # Cap at 30
            self._create_search_result_card(r)

    def _create_recommendation_card(self, novel: Novel) -> None:
        card = ctk.CTkFrame(self._results_frame, fg_color=COLORS["bg_card"],
                            corner_radius=10, height=90)
        card.pack(fill="x", padx=4, pady=4)
        card.pack_propagate(False)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=PADDING, pady=PADDING)

        ctk.CTkLabel(
            inner,
            text=novel.title,
            font=FONTS["subheading"],
            text_color=COLORS["fg_primary"],
            anchor="w",
        ).pack(anchor="w")
        genres_str = ", ".join(novel.genres[:4])
        info = f"by {novel.author}  •  {novel.source_site}  •  {genres_str}"
        ctk.CTkLabel(
            inner,
            text=info,
            font=FONTS["body_small"],
            text_color=COLORS["fg_secondary"],
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkButton(
            inner,
            text="Read",
            font=FONTS["button"],
            width=60,
            corner_radius=6,
            fg_color=COLORS["accent"],
            command=lambda nid=novel.id: self.app.open_reader(nid),
        ).pack(side="right")

    def _create_search_result_card(self, result) -> None:
        card = ctk.CTkFrame(self._results_frame, fg_color=COLORS["bg_card"],
                            corner_radius=10, height=90)
        card.pack(fill="x", padx=4, pady=4)
        card.pack_propagate(False)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=PADDING, pady=PADDING)

        ctk.CTkLabel(
            inner,
            text=result.title,
            font=FONTS["subheading"],
            text_color=COLORS["fg_primary"],
            anchor="w",
        ).pack(anchor="w")
        info = f"by {result.author}  •  {result.source_site}"
        if result.genres:
            info += f"  •  {', '.join(result.genres[:3])}"
        ctk.CTkLabel(
            inner,
            text=info,
            font=FONTS["body_small"],
            text_color=COLORS["fg_secondary"],
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkButton(
            inner,
            text="Add to Library",
            font=FONTS["button"],
            width=110,
            corner_radius=6,
            fg_color=COLORS["success"],
            command=lambda r=result: self._add_result(r),
        ).pack(side="right")

    def _add_result(self, result) -> None:
        from database.models import Novel as NovelModel
        with get_session() as session:
            existing = session.query(NovelModel).filter_by(source_url=result.url).first()
            if existing:
                existing.is_in_library = True
                session.commit()
                self._status.configure(text=f"'{result.title}' is already in library.")
                return

            novel = NovelModel(
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
