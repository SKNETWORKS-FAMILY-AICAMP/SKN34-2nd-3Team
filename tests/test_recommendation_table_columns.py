from pathlib import Path


PAGE = Path(__file__).parents[1] / "pages" / "recommendation_dashboard.py"


def test_ranking_table_starts_with_rank_and_excludes_comment_columns() -> None:
    source = PAGE.read_text(encoding="utf-8")
    frame_start = source.index("ranking_frame = pd.DataFrame(")
    table_start = source.index("st.dataframe(", frame_start)
    table_end = source.index("novel_clicked =", table_start)
    frame_source = source[frame_start:table_start]
    table_source = source[table_start:table_end]

    assert frame_source.index('"순위"') < frame_source.index('"작품명"')
    title_config_start = table_source.index(
        '"작품명": st.column_config.ButtonColumn('
    )
    title_config_end = table_source.index(
        '"작가": st.column_config.ButtonColumn(', title_config_start
    )
    assert "pinned=True" not in table_source[title_config_start:title_config_end]
    for comment_column in ('"긍정 댓글"', '"부정 댓글"', '"중립 댓글"'):
        assert comment_column not in frame_source
        assert comment_column not in table_source
