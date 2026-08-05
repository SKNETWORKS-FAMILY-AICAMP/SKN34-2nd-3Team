from __future__ import annotations

from contextlib import contextmanager
import ast
from pathlib import Path
from types import SimpleNamespace

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


def test_repository_bulk_loads_both_analysis_coverages_in_one_query(monkeypatch):
    repository = Repository()
    cursor = ReadCursor(
        [
            {"novel_id": 20, "recommendation_score": 81.25, "paid_prediction_novel_id": 20},
            {"novel_id": 10, "recommendation_score": 47.0, "paid_prediction_novel_id": None},
        ]
    )

    @contextmanager
    def fake_cursor(*, dictionary=False):
        assert dictionary is True
        yield cursor

    monkeypatch.setattr(repository, "_cursor", fake_cursor)

    scores, paid_ids = repository.get_author_analysis([20, 10, 20])

    assert scores == {20: 81.25, 10: 47.0}
    assert paid_ids == {20}
    assert len(cursor.executed) == 1
    query, params = cursor.executed[0]
    assert "r.recommendation_score" in query
    assert "LEFT JOIN novel_recommendation_score AS r" in query
    assert "novel_paid_conversion_prediction AS p" in query
    assert "IN (%s, %s)" in query
    assert params == (20, 10)


def test_repository_skips_database_for_empty_novel_ids(monkeypatch):
    repository = Repository()
    monkeypatch.setattr(
        repository,
        "_cursor",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("DB queried")),
    )

    assert repository.get_author_analysis([]) == ({}, set())


def test_recommendation_service_delegates_bulk_author_analysis_lookup():
    class StubRepository:
        def __init__(self):
            self.calls = []

        def get_author_analysis(self, novel_ids):
            self.calls.append(list(novel_ids))
            return {10: 72.04}, {20}

    repository = StubRepository()
    service = RecommendationService(repository)

    assert service.get_author_analysis([10, 20]) == ({10: 72.04}, {20})
    assert repository.calls == [[10, 20]]


def test_author_page_uses_one_bulk_analysis_call_and_coverage_cards():
    source = PAGE.read_text(encoding="utf-8")

    assert "RecommendationService" in source
    assert "recommendation_service.get_author_analysis" in source
    assert source.index("recommendation_service.get_author_analysis") < source.index(
        "for novel in novels:"
    )
    assert "조회 유지·타깃 점수" in source
    assert "유료 전환 예측" in source
    assert source.count("분석 작품") >= 2
    assert "유료 전환 타깃 점수" in source
    assert 'f"{score:.1f} / 100"' in source
    assert '"분석 대상 아님"' in source
    assert "border-radius" in source
    assert "#" in source
    assert "recommendation_score" not in source
    assert "find_recommendations_by_genre" not in source


def _load_page_function(name):
    source = PAGE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    module = ast.Module(body=[node], type_ignores=[])
    namespace = {}
    exec(compile(module, str(PAGE), "exec"), namespace)
    return namespace[name]


def test_payment_status_accepts_mysql_integer_booleans_and_preserves_unknown():
    payment_status = _load_page_function("payment_status")

    assert payment_status(SimpleNamespace(free=1, paid_serial=0)) == "무료"
    assert payment_status(SimpleNamespace(free=0, paid_serial=1)) == "유료"
    assert payment_status(SimpleNamespace(free=None, paid_serial=1)) == "유료"
    assert payment_status(SimpleNamespace(free=None, paid_serial=None)) == "무료/유료 정보 없음"
