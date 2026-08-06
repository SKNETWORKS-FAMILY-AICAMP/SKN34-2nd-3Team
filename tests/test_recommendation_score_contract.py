from pathlib import Path


ROOT = Path(__file__).parents[1]
SQL = ROOT / "db" / "migration" / "V3__create_recommendation_dashboard.sql"
DASHBOARD = ROOT / "pages" / "recommendation_dashboard.py"
REPOSITORY = ROOT / "repository" / "repository.py"


def test_v3_stores_only_independent_score_components_and_preserves_nulls():
    sql = SQL.read_text(encoding="utf-8")

    assert "view_scale_score DECIMAL(6, 2)" in sql
    assert "free_retention_score DECIMAL(6, 2)" in sql
    assert "paid_retention_score DECIMAL(6, 2)" in sql
    assert "recommendation_score DECIMAL" not in sql
    assert "free_score DECIMAL" not in sql
    assert "paid_score DECIMAL" not in sql
    assert "COALESCE(free_retention_score, 0)" not in sql
    assert "CASE WHEN has_reference_view THEN ROUND(score_floor, 2) END" in sql
    repository_source = (ROOT / "repository" / "repository.py").read_text(encoding="utf-8")
    assert "r.free_retention_score IS NOT NULL" in repository_source


def test_v3_creates_the_current_score_schema_and_refreshes_it_repeatably():
    sql = SQL.read_text(encoding="utf-8")

    assert "DROP TABLE" not in sql.upper()
    assert "CREATE TABLE IF NOT EXISTS novel_recommendation_score" in sql
    assert "INFORMATION_SCHEMA" not in sql.upper()
    assert "PREPARE" not in sql.upper()
    assert "ALTER TABLE" not in sql.upper()
    assert "DELETE FROM novel_recommendation_score" in sql
    assert "TRUNCATE TABLE novel_recommendation_score" not in sql


def test_dashboard_displays_integrated_average_without_individual_score_columns():
    source = DASHBOARD.read_text(encoding="utf-8")

    assert '"통합 평균 점수"' in source
    frame_source = source[source.index("ranking_frame = pd.DataFrame("):source.index("st.dataframe(")]
    assert '"조회 규모 점수"' not in frame_source
    assert '"FREE 유지 점수"' not in frame_source
    assert '"PAID 유지 점수"' not in frame_source
    assert "타깃 점수" not in source
    assert "recommendation_score" not in source


def test_repository_returns_all_eligible_candidates_without_prediction_or_comments():
    source = REPOSITORY.read_text(encoding="utf-8")
    start = source.index("def find_recommendations_by_genre(")
    end = source.index("def get_recommendation_episode_scores(", start)
    query = source[start:end]

    assert "n.origin_cover_url" in query
    assert "n.free = 1" in query
    assert "paid_serial, 0) = 0" in query
    assert "finish, 0) = 0" in query
    assert "pause, 0) = 0" in query
    assert "episode_number >= 30" in query
    assert "r.free_retention_score IS NOT NULL" in query
    assert "novel_paid_conversion_prediction" not in query
    assert "novel_comment_sentiment" not in query
    assert "predicted_" not in query
    assert "positive_count" not in query
    assert "LIMIT %s" not in query
