from __future__ import annotations

import pandas as pd
import streamlit as st

from repository.repository import Repository
from service import CollectionService, NovelServiceError


DEFAULT_PAGE_SIZE = 20
STATUS_CELL_COLORS = {
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


def status_cell_style(value: object) -> str:
    colors = STATUS_CELL_COLORS.get(str(value))
    if colors is None:
        return ""
    background, text = colors
    return f"background-color: {background}; color: {text}; font-weight: 600"

repository = Repository()
service = CollectionService(repository=repository)

st.set_page_config(page_title="문피아 작품 수집", page_icon="📚", layout="wide")

# st.markdown(
#     """
#     <style>
#       .block-container {padding-top:2rem; padding-left:5%; padding-right:5%;}
#       [data-testid="stHeader"] {display:none;}
#     </style>
#     """,
#     unsafe_allow_html=True,
# )
st.markdown(
    """
    <style>
      .block-container {
          padding-top: 2rem;
          padding-left: 5%;
          padding-right: 5%;
      }

      /* 헤더 자체는 유지: 사이드바 다시 열기 버튼이 여기 들어 있음 */
      [data-testid="stHeader"] {
          background: transparent;
      }

      /* Deploy 버튼 */
      [data-testid="stAppDeployButton"] {
          display: none !important;
      }

      /* 우측 점 3개 메뉴 */
      [data-testid="stMainMenu"] {
          display: none !important;
      }

      /* 우측 기타 툴바 항목 */
      [data-testid="stToolbarActions"] {
          display: none !important;
      }

      /* 사이드바 다시 열기 버튼은 명시적으로 유지 */
      [data-testid="stExpandSidebarButton"] {
          display: flex !important;
          visibility: visible !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("📚 문피아 작품 실시간 수집")

if "collection_page" not in st.session_state:
    st.session_state.collection_page = 1
if "last_changed_novel_id" not in st.session_state:
    st.session_state.last_changed_novel_id = None
if "last_change_type" not in st.session_state:
    st.session_state.last_change_type = None
if "collection_filter_fingerprint" not in st.session_state:
    st.session_state.collection_filter_fingerprint = None
if "collection_states" not in st.session_state:
    st.session_state.collection_states = {}
if "manual_collection_click_token" not in st.session_state:
    st.session_state.manual_collection_click_token = None
if "pending_manual_collection_id" not in st.session_state:
    st.session_state.pending_manual_collection_id = None

genre_options = repository.list_genre_options()
genre_labels = {genre_id: genre_name for genre_id, genre_name in genre_options}
selected_genre_label = st.sidebar.selectbox(
    "카테고리",
    ["전체", *genre_labels.values()],
)
selected_genre_id = next(
    (
        genre_id
        for genre_id, genre_name in genre_options
        if genre_name == selected_genre_label
    ),
    None,
)
status_options = {
    "전체": None,
    "연재 중": "serializing",
    "휴재 중": "paused",
    "완결": "finished",
    "상태 미확인": "unknown",
}
selected_status_label = st.sidebar.selectbox("연재 상태", status_options)
selected_serial_status = status_options[selected_status_label]
page_size = st.sidebar.selectbox(
    "페이지당 작품 수",
    [DEFAULT_PAGE_SIZE, 50, 100],
    index=0,
)
min_view_count = st.sidebar.number_input(
    "최소 누적 조회수", min_value=0, value=0, step=1000
)
min_preference_count = st.sidebar.number_input(
    "최소 선호작 수", min_value=0, value=0, step=100
)
min_chapter_count = st.sidebar.number_input(
    "최소 회차 수", min_value=0, value=0, step=1
)
filter_fingerprint = (
    page_size,
    selected_genre_id,
    selected_serial_status,
    int(min_view_count),
    int(min_preference_count),
    int(min_chapter_count),
)
if filter_fingerprint != st.session_state.collection_filter_fingerprint:
    st.session_state.collection_page = 1
    st.session_state.collection_filter_fingerprint = filter_fingerprint

with st.form("collect-form"):
    raw_input = st.text_input(
        "작품 링크 또는 novel_id",
        placeholder="https://www.munpia.com/novel/detail/512551",
    )
    submitted = st.form_submit_button(
        "데이터 수집",
        type="primary",
        width="stretch",
    )

if submitted:
    status = st.status("수집을 시작합니다.", expanded=True)
    message = status.empty()
    progress = status.progress(0)
    try:
        final_result = None
        for event in service.collect_stream(raw_input):
            if event.event == "COMPLETE":
                final_result = event.result
                progress.progress(100)
                message.markdown(f"**완료** · {event.elapsed_seconds:.1f}초")
                status.update(
                    label="수집 및 DB 저장 완료",
                    state="complete",
                    expanded=False,
                )
                break

            total = event.chapter_total
            done = event.chapter_done
            percent = min(95, max(5, int(done / total * 90) + 5)) if total else 5
            progress.progress(percent)
            message.markdown(
                f"**{event.message}**  \n"
                f"경과시간: {event.elapsed_seconds:.1f}초"
            )

        if final_result is None:
            raise RuntimeError("완료 결과를 받지 못했습니다.")

        st.session_state.last_changed_novel_id = final_result.novel_id
        st.session_state.last_change_type = final_result.change_type
        st.session_state.collection_page = repository.find_page(
            final_result.novel_id,
            page_size,
        )

        action = (
            "신규 추가"
            if final_result.change_type == "INSERT"
            else "기존 데이터 갱신"
        )
        st.success(
            f"{final_result.novel_id} · "
            f"{final_result.title} · "
            f"{action} 완료"
        )

    except NovelServiceError as exc:
        status.update(label="수집 실패", state="error")
        st.error(str(exc))

    except Exception as exc:
        status.update(label="수집 실패", state="error")
        st.error(f"수집 실패: {exc}")

st.divider()
st.subheader("수집된 작품 목록")

rows, total_rows = repository.list_novels(
    st.session_state.collection_page,
    page_size,
    genre_id=selected_genre_id,
    serial_status=selected_serial_status,
    min_view_count=min_view_count,
    min_preference_count=min_preference_count,
    min_chapter_count=min_chapter_count,
)

total_pages = max(1, (total_rows + page_size - 1) // page_size)
if st.session_state.collection_page > total_pages:
    st.session_state.collection_page = total_pages
    rows, total_rows = repository.list_novels(
        st.session_state.collection_page,
        page_size,
        genre_id=selected_genre_id,
        serial_status=selected_serial_status,
        min_view_count=min_view_count,
        min_preference_count=min_preference_count,
        min_chapter_count=min_chapter_count,
    )

left, center, right = st.columns([1, 2, 1])

with left:
    if st.button(
        "◀ 이전",
        disabled=st.session_state.collection_page <= 1,
        width="stretch",
    ):
        st.session_state.collection_page -= 1
        st.rerun()

with center:
    selected_page = st.number_input(
        "페이지",
        min_value=1,
        max_value=total_pages,
        value=st.session_state.collection_page,
        label_visibility="collapsed",
    )

    st.caption(
        f"{st.session_state.collection_page} / "
        f"{total_pages}페이지 · "
        f"총 {total_rows:,}개"
    )

    if int(selected_page) != st.session_state.collection_page:
        st.session_state.collection_page = int(selected_page)
        st.rerun()

with right:
    if st.button(
        "다음 ▶",
        disabled=st.session_state.collection_page >= total_pages,
        width="stretch",
    ):
        st.session_state.collection_page += 1
        st.rerun()

if rows:
    frame = pd.DataFrame(rows)

    frame["free"] = (
        frame["free"].fillna(False).astype(bool)
        .map({True: "무료", False: "유료"})
    )
    has_known_status = frame["finish"].notna() & frame["pause"].notna()
    is_finished = frame["finish"].fillna(False).astype(bool)
    is_paused = has_known_status & frame["pause"].astype(bool) & ~is_finished
    is_serializing = has_known_status & ~is_paused & ~is_finished
    frame["serial_status"] = "상태 미확인"
    frame.loc[is_serializing, "serial_status"] = "연재 중"
    frame.loc[is_paused, "serial_status"] = "휴재 중"
    frame.loc[is_finished, "serial_status"] = "완결"
    frame.drop(columns=["finish", "pause"], inplace=True)
    frame["category"] = frame.apply(
        lambda row: " / ".join(
            dict.fromkeys(
                name
                for name in (row["genre_1_name"], row["genre_2_name"])
                if pd.notna(name) and name
            )
        ),
        axis=1,
    )
    frame.drop(columns=["genre_1_name", "genre_2_name"], inplace=True)

    frame.rename(
        columns={
            "novel_id": "소설 아이디",
            "title": "제목",
            "category": "카테고리",
            "author_name": "작가",
            "free": "제공 유형",
            "serial_status": "연재 상태",
            "view_count": "누적 조회수",
            "preference_count": "선호작 수",
            "chapter_count": "회차 수",
            "collected_at": "수집 일시",
        },
        inplace=True,
    )

    collection_states = st.session_state.collection_states
    frame["수집 상태"] = "수집 완료"
    state_labels = {
        "collecting": "수집 중",
        "complete": "수집 완료",
        "failed": "수집 실패",
    }
    frame["수집 상태"] = frame["소설 아이디"].map(
        lambda novel_id: state_labels.get(
            collection_states.get(int(novel_id)), "수집 완료"
        )
    )
    frame["수동 수집"] = "수집"
    frame["상세보기"] = ":material/visibility: 보기"
    frame = frame[
        [
            "소설 아이디",
            "제목",
            "카테고리",
            "작가",
            "제공 유형",
            "연재 상태",
            "누적 조회수",
            "선호작 수",
            "회차 수",
            "수집 일시",
            "수집 상태",
            "수동 수집",
            "상세보기",
        ]
    ]

    styled_frame = frame.style.map(
        status_cell_style,
        subset=["제공 유형", "연재 상태", "수집 상태"],
    )

    st.dataframe(
        styled_frame,
        width="stretch",
        hide_index=True,
        height=740,
        key="novel_table",
        column_config={
            "수집 일시": st.column_config.DatetimeColumn(
                "수집 일시",
            ),
            "수동 수집": st.column_config.ButtonColumn(
                "수동 수집",
                width="small",
                key="manual_collection_button",
            ),
            "상세보기": st.column_config.ButtonColumn(
                "상세보기",
                width="small",
                type="primary",
                key="novel_detail_button",
            ),
        },
    )

    pending_novel_id = st.session_state.pending_manual_collection_id
    manual_clicked = st.session_state.get("manual_collection_button")
    if manual_clicked is None:
        st.session_state.manual_collection_click_token = None
    else:
        row_index = int(manual_clicked["row"])
        novel_id = int(frame.iloc[row_index]["소설 아이디"])
        click_token = (novel_id, row_index)
        if (
            pending_novel_id is None
            and click_token != st.session_state.manual_collection_click_token
        ):
            st.session_state.manual_collection_click_token = click_token
            collection_states[novel_id] = "collecting"
            st.session_state.pending_manual_collection_id = novel_id
            st.rerun()

    if pending_novel_id is not None:
        novel_id = int(pending_novel_id)
        st.session_state.pending_manual_collection_id = None
        status = st.status("수동 수집을 시작합니다.", expanded=True)
        message = status.empty()
        progress = status.progress(0)
        try:
            completed = False
            for event in service.collect_stream(str(novel_id)):
                if event.event == "COMPLETE":
                    completed = True
                    progress.progress(100)
                    message.markdown(f"**완료** · {event.elapsed_seconds:.1f}초")
                    status.update(
                        label="수집 및 DB 저장 완료",
                        state="complete",
                        expanded=False,
                    )
                    break
                total = event.chapter_total
                done = event.chapter_done
                percent = (
                    min(95, max(5, int(done / total * 90) + 5))
                    if total else 5
                )
                progress.progress(percent)
                message.markdown(
                    f"**{event.message}**  \n"
                    f"경과시간: {event.elapsed_seconds:.1f}초"
                )
            if not completed:
                raise RuntimeError("완료 결과를 받지 못했습니다.")
            collection_states[novel_id] = "complete"
        except Exception as exc:
            collection_states[novel_id] = "failed"
            status.update(label="수집 실패", state="error")
            st.error(f"수집 실패: {exc}")
        st.rerun()

    clicked = st.session_state.get("novel_detail_button")
    if clicked is not None:
        row_index = int(clicked["row"])
        novel_id = str(frame.iloc[row_index]["소설 아이디"])
        st.switch_page(
            "pages/novel_basic_info.py",
            query_params={"url": novel_id},
        )
else:
    st.info("수집된 작품이 없습니다.")
