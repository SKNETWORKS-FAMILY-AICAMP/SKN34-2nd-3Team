from __future__ import annotations

from typing import Any, Sequence

from repository.repository import Repository


class RecommendationService:
    """무료 작품의 유료 전환 후보를 조회하고 설명하는 서비스."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def list_genres(self) -> list[dict[str, Any]]:
        return self.repository.list_recommendation_genres()

    def get_ranked_novels(
        self, genre_id: int, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        rows = self.repository.find_recommendations_by_genre(genre_id)
        for row in rows:
            available_scores = [
                float(row[key])
                for key in (
                    "view_scale_score",
                    "free_retention_score",
                    "paid_retention_score",
                )
                if row.get(key) is not None
            ]
            row["integrated_average_score"] = sum(available_scores) / len(available_scores)
        rows.sort(
            key=lambda row: (
                -float(row["integrated_average_score"]),
                int(row["novel_id"]),
            )
        )
        rows = rows[:limit]
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
        return rows

    def get_episode_dropout(self, novel_id: int) -> list[dict[str, Any]]:
        return self.repository.get_recommendation_episode_scores(novel_id)

    def get_author_analysis(
        self, novel_ids: Sequence[int]
    ) -> dict[int, tuple[float | None, float | None, float | None]]:
        """Return independent score components from one bulk lookup."""
        return self.repository.get_author_analysis(novel_ids)

    @staticmethod
    def author_average_free_retention(
        scores: dict[int, tuple[float | None, float | None, float | None]],
    ) -> tuple[float | None, int]:
        """Average only available FREE retention components."""
        values = [parts[1] for parts in scores.values() if parts[1] is not None]
        reflected_count = len(values)
        if not reflected_count:
            return None, 0
        return sum(values) / reflected_count, reflected_count
