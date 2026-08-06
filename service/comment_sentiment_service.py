from __future__ import annotations

from typing import Any

from repository.repository import Repository


class CommentSentimentServiceError(RuntimeError):
    """User-facing error raised while reading comment sentiment data."""


class CommentSentimentService:
    """Read-only application service for V5 comment sentiment data."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _reliability_label(count: int) -> str:
        if count <= 0:
            return "분석 데이터 없음"
        if count < 5:
            return "표본 매우 적음"
        if count < 20:
            return "참고용"
        return "일반 분석"

    def _with_ratios(self, row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        analyzed = self._int(result.get("analyzed_comment_count"))
        eligible = self._int(result.get("eligible_comment_count"))
        positive = self._int(result.get("positive_count"))
        neutral = self._int(result.get("neutral_count"))
        negative = self._int(result.get("negative_count"))

        result.update(
            stored_comment_count=self._int(
                result.get("stored_comment_count")
            ),
            eligible_comment_count=eligible,
            analyzed_comment_count=analyzed,
            analysis_rate=(analyzed / eligible * 100.0) if eligible else 0.0,
            positive_count=positive,
            neutral_count=neutral,
            negative_count=negative,
            positive_ratio=(positive / analyzed * 100.0) if analyzed else 0.0,
            neutral_ratio=(neutral / analyzed * 100.0) if analyzed else 0.0,
            negative_ratio=(negative / analyzed * 100.0) if analyzed else 0.0,
            reaction_score=(
                (positive - negative) / analyzed * 100.0
                if analyzed
                else 0.0
            ),
            average_confidence=self._float(
                result.get("average_confidence")
            ),
            reliability=self._reliability_label(analyzed),
        )
        return result

    def get_novel_overview(self, novel_id: int) -> dict[str, Any]:
        try:
            row = self.repository.get_novel_comment_sentiment_overview(
                novel_id
            )
            return self._with_ratios(row)
        except Exception as exc:
            raise CommentSentimentServiceError(
                f"작품 댓글 반응 요약 조회 실패: {exc}"
            ) from exc

    def get_episode_summaries(
        self,
        novel_id: int,
    ) -> list[dict[str, Any]]:
        try:
            rows = (
                self.repository
                .get_episode_comment_sentiment_summaries(novel_id)
            )
            return [self._with_ratios(row) for row in rows]
        except Exception as exc:
            raise CommentSentimentServiceError(
                f"회차별 댓글 반응 조회 실패: {exc}"
            ) from exc

    def get_episode_comments(
        self,
        episode_id: int,
        *,
        label: str = "all",
        sort_by: str = "latest",
        analyzed_only: bool = False,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        try:
            return self.repository.get_episode_comments_with_sentiment(
                episode_id,
                label=label,
                sort_by=sort_by,
                analyzed_only=analyzed_only,
                limit=limit,
            )
        except Exception as exc:
            raise CommentSentimentServiceError(
                f"회차 댓글 조회 실패: {exc}"
            ) from exc

    def get_representative_comments(
        self,
        episode_id: int,
        *,
        limit: int = 5,
    ) -> dict[str, list[dict[str, Any]]]:
        try:
            return self.repository.get_representative_episode_comments(
                episode_id,
                limit=limit,
            )
        except Exception as exc:
            raise CommentSentimentServiceError(
                f"대표 댓글 조회 실패: {exc}"
            ) from exc
