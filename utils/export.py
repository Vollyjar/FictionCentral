"""
WebNovel Scraper — EPUB & Text Exporter

Generates standards-compliant EPUB 3.0 / 2.0 files directly using Python's
built-in zipfile module — zero external binary dependencies, 100% portable, and
fully compatible with Kindle, Kobo, Apple Books, Calibre, and Moon+ Reader.

Preserves the author's original publishing formatting:
  • Italics, bolding, underlines, strikethrough
  • Scene break dividers (<hr />)
  • Centered text and dialogue emphasis
  • Indented letters and blockquotes
  • System screens, stat windows, and tables (crucial for LitRPG / progression fantasy)
"""
from __future__ import annotations

import html
import logging
import pathlib
import re
import uuid
import zipfile
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup, Comment

if TYPE_CHECKING:
    from database.models import Chapter, Novel

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Remove illegal characters for cross-platform filenames."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    return clean.strip() or "novel"


def _format_chapter_to_xhtml(raw_content: str, chapter_title: str) -> str:
    """Convert stored chapter content (raw HTML or clean text) into valid,
    clean XHTML preserving all original publishing formatting.
    """
    ch_title_escaped = html.escape(chapter_title)
    content_str = (raw_content or "").strip()

    # Check if content has HTML elements
    html_tags = (
        "<p", "<div", "<br", "<em", "<strong", "<i", "<b",
        "<blockquote", "<hr", "<pre", "<table"
    )
    has_html = any(tag in content_str for tag in html_tags)

    if has_html:
        soup = BeautifulSoup(content_str, "lxml")

        # Strip scripts, styles, iframes, and comments
        for bad in soup.find_all(["script", "style", "iframe", "noscript"]):
            bad.decompose()
        for comm in soup.find_all(text=lambda t: isinstance(t, Comment)):
            comm.extract()

        ALLOWED_TAGS = {
            "p", "br", "hr",
            "em", "i", "strong", "b", "u", "s", "strike", "del", "sub", "sup",
            "blockquote", "q", "cite",
            "pre", "code", "samp", "kbd",
            "h1", "h2", "h3", "h4", "h5", "h6",
            "ul", "ol", "li", "dl", "dt", "dd",
            "table", "thead", "tbody", "tfoot", "tr", "th", "td",
            "span", "div",
        }

        for tag in list(soup.find_all(True)):
            if tag.name not in ALLOWED_TAGS:
                tag.unwrap()
            else:
                # Retain only safe styling
                style = tag.get("style", "")
                tag.attrs = {}
                if style:
                    safe_styles = []
                    if "center" in style:
                        safe_styles.append("text-align: center;")
                    if "right" in style:
                        safe_styles.append("text-align: right;")
                    if "italic" in style:
                        safe_styles.append("font-style: italic;")
                    if "bold" in style:
                        safe_styles.append("font-weight: bold;")
                    if safe_styles:
                        tag["style"] = " ".join(safe_styles)

        # Convert <div> to <p> where appropriate
        for d in soup.find_all("div"):
            if not d.find_all(["p", "div", "blockquote", "table", "pre"]):
                d.name = "p"
            else:
                d.unwrap()

        body = soup.body if soup.body else soup
        body_html = "".join(str(c) for c in body.contents).strip()

        # Self-close void tags for valid XHTML
        body_html = re.sub(r"<hr(?:\s*\/)?>", "<hr />", body_html)
        body_html = re.sub(r"<br(?:\s*\/)?>", "<br />", body_html)
    else:
        # Plain text paragraphs
        paragraphs = [p.strip() for p in content_str.split("\n") if p.strip()]
        body_html = "\n".join(f"    <p>{html.escape(p)}</p>" for p in paragraphs)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en">
<head>
    <title>{ch_title_escaped}</title>
    <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
    <h1>{ch_title_escaped}</h1>
    {body_html}
</body>
</html>"""


def export_to_epub(novel: "Novel", output_path: str | pathlib.Path | None = None) -> pathlib.Path:
    """Export a Novel to a professionally formatted .epub file.

    For FanFiction.net novels, it first attempts to stream the pristine official EPUB
    via FicHub API for 100% exact publisher fidelity.
    For all novels, it packages chapters into a standards-compliant EPUB 3.0 / 2.0 archive.

    Args:
        novel: Novel ORM object (with chapters relationship populated)
        output_path: Optional destination filepath. Defaults to ~/Downloads/{title}.epub

    Returns:
        pathlib.Path pointing to the created .epub file.
    """
    if output_path is None:
        downloads_dir = pathlib.Path.home() / "Downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        clean_title = sanitize_filename(novel.title)
        output_path = downloads_dir / f"{clean_title}.epub"
        output_path = pathlib.Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Resolve writable destination path (handles files locked by e-readers on Windows)
    candidate_path = output_path
    counter = 1
    while candidate_path.exists():
        try:
            with open(candidate_path, "a+b"):
                pass
            break
        except (PermissionError, OSError):
            candidate_path = output_path.parent / f"{output_path.stem} ({counter}){output_path.suffix}"
            counter += 1
    output_path = candidate_path

    # ── Check FicHub direct download for FanFiction.net ──
    if novel.source_site == "fanfiction" and novel.source_url:
        try:
            import requests
            fichub_url = f"https://fichub.net/api/v0/epub?q={novel.source_url}"
            resp = requests.get(fichub_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                epub_rel = data.get("epub_url")
                if epub_rel:
                    download_url = f"https://fichub.net{epub_rel}" if epub_rel.startswith("/") else epub_rel
                    dl_resp = requests.get(download_url, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=30)
                    if dl_resp.status_code == 200:
                        with open(output_path, "wb") as f:
                            for chunk in dl_resp.iter_content(chunk_size=65536):
                                f.write(chunk)
                        logger.info("Successfully fetched direct official EPUB from FicHub: %s", output_path)
                        return output_path
        except Exception as exc:
            logger.debug("FicHub direct EPUB download fallback failed: %s", exc)

    # ── Standard EPUB compilation from local database ──
    chapters: list["Chapter"] = sorted(
        [ch for ch in novel.chapters if ch.is_downloaded and ch.content],
        key=lambda c: c.chapter_number,
    )

    if not chapters:
        raise ValueError(f"No downloaded chapters found for '{novel.title}' to export.")

    book_uuid = str(uuid.uuid4())
    current_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    title_escaped = html.escape(novel.title)
    author_escaped = html.escape(novel.author or "Unknown")
    synopsis_escaped = html.escape(novel.synopsis or "")

    with zipfile.ZipFile(output_path, "w") as zf:
        # 1. mimetype (MUST be first, uncompressed)
        zf.writestr(
            "mimetype",
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )

        # 2. META-INF/container.xml
        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>"""
        zf.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)

        # 3. OEBPS/style.css — Book Typography Matching Original Publishing
        style_css = """body {
    font-family: Georgia, "Cambria", "Times New Roman", serif;
    margin: 4% 6%;
    line-height: 1.65;
    color: #1a1a1a;
}
h1, h2, h3, h4, h5, h6 {
    font-family: Georgia, "Cambria", serif;
    text-align: center;
    font-weight: bold;
    margin-top: 1.8em;
    margin-bottom: 1em;
    line-height: 1.3;
}
p {
    text-indent: 1.5em;
    margin-top: 0;
    margin-bottom: 0.4em;
    text-align: justify;
}
/* First paragraph after heading, divider, or quote should NOT be indented */
h1 + p, h2 + p, h3 + p, hr + p, blockquote + p, pre + p, table + p {
    text-indent: 0;
}
em, i {
    font-style: italic;
}
strong, b {
    font-weight: bold;
}
hr {
    border: 0;
    height: 1px;
    background: #aaa;
    margin: 2em auto;
    width: 35%;
}
blockquote {
    margin: 1.5em 2.5em;
    padding-left: 1.2em;
    border-left: 3px solid #777;
    font-style: italic;
    color: #333;
}
/* System Windows / Stat Blocks (Crucial for LitRPG / Cultivation / Progression Fantasy) */
pre, code, .stat-block, .system-window {
    font-family: Consolas, "Courier New", monospace;
    background-color: #f5f5f7;
    border: 1px solid #dcdce2;
    border-radius: 4px;
    padding: 0.8em 1em;
    margin: 1.2em 0;
    font-size: 0.9em;
    line-height: 1.45;
    white-space: pre-wrap;
    text-indent: 0;
}
table {
    border-collapse: collapse;
    width: 95%;
    margin: 1.5em auto;
    font-size: 0.9em;
}
th, td {
    border: 1px solid #ccc;
    padding: 6px 10px;
    text-align: left;
}
th {
    background-color: #eee;
    font-weight: bold;
}
.center, [align="center"] {
    text-align: center;
    text-indent: 0;
}
.title-page {
    text-align: center;
    margin-top: 15%;
}
.title-page h1 {
    font-size: 2.3em;
    margin-bottom: 0.2em;
}
.title-page .author {
    font-size: 1.35em;
    color: #555;
    margin-bottom: 2.5em;
}
.title-page .meta {
    font-size: 0.9em;
    color: #777;
    margin-top: 2em;
}
.synopsis-box {
    text-align: left;
    margin: 2.5em 8%;
    font-style: italic;
    border-left: 3px solid #ccc;
    padding-left: 1.2em;
}
"""
        zf.writestr("OEBPS/style.css", style_css, compress_type=zipfile.ZIP_DEFLATED)

        # 4. Title / Cover page (OEBPS/title.xhtml)
        title_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en">
<head>
    <title>{title_escaped}</title>
    <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
    <div class="title-page">
        <h1>{title_escaped}</h1>
        <div class="author">by {author_escaped}</div>
        <div class="synopsis-box">
            <p>{synopsis_escaped.replace(chr(10), '</p><p>')}</p>
        </div>
        <div class="meta">
            <p>Source: {html.escape(novel.source_site.title())}</p>
            <p>Exported on: {datetime.now().strftime('%B %d, %Y')}</p>
            <p>Chapters: {len(chapters)}</p>
        </div>
    </div>
</body>
</html>"""
        zf.writestr("OEBPS/title.xhtml", title_xhtml, compress_type=zipfile.ZIP_DEFLATED)

        # 5. Write each chapter XHTML
        manifest_items = [
            '<item id="style" href="style.css" media-type="text/css"/>',
            '<item id="title" href="title.xhtml" media-type="application/xhtml+xml"/>',
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        ]
        spine_items = [
            '<itemref idref="title"/>',
            '<itemref idref="nav"/>',
        ]
        nav_li_items = []
        ncx_navpoints = []

        for idx, ch in enumerate(chapters, 1):
            ch_id = f"ch_{idx:04d}"
            ch_filename = f"chapter_{idx:04d}.xhtml"
            ch_title_raw = ch.title or f"Chapter {ch.chapter_number}"
            ch_title_escaped = html.escape(ch_title_raw)

            ch_xhtml = _format_chapter_to_xhtml(ch.content, ch_title_raw)
            zf.writestr(f"OEBPS/{ch_filename}", ch_xhtml, compress_type=zipfile.ZIP_DEFLATED)

            manifest_items.append(
                f'<item id="{ch_id}" href="{ch_filename}" media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'<itemref idref="{ch_id}"/>')
            nav_li_items.append(
                f'            <li><a href="{ch_filename}">{ch_title_escaped}</a></li>'
            )
            ncx_navpoints.append(f"""    <navPoint id="navPoint-{idx}" playOrder="{idx}">
        <navLabel><text>{ch_title_escaped}</text></navLabel>
        <content src="{ch_filename}"/>
    </navPoint>""")

        # 6. OEBPS/nav.xhtml (EPUB 3 Navigation)
        nav_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en">
<head>
    <title>Table of Contents</title>
    <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
    <nav epub:type="toc" id="toc">
        <h1>Table of Contents</h1>
        <ol>
{chr(10).join(nav_li_items)}
        </ol>
    </nav>
</body>
</html>"""
        zf.writestr("OEBPS/nav.xhtml", nav_xhtml, compress_type=zipfile.ZIP_DEFLATED)

        # 7. OEBPS/toc.ncx (EPUB 2 / Kindle compatibility)
        toc_ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
    <head>
        <meta name="dtb:uid" content="urn:uuid:{book_uuid}"/>
        <meta name="dtb:depth" content="1"/>
        <meta name="dtb:totalPageCount" content="0"/>
        <meta name="dtb:maxPageNumber" content="0"/>
    </head>
    <docTitle><text>{title_escaped}</text></docTitle>
    <docAuthor><text>{author_escaped}</text></docAuthor>
    <navMap>
{chr(10).join(ncx_navpoints)}
    </navMap>
</ncx>"""
        zf.writestr("OEBPS/toc.ncx", toc_ncx, compress_type=zipfile.ZIP_DEFLATED)

        # 8. OEBPS/content.opf
        content_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="3.0">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:identifier id="BookId">urn:uuid:{book_uuid}</dc:identifier>
        <dc:title>{title_escaped}</dc:title>
        <dc:creator>{author_escaped}</dc:creator>
        <dc:language>en</dc:language>
        <dc:publisher>{html.escape(novel.source_site.title())}</dc:publisher>
        <dc:description>{synopsis_escaped}</dc:description>
        <meta property="dcterms:modified">{current_time}</meta>
    </metadata>
    <manifest>
{chr(10).join(f"        {item}" for item in manifest_items)}
    </manifest>
    <spine toc="ncx">
{chr(10).join(f"        {item}" for item in spine_items)}
    </spine>
</package>"""
        zf.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)

    logger.info("Successfully exported novel to EPUB: %s", output_path)
    return output_path
