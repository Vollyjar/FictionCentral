"""
WebNovel Scraper — Library Page

Displays saved novels in a grid with reading progress and sort options.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from database.db import get_session
from database.models import Novel, ReadingProgress
from gui.styles import COLORS, FONTS, PADDING

if TYPE_CHECKING:
    from gui.app import App


class LibraryPage(ctk.CTkFrame):
    """Grid of saved novels with progress indicators."""

    def __init__(self, parent: ctk.CTkFrame, app: "App") -> None:
        super().__init__(parent, fg_color=COLORS["bg_content"])
        self.app = app
        self._sort_by = "last_read"
        self._build_ui()

    def _build_ui(self) -> None:
        # ── Header ──
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=PADDING * 2, pady=(PADDING * 2, PADDING))

        ctk.CTkLabel(
            header, text="📚 Library", font=FONTS["heading"],
            text_color=COLORS["fg_primary"]
        ).pack(side="left")

        # Sort dropdown
        sort_frame = ctk.CTkFrame(header, fg_color="transparent")
        sort_frame.pack(side="right")
        ctk.CTkLabel(
            sort_frame, text="Sort:", font=FONTS["body_small"],
            text_color=COLORS["fg_muted"]
        ).pack(side="left", padx=(0, 4))
        self._sort_dropdown = ctk.CTkComboBox(
            sort_frame, values=["Last Read", "Date Added", "Title", "Chapters"],
            width=140, height=32, font=FONTS["body_small"], state="readonly",
            command=self._on_sort_change,
        )
        self._sort_dropdown.set("Last Read")
        self._sort_dropdown.pack(side="left")

        # ── Status ──
        self._status = ctk.CTkLabel(
            self, text="", font=FONTS["body_small"],
            text_color=COLORS["fg_muted"]
        )
        self._status.pack(anchor="w", padx=PADDING * 2)

        # ── Scrollable grid ──
        self._grid_frame = ctk.CTkScrollableFrame(self, fg_color=COLORS["bg_content"])
        self._grid_frame.pack(fill="both", expand=True, padx=PADDING, pady=PADDING)

    def on_show(self) -> None:
        """Called when the page is raised. Refresh the library."""
        self._refresh()

    def _on_sort_change(self, value: str) -> None:
        sort_map = {
            "Last Read": "last_read",
            "Date Added": "date_added",
            "Title": "title",
            "Chapters": "chapters",
        }
        self._sort_by = sort_map.get(value, "last_read")
        self._refresh()

    def _refresh(self) -> None:
        # Clear grid
        for widget in self._grid_frame.winfo_children():
            widget.destroy()

        with get_session() as session:
            query = session.query(Novel).filter(Novel.is_in_library == True)  # noqa: E712

            if self._sort_by == "title":
                query = query.order_by(Novel.title)
            elif self._sort_by == "date_added":
                query = query.order_by(Novel.date_added.desc())
            elif self._sort_by == "chapters":
                query = query.order_by(Novel.total_chapters.desc())
            else:  # last_read
                query = query.order_by(Novel.last_updated.desc())

            novels = query.all()

            if not novels:
                self._status.configure(text="Your library is empty. Search for novels to add them!")
                return

            self._status.configure(text=f"{len(novels)} novel(s) in library")

            for novel in novels:
                progress = session.query(ReadingProgress).filter_by(novel_id=novel.id).first()
                self._create_novel_card(novel, progress)

    def _create_novel_card(self, novel: Novel, progress: ReadingProgress | None) -> None:
        card = ctk.CTkFrame(self._grid_frame, fg_color=COLORS["bg_card"],
                            corner_radius=10, height=110)
        card.pack(fill="x", padx=4, pady=4)
        card.pack_propagate(False)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=PADDING, pady=PADDING)

        # Text info
        text_frame = ctk.CTkFrame(inner, fg_color="transparent")
        text_frame.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            text_frame, text=novel.title, font=FONTS["subheading"],
            text_color=COLORS["fg_primary"], anchor="w"
        ).pack(anchor="w")
        ctk.CTkLabel(
            text_frame, text=f"by {novel.author}  •  {novel.source_site}",
            font=FONTS["body_small"], text_color=COLORS["fg_secondary"],
            anchor="w"
        ).pack(anchor="w")

        # Progress bar
        progress_frame = ctk.CTkFrame(text_frame, fg_color="transparent")
        progress_frame.pack(fill="x", pady=(6, 0))

        downloaded = novel.downloaded_chapters or 0
        total = novel.total_chapters or 1
        read_ch = progress.last_chapter_read if progress else 0

        read_pct = min(read_ch / max(total, 1), 1.0)

        pbar = ctk.CTkProgressBar(
            progress_frame, width=200, height=8,
            progress_color=COLORS["accent"]
        )
        pbar.pack(side="left", padx=(0, 8))
        pbar.set(read_pct)
        ctk.CTkLabel(
            progress_frame,
            text=f"Read: {read_ch}/{total}  •  Downloaded: {downloaded}/{total}",
            font=FONTS["body_small"], text_color=COLORS["fg_muted"]
        ).pack(side="left")

        # Buttons
        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(side="right", padx=(PADDING, 0))

        ctk.CTkButton(
            btn_frame, text="Read", font=FONTS["button"], width=75,
            corner_radius=6, fg_color=COLORS["accent"],
            command=lambda: self.app.open_reader(novel.id, max(read_ch, 1))
        ).pack(pady=2)
        ctk.CTkButton(
            btn_frame, text="Export EPUB", font=FONTS["button"], width=90,
            corner_radius=6, fg_color=COLORS["success"],
            command=lambda nid=novel.id: self._export_epub(nid)
        ).pack(pady=2)
        ctk.CTkButton(
            btn_frame, text="Remove", font=FONTS["button"], width=75,
            corner_radius=6, fg_color=COLORS["error"],
            command=lambda nid=novel.id: self._remove_novel(nid)
        ).pack(pady=2)

    def _export_epub(self, novel_id: int) -> None:
        """Export the novel to an EPUB file asynchronously without freezing GUI."""
        import threading
        self._status.configure(text="⏳ Generating EPUB with original publishing formatting…")

        def worker():
            from utils.export import export_to_epub
            try:
                with get_session() as session:
                    novel = session.get(Novel, novel_id)
                    if not novel:
                        return
                    title = novel.title
                    path = export_to_epub(novel)
                self.after(0, lambda p=path, t=title: self._status.configure(text=f"✅ Exported '{t}' to: {p}"))
            except Exception as exc:
                err_msg = str(exc)
                self.after(0, lambda msg=err_msg: self._status.configure(text=f"❌ EPUB Export error: {msg}"))

        threading.Thread(target=worker, daemon=True).start()

    def _remove_novel(self, novel_id: int) -> None:
        with get_session() as session:
            novel = session.get(Novel, novel_id)
            if novel:
                novel.is_in_library = False
                session.commit()
        self._refresh()
