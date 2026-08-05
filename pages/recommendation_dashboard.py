from __future__ import annotations

import altair as alt
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
def load_recommendations(genre_id: int, limit: int) -> list[dict]:
    return RecommendationService(Repository()).get_ranked_novels(genre_id, limit=limit)


@st.cache_data(ttl="15m", max_entries=100)
def load_episode_dropout(novel_id: int) -> list[dict]:
    return RecommendationService(Repository()).get_episode_dropout(novel_id)


def percent(numerator: int, denominator: int) -> float:
    return numerator / denominator * 100 if denominator else 0.0


def decision_label(score: float) -> str:
    if score >= 80:
        return "최우선 검토"
    if score >= 65:
        return "적극 검토"
    if score >= 50:
        return "관찰 후보"
    return "보류"


st.title("무료 → 유료 전환 추천 센터")
st.caption("독자 유지력 모델과 실제 독자 반응을 결합한 문피아 매니저용 의사결정 화면")

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

genre_labels = {
    f"{row['genre_name'] or '미분류'} ({int(row['novel_count']):,}편)": int(row["genre_id"])
    for row in genres
}

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
            4. 26화 이후 이탈률 점수는 같은 조회수 구간 안에서 순서를 결정합니다.

            추천·선호 수와 댓글 감성은 순위 산식에 넣지 않은 **보조 지표**입니다.
            """
        )

selected_genre_id = genre_labels[selected_genre_label]
recommendations = load_recommendations(selected_genre_id, int(candidate_count or 20))
if not recommendations:
    st.info("선택한 장르에는 점수가 계산된 후보가 없습니다.")
    st.stop()

score_values = [float(row["recommendation_score"]) for row in recommendations]
dropout_values = [float(row["average_dropout_rate"]) * 100 for row in recommendations]
with st.container(horizontal=True):
    st.metric("분석 장르", recommendations[0]["genre_name"], border=True)
    st.metric("전환 후보", f"{len(recommendations):,}편", border=True)
    st.metric("평균 타깃 점수", f"{sum(score_values) / len(score_values):.1f}", border=True)
    st.metric("후보 평균 이탈률", f"{sum(dropout_values) / len(dropout_values):.2f}%", border=True)

ranking_frame = pd.DataFrame(
    {
        "순위": [row["rank"] for row in recommendations],
        "작품명": [row["title"] for row in recommendations],
        "작가": [row["author_name"] or "정보 없음" for row in recommendations],
        "판단": [
            row.get("decision_label")
            or decision_label(float(row["recommendation_score"]))
            for row in recommendations
        ],
        "타깃 점수": score_values,
        "조회 규모": [row["view_grade"] for row in recommendations],
        "기준 조회수": [int(row["reference_view_count"]) for row in recommendations],
        "유지 점수": [float(row["retention_score"]) for row in recommendations],
        "예상 구매": [int(row["predicted_purchase_count"]) for row in recommendations],
        "예상 구매 전환율": [
            float(row["predicted_conversion_rate"])
            for row in recommendations
        ],
        "예상 유료 이탈률": [
            float(row["predicted_paid_dropout_rate"])
            for row in recommendations
        ],
        "평균 이탈률": [value / 100 for value in dropout_values],
        "추천·선호": [int(row["preference_count"]) for row in recommendations],
        "연재 회차": [int(row["chapter_count"]) for row in recommendations],
        "긍정 댓글": [int(row["positive_count"]) for row in recommendations],
        "부정 댓글": [int(row["negative_count"]) for row in recommendations],
        "중립 댓글": [int(row["neutral_count"]) for row in recommendations],
    }
)

st.subheader(f"{recommendations[0]['genre_name']} 전환 후보 순위")
selection = st.dataframe(
    ranking_frame,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "작품명": st.column_config.TextColumn(pinned=True),
        "타깃 점수": st.column_config.ProgressColumn(
            min_value=0, max_value=100, format="%.1f점"
        ),
        "기준 조회수": st.column_config.NumberColumn(format="localized"),
        "유지 점수": st.column_config.NumberColumn(format="%.1f점"),
        "예상 구매": st.column_config.NumberColumn(format="localized"),
        "예상 구매 전환율": st.column_config.NumberColumn(format="percent"),
        "예상 유료 이탈률": st.column_config.NumberColumn(format="percent"),
        "평균 이탈률": st.column_config.NumberColumn(format="percent"),
        "추천·선호": st.column_config.NumberColumn(format="localized"),
        "긍정 댓글": st.column_config.NumberColumn(format="localized"),
        "부정 댓글": st.column_config.NumberColumn(format="localized"),
        "중립 댓글": st.column_config.NumberColumn(format="localized"),
    },
)
selected_index = selection.selection.rows[0] if selection.selection.rows else 0
selected = recommendations[selected_index]

st.subheader(f"#{selected['rank']} {selected['title']}")
summary_col, score_col = st.columns([3, 1], vertical_alignment="center")
with summary_col:
    st.markdown(f"**{selected['author_name'] or '작가 정보 없음'} · {selected['genre_name']}**")
    st.write(selected.get("introduction") or "작품 소개가 수집되지 않았습니다.")
    if selected.get("source_url"):
        st.link_button(
            "문피아에서 작품 보기",
            selected["source_url"],
            icon=":material/open_in_new:",
        )
with score_col:
    st.metric(
        "유료 전환 타깃 점수",
        f"{float(selected['recommendation_score']):.1f} / 100",
        selected.get("decision_label")
        or decision_label(float(selected["recommendation_score"])),
        border=True,
    )

with st.container(border=True):
    st.markdown("#### 모델이 이 작품을 추천하는 이유")
    st.write(selected["recommendation_reason"])

with st.container(border=True):
    st.markdown("#### 25화 무료 → 첫 유료 회차 전환 예측")
    with st.container(horizontal=True):
        st.metric(
            "예상 구매 수",
            f"{int(selected['predicted_purchase_count']):,}건",
            border=True,
        )
        st.metric(
            "예상 구매 전환율",
            f"{float(selected['predicted_conversion_rate']) * 100:.1f}%",
            border=True,
        )
        st.metric(
            "예상 유료 이탈률",
            f"{float(selected['predicted_paid_dropout_rate']) * 100:.1f}%",
            border=True,
        )
        st.metric(
            "모델 평균 오차",
            f"±{float(selected['conversion_model_mae']) * 100:.2f}%p",
            border=True,
        )
    st.caption(
        f"실제 전환 작품 {int(selected['conversion_training_samples']):,}편을 학습했습니다. "
        "26화가 공지인 작품은 27화의 첫 실제 유료 구매수를 사용했습니다."
    )

positive_count = int(selected["positive_count"])
negative_count = int(selected["negative_count"])
neutral_count = int(selected["neutral_count"])
comment_total = positive_count + negative_count + neutral_count
with st.container(horizontal=True):
    st.metric("조회 규모", selected["view_grade"], border=True)
    st.metric("기준 조회수", f"{int(selected['reference_view_count']):,}", border=True)
    st.metric("조회수 상한", f"{int(selected['view_scale_max']):,}", border=True)
    st.metric("독자 유지 점수", f"{float(selected['retention_score']):.1f}", border=True)
    st.metric("누적 조회", f"{int(selected['view_count']):,}", border=True)
    st.metric("추천·선호", f"{int(selected['preference_count']):,}", border=True)
    st.metric("연재 회차", f"{int(selected['chapter_count']):,}화", border=True)
    st.metric(
        "평균 회차 이탈률",
        f"{float(selected['average_dropout_rate']) * 100:.2f}%",
        border=True,
    )
    st.metric(
        "긍정 댓글 비율",
        f"{percent(positive_count, comment_total):.1f}%",
        border=True,
    )

episode_rows = load_episode_dropout(int(selected["novel_id"]))
episode_frame = pd.DataFrame(episode_rows)
sentiment_frame = pd.DataFrame(
    {
        "감성": ["긍정", "부정", "중립"],
        "댓글 수": [positive_count, negative_count, neutral_count],
    }
)

dropout_col, sentiment_col = st.columns([3, 2])
with dropout_col.container(border=True):
    st.markdown("#### 회차별 독자 이탈률")
    if episode_frame.empty:
        st.info("이탈률을 계산할 수 있는 회차가 없습니다.")
    else:
        episode_frame["이탈률"] = pd.to_numeric(episode_frame["dropout_rate"])
        episode_frame["위험"] = episode_frame["이탈률"].ge(0.10).map(
            {True: "주의 구간", False: "안정 구간"}
        )
        chart = (
            alt.Chart(episode_frame)
            .mark_line(point=True)
            .encode(
                x=alt.X("episode_number:Q", title="회차"),
                y=alt.Y("이탈률:Q", title="이탈률", axis=alt.Axis(format="%")),
                color=alt.Color("위험:N", scale=alt.Scale(
                    domain=["안정 구간", "주의 구간"], range=["#2563eb", "#dc2626"]
                )),
                tooltip=[
                    alt.Tooltip("episode_number:Q", title="회차"),
                    alt.Tooltip("access_type:N", title="구간"),
                    alt.Tooltip("previous_view_count:Q", title="직전 조회", format=","),
                    alt.Tooltip("view_count:Q", title="현재 조회", format=","),
                    alt.Tooltip("이탈률:Q", title="이탈률", format=".2%"),
                ],
            )
            .properties(height=330)
        )
        st.altair_chart(chart)
        worst = episode_frame.nlargest(3, "이탈률")
        if not worst.empty:
            episodes_text = ", ".join(
                f"{int(row.episode_number)}화({row['이탈률']:.1%})"
                for _, row in worst.iterrows()
            )
            st.caption(f"우선 점검할 이탈 구간: {episodes_text}")

with sentiment_col.container(border=True):
    st.markdown("#### 댓글 감성 구성")
    if comment_total:
        sentiment_chart = (
            alt.Chart(sentiment_frame)
            .mark_arc(innerRadius=65)
            .encode(
                theta=alt.Theta("댓글 수:Q"),
                color=alt.Color(
                    "감성:N",
                    scale=alt.Scale(
                        domain=["긍정", "부정", "중립"],
                        range=["#16a34a", "#dc2626", "#94a3b8"],
                    ),
                    legend=alt.Legend(title=None, orient="bottom"),
                ),
                tooltip=["감성:N", alt.Tooltip("댓글 수:Q", format=",")],
            )
            .properties(height=260)
        )
        st.altair_chart(sentiment_chart)
        st.caption(
            f"긍정 {positive_count:,} · 부정 {negative_count:,} · 중립 {neutral_count:,}"
        )
    else:
        st.info("분석된 댓글이 없습니다.")

with st.expander("점수 해석과 주의사항", icon=":material/info:"):
    st.markdown(
        """
        - **타깃 점수**는 조회수 등급의 20점 구간에 독자 유지 점수의 20%를 더한 값입니다.
        - 조회수 구간은 10부터 수집된 무료 작품의 최대 기준 조회수까지 로그 간격으로 5등분합니다.
        - 수집 자료의 최대 기준 조회수가 10만 이상이면 점수 상한은 10만으로 고정합니다.
        - **기준 조회수**는 최신 게시일보다 최소 7일 전에 게시된 가장 최근 회차의 조회수입니다.
        - **유료 전환 예측**은 실제 25화 FREE→26화 PAID 사례를 학습하며, 26화가 공지면 27화를 사용합니다.
        - 예상 구매 수와 이탈률은 평균 오차가 있는 모델 추정치이며 확정 매출이 아닙니다.
        - **평균 이탈률**은 직전 회차 대비 조회 감소 비율이며 상승 회차는 0%로 처리합니다.
        - 조회수가 0인 회차는 직전 조회수와 관계없이 이탈률 100%와 최저 점수를 적용합니다.
        - **추천·선호 및 댓글 감성**은 모델 순위와 독립된 운영 보조 지표입니다.
        - 댓글 감성은 키워드 기반 분류이므로 문맥·반어 표현을 완전히 해석하지 못할 수 있습니다.
        """
    )
