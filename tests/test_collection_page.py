from pathlib import Path


PAGE = Path(__file__).parents[1] / "pages" / "munpia_apppage.py"


def test_collection_page_uses_collection_result_without_rereading_csv() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert source.count('state="error"') == 2
    assert "result = asyncio.run(collection_service.collect(raw_input))" in source
    assert "st.session_state.novel = result.novel" in source
    assert "fresh_repository" not in source
    assert "read_service" not in source
    assert "process_single_work" not in source
    assert "/api/" not in source
