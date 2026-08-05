from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from repository.repository import Repository
from service.recommendation_service import RecommendationService


PAGE = Path(__file__).parents[1] / "pages" / "author_novels.py"


class ReadCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def execute(self, query, params=()):
        self.executed.append((" ".join(query.split()), tuple(params)))

    def fetchall(self):
        return self.rows


def test_repository_bulk_loads_canonical_scores_in_one_query(monkeypatch):
    repository = Repository()
    cursor = ReadCursor(
        [
            {"novel_id": 20, "recommendation_score": 81.25},
            {"novel_id": 10, "recommendation_score": 47.0},
        ]
    )

    @contextmanager
    def fake_cursor(*, dictionary=False):
        assert dictionary is True
        yield cursor

    monkeypatch.setattr(repository, "_cursor", fake_cursor)

    scores = repository.get_recommendation_scores([20, 10, 20])

    assert scores == {20: 81.25, 10: 47.0}
    assert len(cursor.executed) == 1
    query, params = cursor.executed[0]
    assert "r.recommendation_score" in query
    assert "FROM novel_recommendation_score AS r" in query
    assert "IN (%s, %s)" in query
    assert params == (20, 10)


def test_repository_skips_database_for_empty_novel_ids(monkeypatch):
    repository = Repository()
    monkeypatch.setattr(
        repository,
        "_cursor",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("DB queried")),
    )

    assert repository.get_recommendation_scores([]) == {}


def test_recommendation_service_delegates_bulk_score_lookup():
    class StubRepository:
        def __init__(self):
            self.calls = []

        def get_recommendation_scores(self, novel_ids):
            self.calls.append(list(novel_ids))
            return {10: 72.04}

    repository = StubRepository()
    service = RecommendationService(repository)

    assert service.get_novel_scores([10, 20]) == {10: 72.04}
    assert repository.calls == [[10, 20]]


def test_author_page_uses_service_bulk_scores_and_missing_label():
    source = PAGE.read_text(encoding="utf-8")

    assert "RecommendationService" in source
    assert "recommendation_service.get_novel_scores" in source
    assert source.index("recommendation_service.get_novel_scores") < source.index(
        "for novel in novels:"
    )
    assert "유료 전환 타깃 점수" in source
    assert 'f"{score:.1f} / 100"' in source
    assert '"분석 전"' in source
    assert "recommendation_score" not in source
    assert "find_recommendations_by_genre" not in source
