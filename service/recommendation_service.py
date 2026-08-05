from __future__ import annotations

from typing import Any

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
        rows = self.repository.find_recommendations_by_genre(genre_id, limit=limit)
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
            row["recommendation_reason"] = self._build_reason(row)
            row["decision_label"] = self._decision_label(row)
        return rows

    def get_episode_dropout(self, novel_id: int) -> list[dict[str, Any]]:
        return self.repository.get_recommendation_episode_scores(novel_id)

    @staticmethod
    def _decision_label(row: dict[str, Any]) -> str:
        return str(row.get("view_grade") or "아주 낮음")

    @staticmethod
    def _build_reason(row: dict[str, Any]) -> str:
        score = float(row.get("recommendation_score") or 0)
        retention = float(row.get("retention_score") or 0)
        reference_views = int(row.get("reference_view_count") or 0)
        view_scale_max = int(row.get("view_scale_max") or 100000)
        view_grade = str(row.get("view_grade") or "아주 낮음")
        predicted_purchases = int(row.get("predicted_purchase_count") or 0)
        predicted_conversion = float(row.get("predicted_conversion_rate") or 0) * 100
        predicted_paid_dropout = float(row.get("predicted_paid_dropout_rate") or 1) * 100
        dropout = float(row.get("average_dropout_rate") or 0) * 100
        preferences = int(row.get("preference_count") or 0)
        positive = int(row.get("positive_count") or 0)
        negative = int(row.get("negative_count") or 0)
        neutral = int(row.get("neutral_count") or 0)
        total_comments = positive + negative + neutral

        parts = [
            f"최신 게시일보다 7일 이상 지난 기준 회차의 조회수는 {reference_views:,}회로, "
            f"10~{view_scale_max:,}회 로그 구간에서 조회 규모 등급은 '{view_grade}'입니다.",
            f"26화 이후 무료 구간의 독자 유지 점수는 {retention:.1f}점이며 "
            f"평균 이탈률은 {dropout:.2f}%입니다.",
            f"조회 규모가 결정한 20점 구간 안에서 유지 점수를 반영한 최종 타깃 점수는 "
            f"{score:.1f}점입니다.",
            f"과거 25화 FREE→첫 유료 회차 전환 사례를 학습한 모델은 "
            f"구매 전환율 {predicted_conversion:.1f}%, 예상 구매 {predicted_purchases:,}건, "
            f"예상 유료 이탈률 {predicted_paid_dropout:.1f}%로 추정합니다.",
        ]
        if preferences:
            parts.append(
                f"추천·선호 {preferences:,}건은 이미 형성된 독자 수요를 보여주는 보조 신호입니다."
            )
        if total_comments:
            positive_ratio = positive / total_comments * 100
            parts.append(
                f"분류된 댓글 {total_comments:,}건 중 긍정 반응은 {positive_ratio:.1f}%로 나타났습니다."
            )
        parts.append("최종 계약 판단에는 작품성, 작가 일정, 프로모션 적합성을 함께 검토해야 합니다.")
        return " ".join(parts)
