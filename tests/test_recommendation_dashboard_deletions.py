from pathlib import Path


PAGE = Path(__file__).parents[1] / "pages" / "recommendation_dashboard.py"


def test_removed_selected_detail_feedback_is_absent() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "import altair as alt" not in source
    assert "def load_episode_dropout(" not in source
    assert "load_episode_dropout(" not in source
    assert "모델이 이 작품을 추천하는 이유" not in source
    assert 'selected["recommendation_reason"]' not in source
    assert 'st.subheader(f"#{selected[\'rank\']} {selected[\'title\']}")' not in source
    assert "작가 정보 없음" not in source
    assert 'selected.get("introduction")' not in source
    assert '"유료 전환 타깃 점수"' not in source
    assert "회차별 독자 이탈률" not in source
    assert "우선 점검할 이탈 구간" not in source
    assert "댓글 감성 구성" not in source
    assert "sentiment_frame" not in source
    assert "sentiment_chart" not in source


def test_remaining_dashboard_contract_is_preserved() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "selection = st.dataframe(" in source
    assert "selected_index = selection.selection.rows[0]" in source
    assert 'if selected.get("source_url"):' in source
    assert '"문피아에서 작품 보기"' in source
    assert "25화 무료 → 첫 유료 회차 전환 예측" in source
    assert "with st.container(horizontal=True):" in source
    assert "with st.sidebar:" in source
    assert "점수 해석과 주의사항" in source
    assert "def percent(" in source
