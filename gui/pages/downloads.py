"""
WebNovel Scraper — Downloads Page

Shows active downloads with progress bars, speed, and queue management.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from gui.styles import COLORS, FONTS, PADDING
from scraper.engine import DownloadJob, DownloadStatus

if TYPE_CHECKING:
    from gui.app import App


class DownloadsPage(ctk.CTkFrame):
    """Download queue with progress bars and management controls."""

    def __init__(self, parent: ctk.CTkFrame, app: "App") -> None:
        super().__init__(parent, fg_color=COLORS["bg_content"])
        self.app = app
        self._job_widgets: dict[int, dict] = {}  # novel_id → widget dict
        self._build_ui()

        # Register callback with download engine
        self.app.download_engine.add_callback(self._on_progress)

    def _build_ui(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=PADDING * 2, pady=(PADDING * 2, PADDING))

        ctk.CTkLabel(
            header,
            text="⬇️ Downloads",
            font=FONTS["heading"],
            text_color=COLORS["fg_primary"],
        ).pack(side="left")

        # Status
        self._status = ctk.CTkLabel(
            self,
            text="No active downloads",
            font=FONTS["body_small"],
            text_color=COLORS["fg_muted"],
        )
        self._status.pack(anchor="w", padx=PADDING * 2)

        # Scrollable download list
        self._list_frame = ctk.CTkScrollableFrame(self, fg_color=COLORS["bg_content"])
        self._list_frame.pack(fill="both", expand=True, padx=PADDING, pady=PADDING)

    def on_show(self) -> None:
        """Refresh the download list when page is shown."""
        self._refresh()

    def _refresh(self) -> None:
        queue = self.app.download_engine.get_queue()
        if not queue:
            self._status.configure(text="No downloads in queue.")
            return

        active = sum(1 for j in queue if j.status in (DownloadStatus.DOWNLOADING, DownloadStatus.QUEUED))
        completed = sum(1 for j in queue if j.status == DownloadStatus.COMPLETED)
        self._status.configure(text=f"{active} active, {completed} completed, {len(queue)} total")

        # Create/update widgets for each job
        for job in queue:
            self._update_job_widget(job)

    def _update_job_widget(self, job: DownloadJob) -> None:
        """Create or update the widget for a download job."""
        if job.novel_id not in self._job_widgets:
            self._create_job_widget(job)
        else:
            widgets = self._job_widgets[job.novel_id]
            total = max(job.total_chapters, 1)
            pct = job.downloaded_count / total
            widgets["progress_bar"].set(pct)
            widgets["progress_label"].configure(
                text=f"{job.downloaded_count}/{job.total_chapters} chapters"
            )
            widgets["status_label"].configure(text=self._status_text(job))
            if job.current_chapter:
                widgets["current_label"].configure(text=f"Current: {job.current_chapter}")
            self._update_action_buttons(widgets["btn_frame"], job)

    def _create_job_widget(self, job: DownloadJob) -> None:
        card = ctk.CTkFrame(self._list_frame, fg_color=COLORS["bg_card"],
                            corner_radius=10, height=105)
        card.pack(fill="x", padx=4, pady=4)
        card.pack_propagate(False)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=PADDING, pady=PADDING)

        # Left: info
        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            info, text=job.novel_title, font=FONTS["subheading"],
            text_color=COLORS["fg_primary"], anchor="w"
        ).pack(anchor="w")

        status_label = ctk.CTkLabel(
            info, text=self._status_text(job),
            font=FONTS["body_small"],
            text_color=COLORS["fg_secondary"], anchor="w"
        )
        status_label.pack(anchor="w")

        current_label = ctk.CTkLabel(
            info, text="", font=FONTS["body_small"],
            text_color=COLORS["fg_muted"], anchor="w"
        )
        current_label.pack(anchor="w")

        # Progress
        progress_frame = ctk.CTkFrame(info, fg_color="transparent")
        progress_frame.pack(fill="x", pady=(4, 0))

        total = max(job.total_chapters, 1)
        pct = job.downloaded_count / total

        progress_bar = ctk.CTkProgressBar(
            progress_frame, width=300, height=10,
            progress_color=COLORS["accent"]
        )
        progress_bar.set(pct)
        progress_bar.pack(side="left", padx=(0, 8))

        progress_label = ctk.CTkLabel(
            progress_frame,
            text=f"{job.downloaded_count}/{job.total_chapters} chapters",
            font=FONTS["body_small"],
            text_color=COLORS["fg_muted"]
        )
        progress_label.pack(side="left")

        # Right: action buttons
        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(side="right")
        self._update_action_buttons(btn_frame, job)

        self._job_widgets[job.novel_id] = {
            "card": card,
            "progress_bar": progress_bar,
            "progress_label": progress_label,
            "status_label": status_label,
            "current_label": current_label,
            "btn_frame": btn_frame,
        }

    def _update_action_buttons(self, btn_frame: ctk.CTkFrame, job: DownloadJob) -> None:
        for w in btn_frame.winfo_children():
            w.destroy()

        if job.status in (DownloadStatus.DOWNLOADING, DownloadStatus.QUEUED):
            ctk.CTkButton(
                btn_frame, text="Pause", font=FONTS["button"], width=80,
                corner_radius=6, fg_color=COLORS["warning"],
                command=lambda nid=job.novel_id: self._pause(nid)
            ).pack(pady=2)
            ctk.CTkButton(
                btn_frame, text="Cancel", font=FONTS["button"], width=80,
                corner_radius=6, fg_color=COLORS["error"],
                command=lambda nid=job.novel_id: self._cancel(nid)
            ).pack(pady=2)
        elif job.status == DownloadStatus.PAUSED:
            ctk.CTkButton(
                btn_frame, text="Resume", font=FONTS["button"], width=80,
                corner_radius=6, fg_color=COLORS["success"],
                command=lambda nid=job.novel_id: self._resume(nid)
            ).pack(pady=2)
            ctk.CTkButton(
                btn_frame, text="Cancel", font=FONTS["button"], width=80,
                corner_radius=6, fg_color=COLORS["error"],
                command=lambda nid=job.novel_id: self._cancel(nid)
            ).pack(pady=2)
        elif job.status == DownloadStatus.COMPLETED:
            ctk.CTkButton(
                btn_frame, text="📖 Read", font=FONTS["button"], width=85,
                corner_radius=6, fg_color=COLORS["accent"],
                command=lambda nid=job.novel_id: self.app.open_reader(nid)
            ).pack(pady=2)
            ctk.CTkButton(
                btn_frame, text="Export EPUB", font=FONTS["button"], width=85,
                corner_radius=6, fg_color=COLORS["success"],
                command=lambda nid=job.novel_id: self._export_epub(nid)
            ).pack(pady=2)
        elif job.status in (DownloadStatus.FAILED, DownloadStatus.CANCELLED):
            ctk.CTkButton(
                btn_frame, text="🔄 Retry", font=FONTS["button"], width=80,
                corner_radius=6, fg_color=COLORS["warning"],
                command=lambda nid=job.novel_id: self._resume(nid)
            ).pack(pady=2)

    def _export_epub(self, novel_id: int) -> None:
        import threading
        self._status.configure(text="⏳ Exporting EPUB with original formatting…")

        def worker():
            from database.db import get_session
            from database.models import Novel
            from utils.export import export_to_epub
            try:
                with get_session() as session:
                    novel = session.get(Novel, novel_id)
                    if not novel:
                        return
                    path = export_to_epub(novel)
                self.after(0, lambda p=path: self._status.configure(text=f"✅ Exported to: {p.name}"))
            except Exception as exc:
                err_msg = str(exc)
                self.after(0, lambda msg=err_msg: self._status.configure(text=f"❌ EPUB Export error: {msg}"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_progress(self, job: DownloadJob) -> None:
        """Called from the download engine thread — schedule UI update on main thread."""
        self.after(0, lambda: self._update_job_widget(job))

    def _pause(self, novel_id: int) -> None:
        self.app.download_engine.pause(novel_id)
        self._refresh()

    def _resume(self, novel_id: int) -> None:
        self.app.download_engine.resume(novel_id)
        self._refresh()

    def _cancel(self, novel_id: int) -> None:
        self.app.download_engine.cancel(novel_id)
        self._refresh()

    @staticmethod
    def _status_text(job: DownloadJob) -> str:
        status_map = {
            DownloadStatus.QUEUED: "⏳ Queued",
            DownloadStatus.DOWNLOADING: "⬇️ Downloading…",
            DownloadStatus.PAUSED: "⏸️ Paused",
            DownloadStatus.COMPLETED: "✅ Completed",
            DownloadStatus.FAILED: "❌ Failed",
            DownloadStatus.CANCELLED: "🚫 Cancelled",
        }
        text = status_map.get(job.status, "Unknown")
        if job.error_message and job.status == DownloadStatus.FAILED:
            text += f" — {job.error_message}"
        return text
