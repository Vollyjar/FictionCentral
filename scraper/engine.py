"""
WebNovel Scraper — Download Engine

Manages a background download queue with:
  • Resume support  (skips already-downloaded chapters)
  • Progress callbacks  (for the GUI)
  • Graceful shutdown  (finishes current chapter before stopping)
  • Persistent queue   (survives app restarts via the DB)
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Callable, Optional

from database.db import get_session
from database.models import Chapter, Novel
from scraper.base import BaseScraper, ChapterInfo

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Types
# ──────────────────────────────────────────────
class DownloadStatus(Enum):
    QUEUED = auto()
    DOWNLOADING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class DownloadJob:
    """Represents one novel being downloaded."""
    novel_id: int
    novel_title: str
    source_url: str
    scraper: BaseScraper
    chapters: list[ChapterInfo] = field(default_factory=list)
    status: DownloadStatus = DownloadStatus.QUEUED
    total_chapters: int = 0
    downloaded_count: int = 0
    current_chapter: str = ""
    error_message: str = ""


# Callback signature: (job: DownloadJob) -> None
ProgressCallback = Callable[[DownloadJob], None]


# ──────────────────────────────────────────────
# Engine
# ──────────────────────────────────────────────
class DownloadEngine:
    """Thread-safe download queue manager."""

    def __init__(self) -> None:
        self._queue: list[DownloadJob] = []
        self._lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()
        self._callbacks: list[ProgressCallback] = []

    # ── Public API ────────────────────────────
    def add_callback(self, cb: ProgressCallback) -> None:
        self._callbacks.append(cb)

    def remove_callback(self, cb: ProgressCallback) -> None:
        self._callbacks.remove(cb)

    def enqueue(self, novel_id: int, novel_title: str, source_url: str,
                scraper: BaseScraper, chapters: list[ChapterInfo]) -> DownloadJob:
        """Add a novel to the download queue."""
        job = DownloadJob(
            novel_id=novel_id,
            novel_title=novel_title,
            source_url=source_url,
            scraper=scraper,
            chapters=chapters,
            total_chapters=len(chapters),
        )
        with self._lock:
            self._queue.append(job)
        logger.info("Enqueued: %s (%d chapters)", novel_title, len(chapters))
        self._ensure_running()
        return job

    def pause(self, novel_id: int) -> None:
        with self._lock:
            for job in self._queue:
                if job.novel_id == novel_id and job.status == DownloadStatus.DOWNLOADING:
                    job.status = DownloadStatus.PAUSED

    def resume(self, novel_id: int) -> None:
        with self._lock:
            for job in self._queue:
                if job.novel_id == novel_id and job.status in (DownloadStatus.PAUSED, DownloadStatus.FAILED):
                    job.status = DownloadStatus.QUEUED
                    job.error_message = ""
        self._ensure_running()

    def cancel(self, novel_id: int) -> None:
        with self._lock:
            for job in self._queue:
                if job.novel_id == novel_id and job.status in (
                    DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING, DownloadStatus.PAUSED
                ):
                    job.status = DownloadStatus.CANCELLED

    def get_queue(self) -> list[DownloadJob]:
        with self._lock:
            return list(self._queue)

    def shutdown(self) -> None:
        """Gracefully stop — finish current chapter, then exit."""
        logger.info("Download engine: graceful shutdown requested")
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=120)

    # ── Internal ──────────────────────────────
    def _ensure_running(self) -> None:
        if self._running:
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

    def _worker(self) -> None:
        self._running = True
        logger.info("Download worker started")
        try:
            while not self._stop_event.is_set():
                job = self._next_job()
                if job is None:
                    break   # queue empty
                self._process_job(job)
        finally:
            self._running = False
            logger.info("Download worker stopped")

    def _next_job(self) -> Optional[DownloadJob]:
        with self._lock:
            for job in self._queue:
                if job.status == DownloadStatus.QUEUED:
                    job.status = DownloadStatus.DOWNLOADING
                    return job
        return None

    def _process_job(self, job: DownloadJob) -> None:
        """Download all chapters for a single novel."""
        logger.info("Starting download: %s", job.novel_title)

        for ch_info in job.chapters:
            if self._stop_event.is_set():
                job.status = DownloadStatus.PAUSED
                self._notify(job)
                return

            if job.status == DownloadStatus.PAUSED:
                self._notify(job)
                return

            if job.status == DownloadStatus.CANCELLED:
                self._notify(job)
                return

            # Check if already downloaded (resume support)
            with get_session() as session:
                existing = (
                    session.query(Chapter)
                    .filter_by(novel_id=job.novel_id, chapter_number=ch_info.chapter_number)
                    .first()
                )
                if existing and existing.is_downloaded:
                    job.downloaded_count += 1
                    job.current_chapter = ch_info.title
                    self._notify(job)
                    continue

            # Download the chapter
            try:
                job.current_chapter = ch_info.title or f"Chapter {ch_info.chapter_number}"
                content = job.scraper.get_chapter_content(ch_info.url)
                if not content or not content.strip():
                    raise ValueError(f"Empty content received for chapter {ch_info.chapter_number}")
                word_count = len(content.split())

                # Save to DB immediately after each chapter (crash-safe single transaction)
                with get_session() as session:
                    chapter = (
                        session.query(Chapter)
                        .filter_by(novel_id=job.novel_id, chapter_number=ch_info.chapter_number)
                        .first()
                    )
                    if chapter is None:
                        chapter = Chapter(
                            novel_id=job.novel_id,
                            chapter_number=ch_info.chapter_number,
                            title=ch_info.title,
                            source_url=ch_info.url,
                        )
                        session.add(chapter)
                    chapter.content = content
                    chapter.word_count = word_count
                    chapter.is_downloaded = True
                    chapter.date_downloaded = datetime.now(timezone.utc)

                    # Update novel's downloaded_chapters count in the same commit
                    novel = session.get(Novel, job.novel_id)
                    if novel:
                        novel.downloaded_chapters = job.downloaded_count + 1
                    session.commit()

                job.downloaded_count += 1
                self._notify(job)
                logger.debug("Downloaded: %s ch.%d", job.novel_title, ch_info.chapter_number)

            except Exception as exc:
                logger.error(
                    "Failed to download %s ch.%d: %s",
                    job.novel_title, ch_info.chapter_number, exc,
                )
                job.error_message = str(exc)
                # Continue to next chapter instead of aborting the whole novel
                self._notify(job)
                continue

        # Final count sync & status determination
        with get_session() as session:
            novel = session.get(Novel, job.novel_id)
            if novel:
                actual_count = (
                    session.query(Chapter)
                    .filter_by(novel_id=job.novel_id, is_downloaded=True)
                    .count()
                )
                novel.downloaded_chapters = actual_count
                job.downloaded_count = actual_count
                session.commit()

        # Check overall completion status
        if job.downloaded_count == 0 and job.total_chapters > 0:
            job.status = DownloadStatus.FAILED
            logger.warning("Failed: %s (0/%d chapters downloaded)", job.novel_title, job.total_chapters)
        elif job.downloaded_count < job.total_chapters and job.error_message:
            job.status = DownloadStatus.FAILED
            logger.warning(
                "Partially downloaded: %s (%d/%d chapters)",
                job.novel_title, job.downloaded_count, job.total_chapters,
            )
        else:
            job.status = DownloadStatus.COMPLETED
            logger.info("Completed: %s (%d chapters)", job.novel_title, job.downloaded_count)

        self._notify(job)

    def _notify(self, job: DownloadJob) -> None:
        for cb in self._callbacks:
            try:
                cb(job)
            except Exception:
                logger.exception("Progress callback error")
