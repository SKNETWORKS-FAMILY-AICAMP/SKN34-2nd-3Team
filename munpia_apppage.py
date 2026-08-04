from __future__ import annotations

import pandas as pd
import streamlit as st

from service.novel_service import (
    NovelService,
    NovelServiceError,
    PAGE_SIZE,
)


def init_state() -> None:
    defaults = {
        "novel_page": 1,
        "last_changed_novel_id": None,
        "last_change_type": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_header() -> None:
    st.markdown(
        """
        <style>
            .block-container {
                padding-top: 2rem !important;
                padding-bottom: 2rem !important;
                padding-left: 5% !important;
                padding-right: 5% !important;
            }

            [data-testid="stHeader"] {
                display: none !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div style="
            background-color:#1E1E2E;
            padding:1.2rem 2rem;
            border-radius:0.5rem;
            margin-top:-1rem;
            margin-bottom:2rem;
            border-bottom:2px solid #3b82f6;
        ">
            <h2 style="margin:0;color:white;">
                📚 문피아 작품 실시간 수집기
            </h2>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_collection_form(
    service: NovelService,
) -> None:
    with st.form("novel_collect_form"):
        link_or_id = st.text_input(
            "문피아 작품 링크 또는 novel_id",
            placeholder="https://www.munpia.com/novel/detail/12345",
        )
        submitted = st.form_submit_button(
            "데이터 수집",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return

    try:
        novel_id = service.extract_novel_id(link_or_id)

        status_box = st.status(
            f"작품 {novel_id} 수집을 시작합니다.",
            expanded=True,
        )
        progress_text = status_box.empty()
        progress_bar = status_box.progress(0)
        result = None

        for event in service.collect_or_update_stream(
            link_or_id
        ):
            if event.event == "COMPLETE":
                result = event.result
                progress_bar.progress(100)
                progress_text.markdown(
                    f"**완료** · {event.elapsed_seconds:.1f}초"
                )
                status_box.update(
                    label=(
                        f"작품 {novel_id} 수집 및 CSV 반영 완료"
                    ),
                    state="complete",
                    expanded=False,
                )
                break

            total = event.chapter_total
            done = event.chapter_done

            if total and total > 0:
                percent = min(
                    95,
                    max(5, int(done / total * 90) + 5),
                )
            else:
                phase_percent = {
                    "START": 3,
                    "DETAIL": 8,
                    "CHAPTER_LIST": 12,
                    "EPISODE": 20,
                    "EPISODE_PARALLEL": 20,
                    "COMMENTS": 30,
                }
                percent = phase_percent.get(
                    event.phase,
                    5,
                )

            progress_bar.progress(percent)

            detail_lines = [
                f"**{event.message}**",
                f"경과시간: {event.elapsed_seconds:.1f}초",
            ]

            if event.phase == "EPISODE_PARALLEL":
                detail_lines.append(
                    f"동시 처리 중: {event.chapter_in_flight:,}개"
                )
                detail_lines.append(
                    f"실패 회차: {event.chapter_failed:,}개"
                )

            progress_text.markdown(
                "  \n".join(detail_lines)
            )

        if result is None:
            raise NovelServiceError(
                "수집 완료 결과를 받지 못했습니다."
            )

        st.session_state.last_changed_novel_id = result.novel_id
        st.session_state.last_change_type = result.change_type
        st.session_state.novel_page = service.find_page_of_novel(
            result.novel_id,
            PAGE_SIZE,
        )

        action = (
            "신규 추가"
            if result.change_type == "INSERT"
            else "기존 데이터 갱신"
        )
        title = f" · {result.title}" if result.title else ""

        st.success(
            f"작품 {result.novel_id}{title}: {action} 완료"
        )

    except NovelServiceError as exc:
        message = str(exc)

        if (
            "ACCESS_UNAVAILABLE" in message
            or "A002_14003" in message
            or "권한이 없습니다" in message
        ):
            st.error(
                "로그인 권한이 필요한 데이터입니다. "
                ".env의 MUNPIA_COOKIE가 없거나 만료되었습니다."
            )
        else:
            st.error(f"수집 실패: {message}")

    except Exception as exc:
        st.error(f"수집 실패: {exc}")


def render_pagination(
    current_page: int,
    total_pages: int,
    total_rows: int,
) -> None:
    previous_col, page_col, next_col = st.columns([1, 2, 1])

    with previous_col:
        if st.button(
            "◀ 이전",
            disabled=current_page <= 1,
            use_container_width=True,
        ):
            st.session_state.novel_page = current_page - 1
            st.rerun()

    with page_col:
        selected = st.number_input(
            "페이지",
            min_value=1,
            max_value=total_pages,
            value=current_page,
            step=1,
            label_visibility="collapsed",
        )

        if int(selected) != current_page:
            st.session_state.novel_page = int(selected)
            st.rerun()

        st.caption(
            f"{current_page:,} / {total_pages:,}페이지 "
            f"· 총 {total_rows:,}개 · 페이지당 {PAGE_SIZE}개"
        )

    with next_col:
        if st.button(
            "다음 ▶",
            disabled=current_page >= total_pages,
            use_container_width=True,
        ):
            st.session_state.novel_page = current_page + 1
            st.rerun()


def render_table(
    rows: list[dict],
) -> None:
    if not rows:
        st.info("현재 novel.csv에 수집된 작품이 없습니다.")
        return

    frame = pd.DataFrame(rows)

    changed_id = st.session_state.last_changed_novel_id
    change_type = st.session_state.last_change_type

    def highlight_changed(row: pd.Series) -> list[str]:
        if (
            changed_id is not None
            and str(row.get("novel_id", "")) == str(changed_id)
        ):
            background = (
                "background-color: rgba(34, 197, 94, 0.30)"
                if change_type == "INSERT"
                else "background-color: rgba(250, 204, 21, 0.32)"
            )
            return [background] * len(row)

        return [""] * len(row)

    styled = frame.style.apply(
        highlight_changed,
        axis=1,
    )

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=740,
    )


def main() -> None:
    st.set_page_config(
        page_title="문피아 데이터 수집기",
        page_icon="📚",
        layout="wide",
    )

    init_state()
    render_header()

    service = NovelService()

    # 1. 링크/API 수집
    render_collection_form(service)

    st.divider()
    st.subheader("수집된 작품 목록")

    # 2. 기존 novel.csv 목록을 20개씩 표시
    page_data = service.list_novels(
        page=st.session_state.novel_page,
        page_size=PAGE_SIZE,
    )
    st.session_state.novel_page = page_data.page

    render_pagination(
        current_page=page_data.page,
        total_pages=page_data.total_pages,
        total_rows=page_data.total_rows,
    )
    render_table(page_data.rows)


if __name__ == "__main__":
    main()
