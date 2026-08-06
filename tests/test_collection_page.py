from pathlib import Path

PAGE = Path(__file__).parents[1] / "pages" / "munpia_apppage.py"


def test_page_uses_service_and_progress():
    source = PAGE.read_text(encoding="utf-8")
    assert "service.collect_stream" in source
    assert "chapter_in_flight" not in source or "event.message" in source
    assert "repository.save_result" not in source
    assert "pd.read_csv" not in source


def test_novel_table_has_detail_button_navigation():
    source = PAGE.read_text(encoding="utf-8")
    assert 'frame["상세보기"]' in source
    assert "st.column_config.ButtonColumn" in source
    assert 'key="novel_detail_button"' in source
    assert "def open_novel_detail" not in source
    assert "on_click=open_novel_detail" not in source
    assert 'st.session_state.get("novel_detail_button")' in source
    assert 'frame.iloc[row_index]["소설 아이디"]' in source
    assert '"pages/novel_basic_info.py"' in source
    assert 'query_params={"url": novel_id}' in source


def test_novel_table_uses_clear_read_only_statuses_and_datetime_column():
    source = PAGE.read_text(encoding="utf-8")
    assert '.map({True: "무료", False: "유료"})' in source
    assert 'frame["paid_serial"]' not in source
    assert 'frame["serial_status"] = "상태 미확인"' in source
    assert 'frame.loc[is_serializing, "serial_status"] = "연재 중"' in source
    assert 'frame.loc[is_paused, "serial_status"] = "휴재 중"' in source
    assert 'frame.loc[is_finished, "serial_status"] = "완결"' in source
    assert source.index('frame.loc[is_paused, "serial_status"]') < source.index(
        'frame.loc[is_finished, "serial_status"]'
    )
    assert 'frame.drop(columns=["finish", "pause"], inplace=True)' in source

    assert '"제공 유형": st.column_config.ButtonColumn(' not in source
    assert '"연재 상태": st.column_config.ButtonColumn(' not in source
    assert '"수집 상태": st.column_config.ButtonColumn(' not in source
    assert "st.column_config.MarkdownColumn" not in source
    assert "frame.style.map(" in source
    assert 'subset=["제공 유형", "연재 상태", "수집 상태"]' in source

    assert (
        '"수집 일시": st.column_config.DatetimeColumn(\n'
        '                "수집 일시",'
    ) in source


def test_novel_table_displays_serial_status_in_finish_column_position():
    source = PAGE.read_text(encoding="utf-8")
    display_order = (
        '            "제공 유형",\n'
        '            "연재 상태",\n'
        '            "누적 조회수",'
    )

    assert "".join(display_order) in source


def test_page_builds_deduplicated_category_and_sidebar_filters():
    source = PAGE.read_text(encoding="utf-8")
    assert "service.list_genre_options()" in source
    assert "repository.list_genre_options()" not in source
    assert "repository.find_page(" not in source
    assert "repository.list_novels(" not in source
    assert "selected_genre_label = st.sidebar.selectbox(" in source
    assert '    "카테고리",' in source
    assert 'st.sidebar.selectbox("연재 상태"' in source
    assert "page_size = st.sidebar.selectbox(" in source
    assert '    "페이지당 작품 수",' in source
    assert '    "최소 누적 조회수",' in source
    assert '    "최소 선호작 수",' in source
    assert '    "최소 회차 수",' in source
    assert 'genre_id=selected_genre_id' in source
    assert 'serial_status=selected_serial_status' in source
    assert 'min_view_count=min_view_count' in source
    assert 'min_preference_count=min_preference_count' in source
    assert 'min_chapter_count=min_chapter_count' in source
    assert 'st.session_state.collection_page = 1' in source
    assert 'filter_fingerprint' in source
    assert 'dict.fromkeys' in source
    assert '"genre_1_name"' in source
    assert '"genre_2_name"' in source


def test_novel_table_has_collection_states_manual_button_and_preferred_order():
    source = PAGE.read_text(encoding="utf-8")
    assert 'frame["수집 상태"] = "수집 완료"' in source
    assert '"collecting": "수집 중"' in source
    assert '"failed": "수집 실패"' in source
    assert 'frame["수동 수집"] = "수집"' in source
    expected_order = (
        '            "소설 아이디",\n'
        '            "제목",\n'
        '            "카테고리",\n'
        '            "작가",\n'
        '            "제공 유형",\n'
        '            "연재 상태",\n'
        '            "누적 조회수",\n'
        '            "선호작 수",\n'
        '            "회차 수",\n'
        '            "수집 일시",\n'
        '            "수집 상태",\n'
        '            "수동 수집",\n'
        '            "상세보기",'
    )
    assert "".join(expected_order) in source
    assert '"수집 상태": st.column_config.ButtonColumn(' not in source
    assert '"수동 수집": st.column_config.ButtonColumn(' in source
    assert 'key="manual_collection_button"' in source
    assert 'key="novel_detail_button"' in source


def test_status_cell_style_has_accessible_light_background_dark_text_pairs():
    source = PAGE.read_text(encoding="utf-8")
    expected_colors = {
        "무료": ("#dcfce7", "#14532d"),
        "유료": ("#fee2e2", "#7f1d1d"),
        "연재 중": ("#dcfce7", "#14532d"),
        "휴재 중": ("#fef3c7", "#78350f"),
        "완결": ("#dbeafe", "#1e3a8a"),
        "상태 미확인": ("#e5e7eb", "#374151"),
        "수집 완료": ("#dcfce7", "#14532d"),
        "수집 중": ("#fef3c7", "#78350f"),
        "수집 실패": ("#fee2e2", "#7f1d1d"),
    }

    for label, (background, text) in expected_colors.items():
        assert f'"{label}": ("{background}", "{text}")' in source


def test_manual_collection_renders_collecting_state_before_consuming_pending_once():
    source = PAGE.read_text(encoding="utf-8")
    assert 'st.session_state.get("manual_collection_button")' in source
    assert 'manual_collection_click_token' in source
    assert 'pending_manual_collection_id' in source
    assert 'service.collect_stream(str(novel_id))' in source
    assert 'st.status("수동 수집을 시작합니다."' in source
    assert 'collection_states[novel_id] = "collecting"' in source
    assert 'collection_states[novel_id] = "complete"' in source
    assert 'collection_states[novel_id] = "failed"' in source

    first_rerun = source.index(
        "st.rerun()",
        source.index('collection_states[novel_id] = "collecting"'),
    )
    collect_call = source.index('service.collect_stream(str(novel_id))')
    assert first_rerun < collect_call
    assert source.index("st.dataframe(") < collect_call
    pending_branch = source.index("if pending_novel_id is not None:")
    assert (
        source.index(
            "st.session_state.pending_manual_collection_id = None",
            pending_branch,
        )
        < collect_call
    )
    assert "pending_novel_id is None\n            and click_token !=" in source
