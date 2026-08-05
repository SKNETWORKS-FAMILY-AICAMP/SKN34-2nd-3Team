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
        score = float(row.get("recommendation_score") or 0)
        if score >= 80:
            return "최우선 검토"
        if score >= 65:
            return "적극 검토"
        if score >= 50:
            return "관찰 후보"
        return "보류"

    @staticmethod
    def _build_reason(row: dict[str, Any]) -> str:
        score = float(row.get("recommendation_score") or 0)
        dropout = float(row.get("average_dropout_rate") or 0) * 100
        preferences = int(row.get("preference_count") or 0)
        positive = int(row.get("positive_count") or 0)
        negative = int(row.get("negative_count") or 0)
        neutral = int(row.get("neutral_count") or 0)
        total_comments = positive + negative + neutral

        if score >= 80:
            score_reason = "무료 회차의 독자 유지력이 전체 작품 중 최상위권입니다."
        elif score >= 65:
            score_reason = "무료 회차의 독자 유지력이 유료 전환 검토 기준에 충분히 경쟁력이 있습니다."
        elif score >= 50:
            score_reason = "독자 유지력은 중상위권으로, 추가 연재 추이를 확인할 가치가 있습니다."
        else:
            score_reason = "현재 독자 유지력만으로는 즉시 전환보다 관찰이 적합합니다."

        parts = [
            f"노트북 산식으로 계산한 무료 구간 점수는 {score:.1f}점입니다. {score_reason}",
            f"1~5화와 무료·유료 전환 경계를 제외한 회차의 평균 이탈률은 {dropout:.2f}%입니다.",
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
