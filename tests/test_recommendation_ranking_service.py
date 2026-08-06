from typing import get_type_hints

from service.recommendation_service import RecommendationService


class StubRepository:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def find_recommendations_by_genre(self, genre_id):
        self.calls.append(genre_id)
        return [dict(row) for row in self.rows]


def test_ranked_novels_equal_weights_available_components_then_limits():
    repository = StubRepository(
        [
            {"novel_id": 1, "view_scale_score": 100, "free_retention_score": 20, "paid_retention_score": None, "analyzed_comment_count": 0},
            {"novel_id": 2, "view_scale_score": 70, "free_retention_score": 80, "paid_retention_score": 90, "analyzed_comment_count": 4, "positive_count": 3, "negative_count": 1},
            {"novel_id": 3, "view_scale_score": None, "free_retention_score": 90, "paid_retention_score": None, "analyzed_comment_count": 0},
        ]
    )

    rows = RecommendationService(repository).get_ranked_novels(7, limit=2)

    assert repository.calls == [7]
    assert [row["novel_id"] for row in rows] == [3, 2]
    assert [row["rank"] for row in rows] == [1, 2]
    assert [row["integrated_average_score"] for row in rows] == [90.0, 83.125]
    assert rows[1]["reaction_score"] == 50.0


def test_calculate_integrated_score_normalizes_and_ignores_missing_components():
    score = RecommendationService.calculate_integrated_score(
        {
            "view_scale_score": 40,
            "free_retention_score": 60,
            "paid_retention_score": None,
            "analyzed_comment_count": 4,
            "positive_count": 3,
            "negative_count": 1,
        }
    )

    assert score == {"reaction_score": 50.0, "integrated_average_score": 185 / 3}
    assert RecommendationService.calculate_integrated_score(
        {"view_scale_score": None, "free_retention_score": None,
         "paid_retention_score": None, "analyzed_comment_count": 0}
    ) == {"reaction_score": None, "integrated_average_score": None}


def test_ranked_novels_rejects_non_positive_limit():
    service = RecommendationService(StubRepository([]))

    try:
        service.get_ranked_novels(7, limit=0)
    except ValueError as exc:
        assert str(exc) == "limit must be greater than zero"
    else:
        raise AssertionError("ValueError was not raised")


def test_ranked_novels_passes_none_for_all_genres():
    repository = StubRepository([])

    RecommendationService(repository).get_ranked_novels(None)

    assert repository.calls == [None]
    assert get_type_hints(RecommendationService.get_ranked_novels)["genre_id"] == int | None
