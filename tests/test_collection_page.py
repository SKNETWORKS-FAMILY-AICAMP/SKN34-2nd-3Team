from pathlib import Path

PAGE = Path(__file__).parents[1] / "pages" / "munpia_apppage.py"


def test_page_uses_service_and_progress():
    source = PAGE.read_text(encoding="utf-8")
    assert "service.collect_stream" in source
    assert "chapter_in_flight" not in source or "event.message" in source
    assert "repository.save_result" not in source
    assert "pd.read_csv" not in source
