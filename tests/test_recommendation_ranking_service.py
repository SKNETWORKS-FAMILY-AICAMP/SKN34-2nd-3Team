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
            {"novel_id": 1, "view_scale_score": 100, "free_retention_score": 20, "paid_retention_score": None},
            {"novel_id": 2, "view_scale_score": 70, "free_retention_score": 80, "paid_retention_score": 90},
            {"novel_id": 3, "view_scale_score": None, "free_retention_score": 90, "paid_retention_score": None},
        ]
    )

    rows = RecommendationService(repository).get_ranked_novels(7, limit=2)

    assert repository.calls == [7]
    assert [row["novel_id"] for row in rows] == [3, 2]
    assert [row["rank"] for row in rows] == [1, 2]
    assert [row["integrated_average_score"] for row in rows] == [90.0, 80.0]


def test_ranked_novels_rejects_non_positive_limit():
    service = RecommendationService(StubRepository([]))

    try:
        service.get_ranked_novels(7, limit=0)
    except ValueError as exc:
        assert str(exc) == "limit must be greater than zero"
    else:
        raise AssertionError("ValueError was not raised")
