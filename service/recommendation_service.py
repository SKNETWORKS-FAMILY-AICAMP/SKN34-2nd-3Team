from __future__ import annotations

from typing import Any, Sequence

from repository.repository import Repository
from service.comment_sentiment_service import CommentSentimentService


class RecommendationService:
    """무료 작품의 유료 전환 후보를 조회하고 설명하는 서비스."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def list_genres(self) -> list[dict[str, Any]]:
        return self.repository.list_recommendation_genres()

    def get_ranked_novels(
        self, genre_id: int | None, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        rows = self.repository.find_recommendations_by_genre(genre_id)
        for row in rows:
            row.update(self.calculate_integrated_score(row))
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
    ) -> dict[int, dict[str, Any]]:
        """Return raw components and centrally calculated scores from one bulk lookup."""
        rows = self.repository.get_author_analysis(novel_ids)
        for row in rows.values():
            row.update(self.calculate_integrated_score(row))
        return rows

    @staticmethod
    def calculate_integrated_score(row: dict[str, Any]) -> dict[str, float | None]:
        """Normalize available components to 0..100 and average them equally."""
        components: list[float] = []
        view_scale = row.get("view_scale_score")
        if view_scale is not None:
            components.append(min(100.0, max(0.0, float(view_scale) * 1.25)))
        for key in ("free_retention_score", "paid_retention_score"):
            if row.get(key) is not None:
                components.append(min(100.0, max(0.0, float(row[key]))))

        analyzed = int(row.get("analyzed_comment_count") or 0)
        reaction_score = CommentSentimentService.reaction_score_from_counts(
            int(row.get("positive_count") or 0),
            int(row.get("negative_count") or 0),
            analyzed,
        )
        if reaction_score is not None:
            components.append((reaction_score + 100.0) / 2.0)

        return {
            "reaction_score": reaction_score,
            "integrated_average_score": (
                sum(components) / len(components) if components else None
            ),
        }

    @staticmethod
    def author_average_integrated_score(
        scores: dict[int, dict[str, Any]],
    ) -> tuple[float | None, int]:
        """Average calculable per-novel integrated scores equally."""
        values = [
            float(row["integrated_average_score"])
            for row in scores.values()
            if row.get("integrated_average_score") is not None
        ]
        reflected_count = len(values)
        if not reflected_count:
            return None, 0
        return sum(values) / reflected_count, reflected_count
