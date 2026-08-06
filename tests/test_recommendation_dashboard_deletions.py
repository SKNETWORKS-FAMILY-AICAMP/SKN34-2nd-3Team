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

    assert "st.dataframe(" in source
    assert '"작품명": st.column_config.ButtonColumn(' in source
    assert 'key="recommendation_novel_button"' in source
    assert '"작가": st.column_config.ButtonColumn(' in source
    assert 'key="recommendation_author_button"' in source
    assert 'st.session_state.get("recommendation_novel_button")' in source
    assert 'st.session_state.get("recommendation_author_button")' in source
    assert '"pages/novel_basic_info.py"' in source
    assert 'query_params={"url": novel_id}' in source
    assert '"pages/author_novels.py"' in source
    assert 'query_params={"author_id": author_id}' in source
    assert "selected = recommendations[0]" not in source
    assert "25화 무료 → 첫 유료 회차 전환 예측" not in source
    assert "with st.container(horizontal=True):" in source
    assert "with st.sidebar:" in source
    assert "점수 해석과 주의사항" in source
    assert "def percent(" not in source


def test_dashboard_has_top_three_cards_and_only_simplified_table_columns() -> None:
    source = PAGE.read_text(encoding="utf-8")
    assert "recommendations[:3]" in source
    assert "st.columns(3" in source
    assert "origin_cover_url" in source
    assert "st.image(" in source
    assert "st.page_link(" in source
    frame_start = source.index("ranking_frame = pd.DataFrame(")
    table_start = source.index("st.dataframe(", frame_start)
    frame_source = source[frame_start:table_start]
    for column in ("순위", "작품명", "작가", "통합 평균 점수", "조회 규모", "기준 조회수"):
        assert f'"{column}"' in frame_source
    for removed in (
        "판단", "예상 구매", "예상 구매 전환율", "예상 유료 이탈률",
        "평균 이탈률", "추천·선호", "연재 회차",
    ):
        assert f'"{removed}"' not in frame_source

    assert "무료 후보 수" in source
    assert "평균 통합 점수" in source
    assert "사용 가능한 조회 규모/FREE 유지/PAID 유지 점수의 동일 가중 평균, 결측 제외" in source


def test_dataframe_selection_and_external_link_are_removed() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert 'on_select="rerun"' not in source
    assert 'selection_mode="single-row"' not in source
    assert "selection.selection.rows" not in source
    assert "selected_index" not in source
    assert "문피아에서 작품 보기" not in source
    assert "st.link_button(" not in source
    assert "st.column_config.LinkColumn(" not in source
