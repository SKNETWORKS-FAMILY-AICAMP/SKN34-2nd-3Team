from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from repository.collection_repository import CsvCollectionRepository
from service import CollectionService, NovelServiceError


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "db" / "data"
PAGE_SIZE = 20

repository = CsvCollectionRepository(DATA_DIR)
service = CollectionService(repository=repository)

st.set_page_config(page_title="문피아 작품 수집", page_icon="📚", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top:2rem; padding-left:5%; padding-right:5%;}
      [data-testid="stHeader"] {display:none;}
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

with st.form("collect-form"):
    raw_input = st.text_input(
        "작품 링크 또는 novel_id",
        placeholder="https://www.munpia.com/novel/detail/512551",
    )
    submitted = st.form_submit_button("데이터 수집", type="primary", use_container_width=True)

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
                status.update(label="수집 및 CSV 반영 완료", state="complete", expanded=False)
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
        st.session_state.collection_page = repository.find_page(final_result.novel_id, PAGE_SIZE)
        action = "신규 추가" if final_result.change_type == "INSERT" else "기존 데이터 갱신"
        st.success(f"{final_result.novel_id} · {final_result.title} · {action} 완료")
    except NovelServiceError as exc:
        status.update(label="수집 실패", state="error")
        st.error(str(exc))
    except Exception as exc:
        status.update(label="수집 실패", state="error")
        st.error(f"수집 실패: {exc}")

st.divider()
st.subheader("수집된 작품 목록")

rows, total_rows = repository.list_novels(st.session_state.collection_page, PAGE_SIZE)
total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)
st.session_state.collection_page = min(st.session_state.collection_page, total_pages)

left, center, right = st.columns([1, 2, 1])
with left:
    if st.button("◀ 이전", disabled=st.session_state.collection_page <= 1, use_container_width=True):
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
    st.caption(f"{st.session_state.collection_page} / {total_pages}페이지 · 총 {total_rows:,}개")
    if int(selected_page) != st.session_state.collection_page:
        st.session_state.collection_page = int(selected_page)
        st.rerun()
with right:
    if st.button("다음 ▶", disabled=st.session_state.collection_page >= total_pages, use_container_width=True):
        st.session_state.collection_page += 1
        st.rerun()

if rows:
    frame = pd.DataFrame(rows)
    changed = st.session_state.last_changed_novel_id
    change_type = st.session_state.last_change_type

    def highlight(row: pd.Series) -> list[str]:
        if changed is not None and str(row.get("novel_id")) == str(changed):
            color = "background-color: rgba(34,197,94,.30)" if change_type == "INSERT" else "background-color: rgba(250,204,21,.32)"
            return [color] * len(row)
        return [""] * len(row)

    st.dataframe(frame.style.apply(highlight, axis=1), use_container_width=True, hide_index=True, height=740)
else:
    st.info("수집된 작품이 없습니다.")
