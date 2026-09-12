"""
WebNovel Scraper — Main Application Window

CustomTkinter-based GUI with sidebar navigation and swappable content pages.
"""
from __future__ import annotations

import customtkinter as ctk

from config import APP_NAME, APP_VERSION, APPEARANCE_MODE, COLOR_THEME, WINDOW_HEIGHT, WINDOW_WIDTH
from gui.styles import COLORS, FONTS, SIDEBAR_ITEMS, SIDEBAR_WIDTH, PADDING
from gui.pages.search import SearchPage
from gui.pages.library import LibraryPage
from gui.pages.reader import ReaderPage
from gui.pages.downloads import DownloadsPage
from gui.pages.recommendations import RecommendationsPage
from scraper.engine import DownloadEngine


class App(ctk.CTk):
    """Root application window."""

    def __init__(self, download_engine: DownloadEngine) -> None:
        super().__init__()
        self.download_engine = download_engine

        # ── Window setup ──
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(900, 600)
        ctk.set_appearance_mode(APPEARANCE_MODE)
        ctk.set_default_color_theme(COLOR_THEME)

        # ── Layout: sidebar (left) + content (right) ──
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self._sidebar = ctk.CTkFrame(
            self, width=SIDEBAR_WIDTH, corner_radius=0, fg_color=COLORS["bg_sidebar"]
        )
        self._sidebar.grid(row=0, column=0, sticky="nsw")
        self._sidebar.grid_propagate(False)

        # Content area
        self._content = ctk.CTkFrame(self, corner_radius=0, fg_color=COLORS["bg_content"])
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

        # ── Build sidebar buttons ──
        self._sidebar_buttons: dict[str, ctk.CTkButton] = {}
        self._build_sidebar()

        # ── Create pages ──
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._create_pages()

        # ── Show default page ──
        self._active_page: str = ""
        self.show_page("search")

    # ──────────────────────────────────────────
    # Sidebar
    # ──────────────────────────────────────────
    def _build_sidebar(self) -> None:
        # App title at top of sidebar
        title_label = ctk.CTkLabel(
            self._sidebar,
            text=f"📖 {APP_NAME}",
            font=FONTS["subheading"],
            text_color=COLORS["accent"],
        )
        title_label.pack(pady=(20, 30), padx=PADDING)

        for item in SIDEBAR_ITEMS:
            btn = ctk.CTkButton(
                self._sidebar,
                text=f"  {item['icon']}  {item['label']}",
                font=FONTS["sidebar"],
                anchor="w",
                height=44,
                corner_radius=8,
                fg_color="transparent",
                text_color=COLORS["fg_primary"],
                hover_color=COLORS["bg_card"],
                command=lambda k=item["key"]: self.show_page(k),
            )
            btn.pack(fill="x", padx=8, pady=3)
            self._sidebar_buttons[item["key"]] = btn

    # ──────────────────────────────────────────
    # Pages
    # ──────────────────────────────────────────
    def _create_pages(self) -> None:
        self._pages["search"] = SearchPage(self._content, app=self)
        self._pages["library"] = LibraryPage(self._content, app=self)
        self._pages["downloads"] = DownloadsPage(self._content, app=self)
        self._pages["recommendations"] = RecommendationsPage(self._content, app=self)
        self._pages["reader"] = ReaderPage(self._content, app=self)

        for page in self._pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def show_page(self, key: str) -> None:
        """Switch to a page by key."""
        if key == self._active_page:
            return
        # Update sidebar highlight
        for k, btn in self._sidebar_buttons.items():
            if k == key:
                btn.configure(fg_color=COLORS["bg_card"])
            else:
                btn.configure(fg_color="transparent")
        # Raise the page
        self._active_page = key
        page = self._pages.get(key)
        if page:
            page.tkraise()
            # Let the page refresh itself if it has an on_show method
            if hasattr(page, "on_show"):
                page.on_show()

    def open_reader(self, novel_id: int, chapter_number: int = 1) -> None:
        """Open the reader page for a specific novel and chapter."""
        reader: ReaderPage = self._pages["reader"]  # type: ignore
        reader.load_novel(novel_id, chapter_number)
        self.show_page("reader")

    def on_closing(self) -> None:
        """Clean shutdown."""
        self.download_engine.shutdown()
        self.destroy()
