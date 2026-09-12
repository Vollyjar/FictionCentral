"""
WebNovel Scraper — GUI Styles & Theming
"""

# ──────────────────────────────────────────────
# Color palette (dark theme defaults)
# ──────────────────────────────────────────────
COLORS = {
    "bg_dark": "#1a1a2e",
    "bg_sidebar": "#16213e",
    "bg_card": "#0f3460",
    "bg_card_hover": "#1a4a7a",
    "bg_content": "#1a1a2e",
    "bg_reader": "#0d1117",
    "fg_primary": "#e8e8e8",
    "fg_secondary": "#a0a0b0",
    "fg_muted": "#6a6a7a",
    "accent": "#4e9af1",
    "accent_hover": "#6bb0ff",
    "success": "#4caf50",
    "warning": "#ff9800",
    "error": "#f44336",
    "border": "#2a2a4a",
}

# ──────────────────────────────────────────────
# Fonts
# ──────────────────────────────────────────────
FONTS = {
    "heading": ("Segoe UI", 22, "bold"),
    "subheading": ("Segoe UI", 16, "bold"),
    "body": ("Segoe UI", 13),
    "body_small": ("Segoe UI", 11),
    "reader": ("Georgia", 16),
    "reader_large": ("Georgia", 20),
    "monospace": ("Consolas", 12),
    "sidebar": ("Segoe UI", 13, "bold"),
    "sidebar_icon": ("Segoe UI Emoji", 18),
    "button": ("Segoe UI", 12, "bold"),
}

# ──────────────────────────────────────────────
# Sidebar items
# ──────────────────────────────────────────────
SIDEBAR_ITEMS = [
    {"key": "search",          "icon": "🔍", "label": "Search"},
    {"key": "library",         "icon": "📚", "label": "Library"},
    {"key": "downloads",       "icon": "⬇️",  "label": "Downloads"},
    {"key": "recommendations", "icon": "⭐", "label": "Discover"},
]

# ──────────────────────────────────────────────
# Layout constants
# ──────────────────────────────────────────────
SIDEBAR_WIDTH = 200
CARD_WIDTH = 280
CARD_HEIGHT = 160
PADDING = 12
