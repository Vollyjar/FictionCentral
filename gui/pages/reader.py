"""
WebNovel Scraper — Reader Page

Displays chapter text with prev/next navigation, chapter selector, and
auto-save of reading position.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import customtkinter as ctk

from database.db import get_session
from database.models import Chapter, Novel, ReadingProgress
from gui.styles import COLORS, FONTS, PADDING

if TYPE_CHECKING:
    from gui.app import App


class ReaderPage(ctk.CTkFrame):
    """Clean chapter reader with navigation controls."""

    def __init__(self, parent: ctk.CTkFrame, app: "App") -> None:
        super().__init__(parent, fg_color=COLORS["bg_reader"])
        self.app = app
        self._novel_id: int = 0
        self._current_chapter: int = 1
        self._total_chapters: int = 0
        self._chapter_numbers: list[int] = []
        self._font_size: int = 16
        self._build_ui()

    def _build_ui(self) -> None:
        # ── Top bar: title + navigation ──
        top = ctk.CTkFrame(self, fg_color=COLORS["bg_sidebar"], height=56, corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)

        inner_top = ctk.CTkFrame(top, fg_color="transparent")
        inner_top.pack(fill="both", expand=True, padx=PADDING, pady=4)

        # Back button
        ctk.CTkButton(
            inner_top, text="← Library", font=FONTS["body"], width=90,
            corner_radius=6, fg_color="transparent",
            hover_color=COLORS["bg_card"],
            text_color=COLORS["accent"],
            command=lambda: self.app.show_page("library"),
        ).pack(side="left")

        # Novel title
        self._title_label = ctk.CTkLabel(
            inner_top, text="", font=FONTS["subheading"],
            text_color=COLORS["fg_primary"],
        )
        self._title_label.pack(side="left", padx=PADDING)

        # Font size & Export controls
        controls_frame = ctk.CTkFrame(inner_top, fg_color="transparent")
        controls_frame.pack(side="right")
        ctk.CTkButton(
            controls_frame, text="Export EPUB", width=95, height=30,
            font=FONTS["body_small"], corner_radius=6,
            fg_color=COLORS["success"],
            command=self._on_export_epub,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            controls_frame, text="A-", width=36, height=30,
            font=FONTS["body"], corner_radius=4,
            command=self._decrease_font,
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            controls_frame, text="A+", width=36, height=30,
            font=FONTS["body"], corner_radius=4,
            command=self._increase_font,
        ).pack(side="left", padx=2)

        # ── Chapter navigation bar ──
        nav = ctk.CTkFrame(self, fg_color=COLORS["bg_sidebar"], height=44, corner_radius=0)
        nav.pack(fill="x")
        nav.pack_propagate(False)

        nav_inner = ctk.CTkFrame(nav, fg_color="transparent")
        nav_inner.pack(fill="both", expand=True, padx=PADDING)

        self._prev_btn = ctk.CTkButton(
            nav_inner, text="◀ Previous", font=FONTS["button"], width=100,
            corner_radius=6, fg_color=COLORS["accent"],
            command=self._prev_chapter,
        )
        self._prev_btn.pack(side="left")

        self._chapter_label = ctk.CTkLabel(
            nav_inner, text="Chapter 1 / 1",
            font=FONTS["body"],
            text_color=COLORS["fg_secondary"],
        )
        self._chapter_label.pack(side="left", expand=True)

        # Chapter selector
        self._chapter_selector = ctk.CTkComboBox(
            nav_inner, values=["1"], width=100, height=30,
            font=FONTS["body_small"], state="readonly",
            command=self._on_chapter_select,
        )
        self._chapter_selector.pack(side="left", padx=8)

        self._next_btn = ctk.CTkButton(
            nav_inner, text="Next ▶", font=FONTS["button"], width=100,
            corner_radius=6, fg_color=COLORS["accent"],
            command=self._next_chapter,
        )
        self._next_btn.pack(side="left")

        # ── Text content area ──
        self._textbox = ctk.CTkTextbox(
            self, font=("Georgia", self._font_size), wrap="word",
            fg_color=COLORS["bg_reader"],
            text_color=COLORS["fg_primary"],
            activate_scrollbars=True,
            padx=40, pady=20,
        )
        self._textbox.pack(fill="both", expand=True)

    # ──────────────────────────────────────────
    # Public interface
    # ──────────────────────────────────────────
    def load_novel(self, novel_id: int, chapter_number: int = 1) -> None:
        """Load a novel and display the given chapter."""
        self._novel_id = novel_id
        with get_session() as session:
            novel = session.get(Novel, novel_id)
            if not novel:
                return
            self._title_label.configure(text=novel.title)

            # Get available chapters
            chapters = (
                session.query(Chapter)
                .filter_by(novel_id=novel_id, is_downloaded=True)
                .order_by(Chapter.chapter_number)
                .all()
            )
            self._chapter_numbers = [c.chapter_number for c in chapters]
            self._total_chapters = len(self._chapter_numbers)
            ch_numbers = [str(num) for num in self._chapter_numbers]

            if ch_numbers:
                self._chapter_selector.configure(values=ch_numbers)
            else:
                self._chapter_selector.configure(values=["—"])

        # Default to first available chapter if requested chapter isn't in downloaded list
        target_ch = chapter_number
        if self._chapter_numbers and target_ch not in self._chapter_numbers:
            target_ch = self._chapter_numbers[0]
        self._load_chapter(target_ch)

    def _load_chapter(self, chapter_number: int) -> None:
        self._current_chapter = chapter_number

        with get_session() as session:
            chapter = (
                session.query(Chapter)
                .filter_by(novel_id=self._novel_id, chapter_number=chapter_number)
                .first()
            )

            self._textbox.configure(state="normal")
            self._textbox.delete("1.0", "end")

            if chapter and chapter.is_downloaded and chapter.content:
                title = chapter.title or f"Chapter {chapter_number}"
                content_text = chapter.content
                if any(tag in content_text for tag in ["<p", "<div", "<br", "<em", "<strong"]):
                    from bs4 import BeautifulSoup
                    bs = BeautifulSoup(content_text, "lxml")
                    for br in bs.find_all(["br", "p"]):
                        br.insert_before("\n")
                    for hr in bs.find_all("hr"):
                        hr.replace_with("\n\n* * *\n\n")
                    content_text = bs.get_text(separator="\n")
                    content_text = re.sub(r"\n{3,}", "\n\n", content_text).strip()
                self._textbox.insert("1.0", f"{title}\n\n{content_text}")
            else:
                self._textbox.insert("1.0", f"Chapter {chapter_number} has not been downloaded yet.")

            self._textbox.configure(state="disabled")
            self._textbox.yview_moveto(0.0)

        # Update navigation controls
        if self._chapter_numbers and chapter_number in self._chapter_numbers:
            idx = self._chapter_numbers.index(chapter_number)
            self._chapter_label.configure(text=f"Chapter {chapter_number} ({idx + 1}/{len(self._chapter_numbers)})")
            self._chapter_selector.set(str(chapter_number))
            self._prev_btn.configure(state="normal" if idx > 0 else "disabled")
            self._next_btn.configure(state="normal" if idx < len(self._chapter_numbers) - 1 else "disabled")
        else:
            self._chapter_label.configure(text=f"Chapter {chapter_number}")
            self._chapter_selector.set(str(chapter_number))
            self._prev_btn.configure(state="disabled")
            self._next_btn.configure(state="disabled")

        # Save reading progress
        self._save_progress(chapter_number)

    def _save_progress(self, chapter_number: int) -> None:
        with get_session() as session:
            progress = session.query(ReadingProgress).filter_by(novel_id=self._novel_id).first()
            if not progress:
                progress = ReadingProgress(novel_id=self._novel_id)
                session.add(progress)
            progress.last_chapter_read = chapter_number
            progress.last_read_at = datetime.now(timezone.utc)
            session.commit()

    # ──────────────────────────────────────────
    # Navigation
    # ──────────────────────────────────────────
    def _prev_chapter(self) -> None:
        if self._chapter_numbers and self._current_chapter in self._chapter_numbers:
            idx = self._chapter_numbers.index(self._current_chapter)
            if idx > 0:
                self._load_chapter(self._chapter_numbers[idx - 1])

    def _next_chapter(self) -> None:
        if self._chapter_numbers and self._current_chapter in self._chapter_numbers:
            idx = self._chapter_numbers.index(self._current_chapter)
            if idx < len(self._chapter_numbers) - 1:
                self._load_chapter(self._chapter_numbers[idx + 1])

    def _on_chapter_select(self, value: str) -> None:
        try:
            ch = int(value)
            self._load_chapter(ch)
        except ValueError:
            pass

    # ──────────────────────────────────────────
    # Font size
    # ──────────────────────────────────────────
    def _increase_font(self) -> None:
        self._font_size = min(self._font_size + 2, 32)
        self._textbox.configure(font=("Georgia", self._font_size))

    def _decrease_font(self) -> None:
        self._font_size = max(self._font_size - 2, 10)
        self._textbox.configure(font=("Georgia", self._font_size))

    # ──────────────────────────────────────────
    # Export EPUB
    # ──────────────────────────────────────────
    def _on_export_epub(self) -> None:
        if not self._novel_id:
            return
        import threading
        orig_text = self._title_label.cget("text")
        self._title_label.configure(text="⏳ Generating EPUB with original formatting…")

        def worker():
            from utils.export import export_to_epub
            try:
                with get_session() as session:
                    novel = session.get(Novel, self._novel_id)
                    if not novel:
                        return
                    path = export_to_epub(novel)
                self.after(0, lambda p=path: self._title_label.configure(text=f"✅ Saved to: {p.name}"))
                self.after(4000, lambda: self._title_label.configure(text=orig_text))
            except Exception as exc:
                err_msg = str(exc)
                self.after(0, lambda msg=err_msg: self._title_label.configure(text=f"❌ Error: {msg}"))
                self.after(4000, lambda: self._title_label.configure(text=orig_text))

        threading.Thread(target=worker, daemon=True).start()
