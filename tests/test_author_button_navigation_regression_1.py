from pathlib import Path


PAGE = Path("pages/recommendation_dashboard.py")


# Regression: ISSUE-001 — 작가 ButtonColumn 클릭 정보가 페이지 이동 전에 사라짐
# Found by /qa on 2026-08-06
# Report: .gstack/qa-reports/qa-report-localhost-2026-08-06.md
def test_author_button_queues_target_in_callback_before_switching_page() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "def queue_author_navigation() -> None:" in source
    assert 'on_click=queue_author_navigation' in source
    assert 'st.session_state["recommendation_author_target"] = str(author_id)' in source
    assert 'st.session_state.pop("recommendation_author_target", None)' in source
    assert '"pages/author_novels.py"' in source
    assert 'query_params={"author_id": author_id}' in source
