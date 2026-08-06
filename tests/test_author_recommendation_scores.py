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


def test_repository_bulk_loads_target_and_retention_scores_in_one_query(monkeypatch):
    repository = Repository()
    cursor = ReadCursor(
        [
            {"novel_id": 20, "recommendation_score": 81.25, "retention_score": 60.0, "paid_score": 80.0},
            {"novel_id": 10, "recommendation_score": 47.0, "retention_score": 50.0, "paid_score": None},
            {"novel_id": 30, "recommendation_score": None, "retention_score": None, "paid_score": 90.0},
        ]
    )

    @contextmanager
    def fake_cursor(*, dictionary=False):
        assert dictionary is True
        yield cursor

    monkeypatch.setattr(repository, "_cursor", fake_cursor)

    scores, retention_parts = repository.get_author_analysis([20, 10, 30, 20])

    assert scores == {20: 81.25, 10: 47.0}
    assert retention_parts == {
        20: (60.0, 80.0),
        10: (50.0, None),
        30: (None, 90.0),
    }
    assert len(cursor.executed) == 1
    query, params = cursor.executed[0]
    assert "r.recommendation_score" in query
    assert "r.retention_score" in query
    assert "r.paid_score" in query
    assert "LEFT JOIN novel_recommendation_score AS r" in query
    assert "novel_paid_conversion_prediction" not in query
    assert "IN (%s, %s, %s)" in query
    assert params == (20, 10, 30)


def test_repository_skips_database_for_empty_novel_ids(monkeypatch):
    repository = Repository()
    monkeypatch.setattr(
        repository,
        "_cursor",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("DB queried")),
    )

    assert repository.get_author_analysis([]) == ({}, {})


def test_recommendation_service_delegates_bulk_author_analysis_lookup():
    class StubRepository:
        def __init__(self):
            self.calls = []

        def get_author_analysis(self, novel_ids):
            self.calls.append(list(novel_ids))
            return {10: 72.04}, {10: (40.0, 80.0), 20: (None, 90.0), 30: (None, None)}

    repository = StubRepository()
    service = RecommendationService(repository)

    assert service.get_author_analysis([10, 20]) == ({10: 72.04}, {10: 60.0, 20: 90.0})
    assert repository.calls == [[10, 20]]


def test_author_average_retention_equal_weights_works_with_values():
    assert RecommendationService.author_average_retention({10: 60.0, 20: 90.0}) == (75.0, 2)
    assert RecommendationService.author_average_retention({}) == (None, 0)


def test_author_page_uses_one_bulk_analysis_call_and_summary_cards():
    source = PAGE.read_text(encoding="utf-8")

    assert "RecommendationService" in source
    assert "recommendation_service.get_author_analysis" in source
    assert source.index("recommendation_service.get_author_analysis") < source.index(
        "for novel in novels:"
    )
    assert "조회 유지·타깃 점수" in source
    assert "유료 전환 예측" not in source
    assert "작가 평균 조회 유지 점수" in source
    assert "반영 작품" in source
    assert "유료 전환 타깃 점수" in source
    assert 'f"{score:.1f} / 100"' in source
    assert '"분석 대상 아님"' in source
    assert "border-radius" in source
    assert "#" in source
    assert "recommendation_score" not in source
    assert "find_recommendations_by_genre" not in source


def test_author_page_links_real_author_url_and_uses_compact_body_metadata():
    source = PAGE.read_text(encoding="utf-8")

    assert "author.author_url" in source
    assert "st.link_button" in source
    assert "작가 개인 페이지" in source
    assert "status_col" not in source
    assert "cover_col, body_col = st.columns" in source
    assert "metadata_cols = st.columns(3)" in source


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
