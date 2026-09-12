"""
WebNovel Scraper — Recommendation Engine

Simple genre-based filtering + popularity scoring.
"""
from __future__ import annotations

from database.db import get_session
from database.models import Novel


def get_recommendations(
    genres: list[str] | None = None,
    limit: int = 20,
    exclude_ids: list[int] | None = None,
) -> list[Novel]:
    """Return novels from the library matching *genres*, sorted by score.

    Score = (rating * 10) + log2(total_chapters + 1)
    """
    import math

    with get_session() as session:
        query = session.query(Novel).filter(Novel.is_in_library == True)  # noqa: E712

        novels = query.all()

        if genres:
            genres_lower = {g.lower() for g in genres}
            novels = [
                n for n in novels
                if {g.lower() for g in n.genres} & genres_lower
            ]

        if exclude_ids:
            novels = [n for n in novels if n.id not in exclude_ids]

        # Score and sort
        def score(n: Novel) -> float:
            r = n.rating or 0.0
            ch = n.total_chapters or 0
            return (r * 10) + math.log2(ch + 1)

        novels.sort(key=score, reverse=True)
        return novels[:limit]


def get_similar(novel_id: int, limit: int = 10) -> list[Novel]:
    """Find novels in library with overlapping genres/tags."""
    with get_session() as session:
        source = session.get(Novel, novel_id)
        if not source:
            return []

        source_genres = {g.lower() for g in source.genres}
        source_tags = {t.lower() for t in source.tags}

        candidates = (
            session.query(Novel)
            .filter(Novel.is_in_library == True, Novel.id != novel_id)  # noqa: E712
            .all()
        )

        scored: list[tuple[float, Novel]] = []
        for n in candidates:
            n_genres = {g.lower() for g in n.genres}
            n_tags = {t.lower() for t in n.tags}
            overlap = len(source_genres & n_genres) * 3 + len(source_tags & n_tags)
            if overlap > 0:
                scored.append((overlap, n))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [n for _, n in scored[:limit]]
