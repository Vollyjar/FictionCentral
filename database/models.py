"""
WebNovel Scraper — SQLAlchemy ORM Models
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


# ──────────────────────────────────────────────
# Novel
# ──────────────────────────────────────────────
class Novel(Base):
    __tablename__ = "novels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    author = Column(String(300), default="Unknown")
    source_site = Column(String(100), nullable=False)       # e.g. "royalroad"
    source_url = Column(String(1000), nullable=False, unique=True)
    synopsis = Column(Text, default="")
    cover_url = Column(String(1000), default="")
    cover_local = Column(String(500), default="")            # local path to cached cover
    status = Column(String(50), default="Unknown")           # Ongoing, Completed, Hiatus
    genres_json = Column(Text, default="[]")                 # JSON array of genre strings
    tags_json = Column(Text, default="[]")                   # JSON array of tag strings
    rating = Column(Float, default=0.0)
    total_chapters = Column(Integer, default=0)
    downloaded_chapters = Column(Integer, default=0)
    is_in_library = Column(Boolean, default=False)
    date_added = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    chapters = relationship("Chapter", back_populates="novel", cascade="all, delete-orphan")
    progress = relationship("ReadingProgress", back_populates="novel", uselist=False, cascade="all, delete-orphan")

    # ── Convenience properties ──
    @property
    def genres(self) -> list[str]:
        try:
            return json.loads(self.genres_json) if self.genres_json else []
        except (json.JSONDecodeError, TypeError):
            return []

    @genres.setter
    def genres(self, value: list[str]) -> None:
        self.genres_json = json.dumps(value)

    @property
    def tags(self) -> list[str]:
        try:
            return json.loads(self.tags_json) if self.tags_json else []
        except (json.JSONDecodeError, TypeError):
            return []

    @tags.setter
    def tags(self, value: list[str]) -> None:
        self.tags_json = json.dumps(value)

    def __repr__(self) -> str:
        return f"<Novel(id={self.id}, title={self.title!r}, site={self.source_site})>"


# ──────────────────────────────────────────────
# Chapter
# ──────────────────────────────────────────────
class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("novel_id", "chapter_number", name="uq_novel_chapter"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    chapter_number = Column(Integer, nullable=False)
    title = Column(String(500), default="")
    content = Column(Text, default="")
    source_url = Column(String(1000), default="")
    word_count = Column(Integer, default=0)
    is_downloaded = Column(Boolean, default=False)
    date_downloaded = Column(DateTime, nullable=True)

    # Relationships
    novel = relationship("Novel", back_populates="chapters")

    def __repr__(self) -> str:
        return f"<Chapter(novel_id={self.novel_id}, ch={self.chapter_number}, title={self.title!r})>"


# ──────────────────────────────────────────────
# Reading Progress
# ──────────────────────────────────────────────
class ReadingProgress(Base):
    __tablename__ = "reading_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, unique=True)
    last_chapter_read = Column(Integer, default=0)
    scroll_position = Column(Float, default=0.0)       # 0.0 – 1.0 within the chapter
    last_read_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    novel = relationship("Novel", back_populates="progress")

    def __repr__(self) -> str:
        return f"<ReadingProgress(novel_id={self.novel_id}, ch={self.last_chapter_read})>"


# ──────────────────────────────────────────────
# Search Cache
# ──────────────────────────────────────────────
class SearchCache(Base):
    __tablename__ = "search_cache"
    __table_args__ = (
        UniqueConstraint("query", "site", name="uq_query_site"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(String(300), nullable=False)
    site = Column(String(100), nullable=False)
    results_json = Column(Text, default="[]")
    cached_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<SearchCache(query={self.query!r}, site={self.site})>"
