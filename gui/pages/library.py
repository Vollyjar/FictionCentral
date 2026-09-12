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

        # Download all incomplete button
        self._download_all_btn = ctk.CTkButton(
            header, text="⬇️ Download All Incomplete", font=FONTS["button"],
            fg_color=COLORS["accent"], height=32, corner_radius=8,
            command=self._on_download_all_incomplete,
        )
        self._download_all_btn.pack(side="left", padx=(16, 0))

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
        try:
            self._grid_frame._parent_canvas.configure(yscrollincrement=8)
        except Exception:
            pass

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

            incomplete_count = sum(1 for n in novels if (n.downloaded_chapters or 0) < (n.total_chapters or 0))
            if incomplete_count > 0:
                self._status.configure(
                    text=f"{len(novels)} novel(s) in library ({incomplete_count} incomplete — ready to download)"
                )
            else:
                self._status.configure(text=f"{len(novels)} novel(s) in library (all downloaded)")

            for novel in novels:
                progress = session.query(ReadingProgress).filter_by(novel_id=novel.id).first()
                self._create_novel_card(novel, progress)

    def _create_novel_card(self, novel: Novel, progress: ReadingProgress | None) -> None:
        # Flat card without nested transparent CTkFrames to eliminate horizontal layer tearing
        card = ctk.CTkFrame(self._grid_frame, fg_color=COLORS["bg_card"], corner_radius=10)
        card.pack(fill="x", padx=4, pady=4)

        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=0)

        # Left Column: Info & Progress
        left_box = ctk.CTkFrame(card, fg_color="transparent")
        left_box.grid(row=0, column=0, sticky="nsew", padx=(PADDING, 8), pady=PADDING)

        ctk.CTkLabel(
            left_box, text=novel.title, font=FONTS["subheading"],
            text_color=COLORS["fg_primary"], anchor="w"
        ).pack(anchor="w")
        ctk.CTkLabel(
            left_box, text=f"by {novel.author}  •  {novel.source_site}",
            font=FONTS["body_small"], text_color=COLORS["fg_secondary"],
            anchor="w"
        ).pack(anchor="w")

        downloaded = novel.downloaded_chapters or 0
        total = novel.total_chapters or 1
        read_ch = progress.last_chapter_read if progress else 0
        read_pct = min(read_ch / max(total, 1), 1.0)

        p_row = ctk.CTkFrame(left_box, fg_color="transparent")
        p_row.pack(fill="x", pady=(6, 0))

        pbar = ctk.CTkProgressBar(p_row, width=180, height=8, progress_color=COLORS["accent"])
        pbar.pack(side="left", padx=(0, 8))
        pbar.set(read_pct)

        ctk.CTkLabel(
            p_row,
            text=f"Read: {read_ch}/{total}  •  Downloaded: {downloaded}/{total}",
            font=FONTS["body_small"], text_color=COLORS["fg_muted"]
        ).pack(side="left")

        # Right Column: Action Buttons (2x2 grid)
        btn_grid = ctk.CTkFrame(card, fg_color="transparent")
        btn_grid.grid(row=0, column=1, sticky="e", padx=(0, PADDING), pady=PADDING)

        # 1. Read Button
        ctk.CTkButton(
            btn_grid, text="Read", font=FONTS["button"], width=80, height=28,
            corner_radius=6, fg_color=COLORS["accent"],
            command=lambda: self.app.open_reader(novel.id, max(read_ch, 1))
        ).grid(row=0, column=0, padx=3, pady=3)

        # 2. Download / Update Button
        is_incomplete = downloaded < total
        dl_text = "⬇️ Download" if downloaded == 0 else ("🔄 Resume" if is_incomplete else "🔄 Check")
        dl_color = COLORS["success"] if is_incomplete else COLORS["bg_sidebar"]
        ctk.CTkButton(
            btn_grid, text=dl_text, font=FONTS["button"], width=95, height=28,
            corner_radius=6, fg_color=dl_color,
            command=lambda nid=novel.id: self._on_download_novel(nid)
        ).grid(row=0, column=1, padx=3, pady=3)

        # 3. Export EPUB Button
        ctk.CTkButton(
            btn_grid, text="Export EPUB", font=FONTS["button"], width=80, height=28,
            corner_radius=6, fg_color=COLORS["bg_sidebar"], hover_color=COLORS["accent"],
            command=lambda nid=novel.id: self._export_epub(nid)
        ).grid(row=1, column=0, padx=3, pady=3)

        # 4. Remove Button
        ctk.CTkButton(
            btn_grid, text="Remove", font=FONTS["button"], width=95, height=28,
            corner_radius=6, fg_color=COLORS["error"],
            command=lambda nid=novel.id: self._remove_novel(nid)
        ).grid(row=1, column=1, padx=3, pady=3)

    def _on_download_novel(self, novel_id: int) -> None:
        """Enqueue single novel for downloading directly from Library."""
        import threading
        self._status.configure(text="⏳ Fetching chapter list and adding to download queue…")

        def worker():
            job = self.app.download_engine.enqueue_novel(novel_id)
            if job:
                msg = f"✅ Enqueued '{job.novel_title}' ({job.total_chapters} chapters) for download"
            else:
                msg = "❌ Failed to enqueue novel for download"
            self.after(0, lambda m=msg: self._status.configure(text=m))
            self.after(0, self._refresh)

        threading.Thread(target=worker, daemon=True).start()

    def _on_download_all_incomplete(self) -> None:
        """Enqueue all incomplete library novels in batch."""
        count = self.app.download_engine.enqueue_all_incomplete()
        if count > 0:
            self._status.configure(
                text=f"⏳ Enqueued {count} incomplete novel(s) to download queue."
            )
            self.app.show_page("downloads")
        else:
            self._status.configure(text="All novels in your library are already fully downloaded!")

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
        self.app.download_engine.cancel(novel_id)
        from database.models import DownloadQueueItem
        with get_session() as session:
            novel = session.get(Novel, novel_id)
            if novel:
                novel.is_in_library = False
                session.query(DownloadQueueItem).filter_by(novel_id=novel_id).delete()
                session.commit()
        self._refresh()
