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
from database.models import Chapter, Novel, DownloadQueueItem
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
    """Thread-safe download queue manager with persistent SQLite backing."""

    def __init__(self) -> None:
        self._queue: list[DownloadJob] = []
        self._lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()
        self._callbacks: list[ProgressCallback] = []

    # ── Persistent DB Sync ───────────────────
    def _sync_db_status(self, novel_id: int, status: DownloadStatus, error_message: str = "") -> None:
        """Persist the download job status into SQLite."""
        try:
            with get_session() as session:
                item = session.query(DownloadQueueItem).filter_by(novel_id=novel_id).first()
                if item is None:
                    item = DownloadQueueItem(
                        novel_id=novel_id,
                        status=status.name,
                        error_message=error_message,
                    )
                    session.add(item)
                else:
                    item.status = status.name
                    item.error_message = error_message
                    item.updated_at = datetime.now(timezone.utc)
                session.commit()
        except Exception as exc:
            logger.error("Failed to sync download queue DB status for novel %d: %s", novel_id, exc)

    # ── Public API ────────────────────────────
    def add_callback(self, cb: ProgressCallback) -> None:
        self._callbacks.append(cb)

    def remove_callback(self, cb: ProgressCallback) -> None:
        self._callbacks.remove(cb)

    def enqueue(self, novel_id: int, novel_title: str, source_url: str,
                scraper: BaseScraper, chapters: list[ChapterInfo]) -> DownloadJob:
        """Add a novel to the download queue and persist in SQLite."""
        with self._lock:
            # Check if existing job is in queue
            for existing in self._queue:
                if existing.novel_id == novel_id:
                    if existing.status in (DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING):
                        return existing
                    existing.status = DownloadStatus.QUEUED
                    existing.chapters = chapters
                    existing.total_chapters = len(chapters)
                    existing.downloaded_count = 0
                    existing.error_message = ""
                    self._sync_db_status(novel_id, DownloadStatus.QUEUED)
                    self._ensure_running()
                    return existing

            job = DownloadJob(
                novel_id=novel_id,
                novel_title=novel_title,
                source_url=source_url,
                scraper=scraper,
                chapters=chapters,
                total_chapters=len(chapters),
            )
            self._queue.append(job)

        self._sync_db_status(novel_id, DownloadStatus.QUEUED)
        logger.info("Enqueued: %s (%d chapters)", novel_title, len(chapters))
        self._ensure_running()
        return job

    def enqueue_novel(self, novel_id: int) -> Optional[DownloadJob]:
        """Fetch novel metadata, resolve scraper and chapter list, and enqueue."""
        from scraper import registry
        with get_session() as session:
            novel = session.get(Novel, novel_id)
            if not novel:
                return None
            source_url = novel.source_url
            novel_title = novel.title

        scraper = registry.get_scraper_for_url(source_url)
        if not scraper:
            logger.error("No scraper available for %s", source_url)
            return None

        try:
            chapters = scraper.get_chapter_list(source_url)
            with get_session() as session:
                novel = session.get(Novel, novel_id)
                if novel and len(chapters) > (novel.total_chapters or 0):
                    novel.total_chapters = len(chapters)
                # Re-align existing DB chapters by URL to match official catalog order
                db_chapters = session.query(Chapter).filter_by(novel_id=novel_id).all()
                if db_chapters:
                    url_to_idx = {ch.url: ch.chapter_number for ch in chapters}
                    # Step 1: temporarily negate chapter_numbers to avoid unique constraint collisions
                    for ch in db_chapters:
                        ch.chapter_number = -ch.id
                    session.flush()
                    # Step 2: assign correct chapter_number based on catalog URL
                    for ch in db_chapters:
                        if ch.source_url in url_to_idx:
                            ch.chapter_number = url_to_idx[ch.source_url]
                        else:
                            ch.chapter_number = abs(ch.chapter_number)
                session.commit()
        except Exception as exc:
            logger.error("Failed to fetch chapter list for %s: %s", novel_title, exc)
            return None

        return self.enqueue(
            novel_id=novel_id,
            novel_title=novel_title,
            source_url=source_url,
            scraper=scraper,
            chapters=chapters,
        )

    def enqueue_all_incomplete(self) -> int:
        """Scan library for any novel with missing chapters and enqueue in background."""
        with get_session() as session:
            novels = (
                session.query(Novel)
                .filter(Novel.is_in_library == True)  # noqa: E712
                .filter(Novel.downloaded_chapters < Novel.total_chapters)
                .all()
            )
            incomplete_ids = [n.id for n in novels]

        for nid in incomplete_ids:
            threading.Thread(target=self.enqueue_novel, args=(nid,), daemon=True).start()

        return len(incomplete_ids)

    def restore_persistent_queue(self) -> None:
        """Survive power outages: restore any unfinished or queued jobs from SQLite."""
        def _worker():
            with get_session() as session:
                items = (
                    session.query(DownloadQueueItem)
                    .filter(DownloadQueueItem.status.in_(["QUEUED", "DOWNLOADING"]))
                    .all()
                )
                novel_ids = [item.novel_id for item in items]

            logger.info("Restoring %d persistent download jobs from DB...", len(novel_ids))
            for nid in novel_ids:
                self.enqueue_novel(nid)

        threading.Thread(target=_worker, daemon=True).start()

    def clear_completed(self) -> None:
        """Remove completed or cancelled jobs from the active queue and DB."""
        with self._lock:
            self._queue = [
                j for j in self._queue
                if j.status not in (DownloadStatus.COMPLETED, DownloadStatus.CANCELLED)
            ]
        try:
            with get_session() as session:
                session.query(DownloadQueueItem).filter(
                    DownloadQueueItem.status.in_(["COMPLETED", "CANCELLED"])
                ).delete(synchronize_session=False)
                session.commit()
        except Exception as exc:
            logger.error("Failed to clear completed items from DB: %s", exc)

    def pause(self, novel_id: int) -> None:
        with self._lock:
            for job in self._queue:
                if job.novel_id == novel_id and job.status == DownloadStatus.DOWNLOADING:
                    job.status = DownloadStatus.PAUSED
                    self._sync_db_status(novel_id, DownloadStatus.PAUSED)

    def resume(self, novel_id: int) -> None:
        with self._lock:
            for job in self._queue:
                if job.novel_id == novel_id and job.status in (DownloadStatus.PAUSED, DownloadStatus.FAILED):
                    job.status = DownloadStatus.QUEUED
                    job.error_message = ""
                    self._sync_db_status(novel_id, DownloadStatus.QUEUED)
        self._ensure_running()

    def cancel(self, novel_id: int) -> None:
        with self._lock:
            for job in self._queue:
                if job.novel_id == novel_id and job.status in (
                    DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING, DownloadStatus.PAUSED
                ):
                    job.status = DownloadStatus.CANCELLED
                    self._sync_db_status(novel_id, DownloadStatus.CANCELLED)

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
        self._sync_db_status(job.novel_id, DownloadStatus.DOWNLOADING)
        job.downloaded_count = 0

        for ch_info in job.chapters:
            if self._stop_event.is_set():
                job.status = DownloadStatus.PAUSED
                self._sync_db_status(job.novel_id, DownloadStatus.PAUSED)
                self._notify(job)
                return

            if job.status == DownloadStatus.PAUSED:
                self._sync_db_status(job.novel_id, DownloadStatus.PAUSED)
                self._notify(job)
                return

            if job.status == DownloadStatus.CANCELLED:
                self._sync_db_status(job.novel_id, DownloadStatus.CANCELLED)
                self._notify(job)
                return

            # Check if already downloaded (resume support)
            with get_session() as session:
                existing = (
                    session.query(Chapter)
                    .filter(
                        Chapter.novel_id == job.novel_id,
                        (Chapter.chapter_number == ch_info.chapter_number) | (Chapter.source_url == ch_info.url),
                    )
                    .first()
                )
                if existing and existing.is_downloaded and existing.content:
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
                        .filter(
                            Chapter.novel_id == job.novel_id,
                            (Chapter.chapter_number == ch_info.chapter_number) | (Chapter.source_url == ch_info.url),
                        )
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
                    else:
                        chapter.chapter_number = ch_info.chapter_number
                        chapter.source_url = ch_info.url
                    chapter.title = ch_info.title
                    chapter.content = content
                    chapter.word_count = word_count
                    chapter.is_downloaded = True
                    chapter.date_downloaded = datetime.now(timezone.utc)

                    actual_dl = (
                        session.query(Chapter)
                        .filter_by(novel_id=job.novel_id, is_downloaded=True)
                        .count()
                    )
                    novel = session.get(Novel, job.novel_id)
                    if novel:
                        novel.downloaded_chapters = actual_dl
                    session.commit()

                job.downloaded_count = actual_dl
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

        self._sync_db_status(job.novel_id, job.status, job.error_message)
        self._notify(job)

    def _notify(self, job: DownloadJob) -> None:
        for cb in self._callbacks:
            try:
                cb(job)
            except Exception:
                logger.exception("Progress callback error")
