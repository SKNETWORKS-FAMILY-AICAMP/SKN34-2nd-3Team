from __future__ import annotations

import streamlit as st

from repository.repository import Repository
from service.novel_service import NovelService
from service.novel_service_errors import NovelServiceError
from service.recommendation_service import RecommendationService


def serialization_status(novel) -> str:
    if novel.finish:
        return "완결"
    if novel.pause:
        return "휴재"
    return "연재 중"


def payment_status(novel) -> str:
    if novel.free is True:
        return "무료"
    if novel.paid_serial is True or novel.free is False:
        return "유료"
    return "무료/유료 정보 없음"


def analysis_score_label(score: float | None) -> str:
    if score is None:
        return "분석 전"
    return f"{score:.1f} / 100"


st.set_page_config(page_title="작가 작품 조회", layout="wide")
st.title("작가 작품 조회")
st.caption("작가 ID로 현재 연재 중이거나 과거에 연재한 모든 수집 작품을 확인합니다.")

repository = Repository()
service = NovelService(repository=repository)
recommendation_service = RecommendationService(repository=repository)
query_author_id = st.query_params.get("author_id", "")
author_input = st.text_input(
    "작가 ID",
    value=str(query_author_id),
    placeholder="예: 12345",
)

if st.button("조회", type="primary") or query_author_id:
    try:
        author_id = service.parse_author_id(author_input)
        author = service.get_author_by_id(author_id)
        if author is None:
            st.error(f"해당 작가를 찾을 수 없습니다. (ID: {author_id})")
            st.stop()

        novels = service.get_novels_by_author(author_id)
        scores_by_novel_id = recommendation_service.get_novel_scores(
            [novel.novel_id for novel in novels]
        )
        st.subheader(author.author_name or f"작가 {author_id}")
        st.caption(f"작가 ID {author_id} · 총 {len(novels):,}개 작품")

        if not novels:
            st.info("수집된 작품이 없습니다.")

        for novel in novels:
            with st.container(border=True):
                cover_col, body_col, status_col = st.columns([1, 4, 1.5])
                with cover_col:
                    if novel.origin_cover_url:
                        st.image(novel.origin_cover_url, use_container_width=True)
                with body_col:
                    st.markdown(f"### {novel.title}")
                    st.page_link(
                        "pages/novel_basic_info.py",
                        label="작품 상세 보기",
                        icon=":material/arrow_forward:",
                        query_params={"url": str(novel.novel_id)},
                    )
                with status_col:
                    st.write(f"**연재 상태**  \n{serialization_status(novel)}")
                    st.write(f"**이용 구분**  \n{payment_status(novel)}")
                    score = scores_by_novel_id.get(novel.novel_id)
                    st.write("**유료 전환 타깃 점수**")
                    st.write(analysis_score_label(score))
    except NovelServiceError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"작가 정보를 불러오지 못했습니다: {exc}")
