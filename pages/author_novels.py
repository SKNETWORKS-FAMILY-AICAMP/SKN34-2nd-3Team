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
    if novel.free == 1:
        return "무료"
    if novel.paid_serial == 1 or novel.free == 0:
        return "유료"
    return "무료/유료 정보 없음"


def analysis_score_label(score: float | None) -> str:
    if score is None:
        return "분석 대상 아님"
    return f"{score:.1f} / 100"


def render_analysis_score(score: float | None) -> None:
    if score is None:
        st.markdown(
            '<span style="display:inline-block;padding:0.2rem 0.55rem;'
            'border-radius:999px;background:#fee2e2;color:#b91c1c;'
            'font-weight:600;">분석 대상 아님</span>',
            unsafe_allow_html=True,
        )
        return
    st.write(analysis_score_label(score))


def format_views(value) -> str:
    if value is None:
        return "—"
    return f"{round(float(value)):,}"


def render_top_authors(service: NovelService) -> None:
    st.subheader("작품별 평균 누적 조회수 상위 작가")
    st.caption("조회수가 있는 작품만 평균과 합계에 반영합니다.")
    rows = service.list_top_authors_by_average_view(limit=10)
    if not rows:
        st.info("표시할 작가가 없습니다.")
        return
    for rank, row in enumerate(rows, start=1):
        with st.container(border=True):
            st.caption(f"순위 {rank}")
            st.page_link(
                "pages/author_novels.py",
                label=row.get("author_name") or f"작가 {row['author_id']}",
                query_params={"author_id": str(row["author_id"])},
            )
            st.write(f"평균 누적 조회수 · {format_views(row.get('average_view_count'))}")
            st.write(f"누적 조회수 합계 · {format_views(row.get('total_view_count'))}")
            st.write(
                "반영 작품 수/전체 작품 수 · "
                f"{int(row.get('reflected_novel_count') or 0):,}/"
                f"{int(row.get('total_novel_count') or 0):,}"
            )


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
is_clicked = st.button("조회", type="primary")
detail_requested = bool(query_author_id or is_clicked)

if not detail_requested:
    render_top_authors(service)

if detail_requested:
    try:
        author_id = service.parse_author_id(author_input)
        author = service.get_author_by_id(author_id)
        if author is None:
            st.error(f"해당 작가를 찾을 수 없습니다. (ID: {author_id})")
            st.stop()

        novels = service.get_novels_by_author(author_id)
        scores_by_novel_id = recommendation_service.get_author_analysis(
            [novel.novel_id for novel in novels]
        )
        average_integrated, reflected_work_count = (
            recommendation_service.author_average_integrated_score(scores_by_novel_id)
        )
        st.subheader(author.author_name or f"작가 {author_id}")
        st.caption(f"작가 ID {author_id} · 총 {len(novels):,}개 작품")
        if author.author_url:
            st.link_button(
                "작가 개인 페이지",
                author.author_url,
                icon=":material/open_in_new:",
            )
        score_coverage_col, integrated_summary_col = st.columns(2)
        with score_coverage_col:
            with st.container(border=True):
                st.caption("개별 추천 지표")
                st.metric("분석 작품", f"{len(scores_by_novel_id):,} / {len(novels):,}")
        with integrated_summary_col:
            with st.container(border=True):
                st.caption("작가 평균 통합점수")
                integrated_value = (
                    f"{average_integrated:.1f} / 100"
                    if average_integrated is not None
                    else "— / 100"
                )
                st.metric(
                    "평균 점수",
                    integrated_value,
                    help=f"반영 작품 {reflected_work_count:,}개",
                )
                st.caption(f"반영 작품 {reflected_work_count:,}개")

        if not novels:
            st.info("수집된 작품이 없습니다.")

        for novel in novels:
            with st.container(border=True):
                cover_col, body_col = st.columns([1, 3])
                with cover_col:
                    if novel.origin_cover_url:
                        st.image(novel.origin_cover_url, width="stretch")
                with body_col:
                    st.markdown(f"### {novel.title}")
                    st.page_link(
                        "pages/novel_basic_info.py",
                        label="작품 상세 보기",
                        icon=":material/arrow_forward:",
                        query_params={"url": str(novel.novel_id)},
                    )
                    metadata_cols = st.columns(7)
                    with metadata_cols[0]:
                        st.caption("연재 상태")
                        st.write(serialization_status(novel))
                    with metadata_cols[1]:
                        st.caption("이용 구분")
                        st.write(payment_status(novel))
                    with metadata_cols[2]:
                        st.caption("조회 규모 점수")
                    scores = scores_by_novel_id.get(novel.novel_id, {})
                    with metadata_cols[2]:
                        render_analysis_score(scores.get("view_scale_score"))
                    with metadata_cols[3]:
                        st.caption("FREE 유지 점수")
                        render_analysis_score(scores.get("free_retention_score"))
                    with metadata_cols[4]:
                        st.caption("PAID 유지 점수")
                        render_analysis_score(scores.get("paid_retention_score"))
                    with metadata_cols[5]:
                        st.caption("댓글 반응 점수")
                        render_analysis_score(scores.get("reaction_score"))
                    with metadata_cols[6]:
                        st.caption("작품 통합점수")
                        render_analysis_score(scores.get("integrated_average_score"))
    except NovelServiceError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"작가 정보를 불러오지 못했습니다: {exc}")
