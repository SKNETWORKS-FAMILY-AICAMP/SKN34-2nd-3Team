from __future__ import annotations

import pandas as pd
import streamlit as st

from repository.repository import Repository
from service.recommendation_service import RecommendationService


st.set_page_config(
    page_title="문피아 유료 전환 추천",
    page_icon=":material/leaderboard:",
    layout="wide",
)


@st.cache_data(ttl="15m", max_entries=5)
def load_genres() -> list[dict]:
    return RecommendationService(Repository()).list_genres()


@st.cache_data(ttl="15m", max_entries=100)
def load_recommendations(genre_id: int | None, limit: int) -> list[dict]:
    service = RecommendationService(Repository())
    return service.get_ranked_novels(genre_id, limit=limit)


st.title("무료 → 유료 전환 추천 센터")
st.caption("무료 연재 작품의 조회 규모와 독자 유지력을 한눈에 비교합니다.")

try:
    genres = load_genres()
except Exception as exc:
    st.error(
        "추천 데이터 테이블을 불러오지 못했습니다. "
        "V3 추천 지표 마이그레이션을 먼저 실행해 주세요.",
        icon=":material/database_off:",
    )
    st.exception(exc)
    st.stop()

if not genres:
    st.warning("분석 가능한 무료 연재 작품이 없습니다.", icon=":material/warning:")
    st.stop()

all_genres_label = f"전체 ({sum(int(row['novel_count']) for row in genres):,}편)"
genre_labels = {all_genres_label: None}
genre_labels.update(
    {
        f"{row['genre_name'] or '미분류'} ({int(row['novel_count']):,}편)": int(row["genre_id"])
        for row in genres
    }
)

with st.sidebar:
    st.subheader("분석 조건")
    selected_genre_label = st.selectbox("장르", options=list(genre_labels))
    candidate_count = st.segmented_control(
        "후보 수", options=[10, 20, 30], default=20
    )
    st.caption(
        "30화 이상 연재된 작품만 분석하며, "
        "완결·연재중단·기유료 작품은 후보에서 제외됩니다."
    )
    with st.expander("모델 산식", icon=":material/function:"):
        st.markdown(
            """
            1. 초기 이탈 구간인 1~25화와 FREE/PAID 전환 회차를 제외합니다.
            2. 최신 게시일보다 7일 이상 지난 가장 최근 회차를 기준 조회수로 사용합니다.
            3. 조회수 10부터 데이터 기반 최대값까지 로그 간격으로 5등급을 나눕니다.
            4. 조회 규모 점수는 1.25배, 댓글 반응은 0~100으로 변환한 뒤 사용 가능한 구성요소를 동일 가중 평균합니다.
            """
        )

selected_genre_id = genre_labels[selected_genre_label]
recommendations = load_recommendations(selected_genre_id, int(candidate_count or 20))
if not recommendations:
    st.info("선택한 장르에는 점수가 계산된 후보가 없습니다.")
    st.stop()

selected_genre_name = "전체" if selected_genre_id is None else recommendations[0]["genre_name"]


def queue_author_navigation() -> None:
    click = st.session_state.get("recommendation_author_button")
    if click is None:
        return

    clicked_row = int(click["row"])
    if not 0 <= clicked_row < len(recommendations):
        return

    author_id = recommendations[clicked_row].get("author_id")
    if author_id is None:
        return

    st.session_state["recommendation_author_target"] = str(author_id)


integrated_scores = [float(row["integrated_average_score"]) for row in recommendations]
with st.container(horizontal=True):
    st.metric("분석 장르", selected_genre_name, border=True)
    st.metric("무료 후보 수", f"{len(recommendations):,}편", border=True)
    st.metric("평균 통합 점수", f"{sum(integrated_scores) / len(integrated_scores):.1f}", border=True)

st.subheader("상위 3개 작품")
card_columns = st.columns(3, gap="medium")
for column, row in zip(card_columns, recommendations[:3]):
    with column:
        with st.container(border=True):
            st.markdown(f"### {int(row['rank'])}위")
            if row.get("origin_cover_url"):
                st.image(row["origin_cover_url"], width="stretch")
            st.page_link(
                "pages/novel_basic_info.py",
                label=f"🔗 {row['title']}",
                query_params={"url": str(row["novel_id"])},
            )
            if row.get("author_id") is not None:
                st.page_link(
                    "pages/author_novels.py",
                    label=f"작가 · {row['author_name'] or '정보 없음'}",
                    query_params={"author_id": str(row["author_id"])},
                )
            else:
                st.caption("작가 · 정보 없음")
            st.metric("통합 평균 점수", f"{float(row['integrated_average_score']):.1f}점")
            st.caption(f"기준 조회수 · {int(row['reference_view_count']):,}회")

ranking_frame = pd.DataFrame(
    {
        "순위": [row["rank"] for row in recommendations],
        "작품명": [row["title"] for row in recommendations],
        "작가": [row["author_name"] or "정보 없음" for row in recommendations],
        "통합 평균 점수": integrated_scores,
        "조회 규모": [row["view_grade"] for row in recommendations],
        "기준 조회수": [int(row["reference_view_count"]) for row in recommendations],
    }
)

st.subheader(f"{selected_genre_name} 전환 후보 순위")
st.dataframe(
    ranking_frame,
    hide_index=True,
    column_config={
        "순위": st.column_config.NumberColumn("순위", width="small"),
        "작품명": st.column_config.ButtonColumn(
            "작품명",
            key="recommendation_novel_button",
            width="medium",
        ),
        "작가": st.column_config.ButtonColumn(
            "작가",
            on_click=queue_author_navigation,
            key="recommendation_author_button",
            width="small",
        ),
        "통합 평균 점수": st.column_config.ProgressColumn(
            "통합 점수", min_value=0, max_value=100, format="%.1f점", width="small"
        ),
        "조회 규모": st.column_config.TextColumn("조회 규모", width="small"),
        "기준 조회수": st.column_config.NumberColumn(
            "기준 조회수", format="localized", width="small"
        ),
    },
)

novel_clicked = st.session_state.get("recommendation_novel_button")
if novel_clicked is not None:
    clicked_row = int(novel_clicked["row"])
    if 0 <= clicked_row < len(recommendations):
        novel_id = str(recommendations[clicked_row]["novel_id"])
        st.switch_page(
            "pages/novel_basic_info.py",
            query_params={"url": novel_id},
        )

author_id = st.session_state.pop("recommendation_author_target", None)
if author_id is not None:
    st.switch_page(
        "pages/author_novels.py",
        query_params={"author_id": author_id},
    )

with st.expander("점수 해석과 주의사항", icon=":material/info:"):
    st.markdown(
        """
        - **통합 평균 점수**는 조회 규모(1.25배), FREE/PAID 유지, 댓글 반응(0~100 변환) 중 사용 가능한 점수의 동일 가중 평균입니다.
        - 조회수 구간은 10부터 수집된 무료 작품의 최대 기준 조회수까지 로그 간격으로 5등분합니다.
        - 수집 자료의 최대 기준 조회수가 10만 이상이면 점수 상한은 10만으로 고정합니다.
        - **기준 조회수**는 최신 게시일보다 최소 7일 전에 게시된 가장 최근 회차의 조회수입니다.
        - 결측 점수는 0점으로 대체하지 않으며, 값이 있는 점수만 평균에 참여합니다.
        - 분석 댓글이 0개인 작품은 댓글 반응 점수를 결측으로 제외합니다.
        """
    )
