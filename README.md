# 📚 FictionCentral

> *"Please support the authors and the free platforms, even if its just a penny, because your support, matters."*

**FictionCentral** is a modern, standalone desktop application built for reading, organizing, and archiving web fiction and fanfiction across 10 major platforms. 

It provides an ad-free, distraction-free reading experience, permanent local storage in a SQLite database, and 1-click formatted `.epub` export for e-readers (Kindle, Kobo, phone, or tablet).

---

## 🌟 Supported Platforms

FictionCentral supports search and direct URL parsing across:

| Platform | Type | Direct Link Support | Formatting & Preservation |
|:---------|:-----|:--------------------|:--------------------------|
| **Royal Road** | Web Fiction | Fiction & Chapter URLs | Full rich text, anti-piracy trap scrubbing |
| **Archive of Our Own (AO3)** | Fanfiction / Original | Works & Chapter URLs | High-speed batch work extraction, clean XHTML |
| **FanFiction.net** | Fanfiction | Story URLs & Numeric IDs | Cloudflare bypass via FicHub API caching |
| **Webnovel** | Web Fiction / Fanfiction | Book & Chapter URLs | Free chapters, REST API accelerated, watermarks removed |
| **SpaceBattles** | Forum Fiction / Quests | Thread & Post URLs | In-memory threadmark cache, instant extraction |
| **Sufficient Velocity** | Forum Fiction / Quests | Thread & Post URLs | In-memory threadmark cache, instant extraction |
| **Wattpad** | Web Fiction | Story & Part URLs | Clean typography, author note separation |
| **NovelFire** | Web Fiction | Book & Chapter URLs | Clean text, promotion removal |
| **Inkitt** | Web Fiction | Story URLs | Native chapter list & story text extraction |
| **Tapas** | Web Fiction | Series & Episode URLs | Free episode parsing & formatting |
| **Scribble Hub** | Web Fiction | Series & Chapter URLs | Rich HTML parser with Cloudflare Turnstile handling |

---

## ✨ Features

- **🔗 Dedicated Direct Link Search**: Paste any story URL, chapter link, or story ID from any supported platform. The app automatically normalizes the link and fetches the full work.
- **📖 Distraction-Free Offline Reader**: Clean dark mode, customizable font sizes (`+` / `-`), chapter dropdown navigation, and auto-saved reading progress per novel.
- **⬇️ High-Performance Downloader**: Multi-threaded background downloads with SQLite Write-Ahead Logging (WAL) for non-blocking concurrent reads and writes.
- **💾 Permanent Local Library**: Stories are stored locally on your machine in `library.db`. Even if an author deletes the story or a platform removes it, your offline copy is never lost.
- **📱 1-Click Formatted EPUB Export**: Converts stories into valid IDPF-compliant `.epub` books with embedded cover art, tables of contents, and clean XHTML matching the original publishing typography.
- **🛡️ Polite & Ethical Rate Limiting**: Built-in per-domain request throttling (`0.35s`–`0.5s`) and rotating User-Agent pooling to avoid putting unnecessary load on community servers.

---

## 🚀 Getting Started

### Option 1: Standalone Executable (Windows)
1. Download the latest `FictionCentral-v1.0.0-windows-x64.zip` from [Releases](https://github.com/Vollyjar/FictionCentral/releases).
2. Extract the zip anywhere on your computer.
3. Run `FictionCentral.exe`. (No Python installation required!)

### Option 2: Run from Source

#### Prerequisites
- Python 3.10 or higher
- Git

#### Installation
```bash
# 1. Clone the repository
git clone https://github.com/Vollyjar/FictionCentral.git
cd FictionCentral

# 2. Create and activate a virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch FictionCentral
python main.py
```

---

## 🏗️ Building Standalone Binary

To package FictionCentral as a standalone Windows executable:
```bash
pip install pyinstaller
pyinstaller FictionCentral.spec --noconfirm
```
The resulting executable will be located at `dist/FictionCentral/FictionCentral.exe`.

---

## ⚖️ Legal & Ethical Disclaimer

FictionCentral is a free, open-source tool developed for **personal offline reading, accessibility, and format-shifting** of publicly available webfiction.

- **No Paywall Circumvention**: FictionCentral **does not** bypass paywalls, decrypt DRM, crack subscription gates, or access locked/coin chapters. It only fetches content that is already freely readable in a standard public browser.
- **Respect for Authors**: All rights, titles, and copyrights to the stories and fanfictions belong strictly to their respective creators. 
- **Non-Commercial**: This software is completely free and non-commercial. No monetization, donations, or fees are associated with this project.
- **Server Courtesy**: Built-in polite rate-limiting ensures requests do not overwhelm community hosting infrastructure.

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more information.
