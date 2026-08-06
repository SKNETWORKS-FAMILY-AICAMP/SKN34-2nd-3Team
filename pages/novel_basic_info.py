from __future__ import annotations

import os
import re
import sys
from dataclasses import asdict
from math import ceil
from typing import Any

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

import altair as alt
import pandas as pd
import streamlit as st
from streamlit_extras.card_selector import card_selector

from repository.repository import Repository
from service.comment_sentiment_service import (
    CommentSentimentService,
    CommentSentimentServiceError,
)
from service.novel_prediction_service import NovelPredictionService
from service.novel_service import NovelService
from service.novel_service_errors import NovelServiceError


LABEL_KO = {
    "positive": "🟢 긍정",
    "neutral": "⚪ 중립",
    "negative": "🔴 부정",
    "unanalyzed": "⚫ 미분석",
    None: "⚫ 미분석",
}

LABEL_SHORT_KO = {
    "positive": "긍정",
    "neutral": "중립",
    "negative": "부정",
}


# -----------------------------------------------------------------------------
# 공통 포맷
# -----------------------------------------------------------------------------
def safe_int(value: Any) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def safe_float(value: Any) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def format_number(value: Any) -> str:
    return f"{safe_int(value):,}"


def format_percent(value: Any, digits: int = 1) -> str:
    return f"{safe_float(value):.{digits}f}%"


def format_datetime(value: Any) -> str:
    if value in (None, "") or pd.isna(value):
        return "-"
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value)
    return parsed.strftime("%Y-%m-%d %H:%M")


def access_label(value: Any) -> str:
    return "무료 회차" if str(value or "").strip().upper() == "FREE" else "유료 회차"


def reaction_description(score: float) -> str:
    if score >= 50:
        return "매우 긍정적"
    if score >= 20:
        return "긍정적"
    if score > -20:
        return "중립적"
    if score > -50:
        return "부정적"
    return "매우 부정적"


def reliability_help(count: int) -> str:
    if count <= 0:
        return "감정분석된 댓글이 없습니다."
    if count < 5:
        return "분석 댓글이 5개 미만이므로 비율 해석에 주의해야 합니다."
    if count < 20:
        return "분석 댓글이 20개 미만이므로 참고용 지표입니다."
    return "분석 댓글이 20개 이상인 일반 분석 구간입니다."


# -----------------------------------------------------------------------------
# 기존 작품 정보 영역
# -----------------------------------------------------------------------------
def render_novel_header(novel: Any, service: NovelService, novel_id: int) -> None:
    st.markdown("---")
    col_img, col_info = st.columns([1, 4])

    with col_img:
        if novel.origin_cover_url:
            st.image(novel.origin_cover_url, width=150)

    with col_info:
        st.header(f"📘 {novel.title}")
        st.write(
            f"**소설 ID:** {novel.novel_id} | "
            f"**유료 연재 여부:** {'무료' if novel.free else '유료'}"
        )

        author = service.get_author(novel_id)
        if author:
            author_str = (
                f"{author.author_name}(일러스트레이터)"
                if author.is_illustrator
                else author.author_name
            )
        else:
            author_str = "정보 없음"

        st.write(f"**작가:** {author_str}")
        st.write(
            f"**작품 소개:** "
            f"{novel.introduction if novel.introduction else '정보 없음'}"
        )

        if novel.source_url:
            st.markdown(f"🔗 [작품 원본 링크]({novel.source_url})")


def render_novel_statistics(stats: Any) -> None:
    if not stats:
        return

    st.markdown("---")
    st.subheader("📊 작품 통계")
    col1, col2, col3 = st.columns(3)
    col1.metric("총 조회수", format_number(stats.view_count))
    col2.metric("선호작 수", format_number(stats.preference_count))
    col3.metric("총 회차", format_number(stats.chapter_count))

    st.markdown("##### 👥 독자 성별 및 연령대 비율")
    stat_col1, stat_col2 = st.columns(2)

    with stat_col1:
        raw_male = safe_int(stats.male_count)
        raw_female = safe_int(stats.female_count)
        total_gender = raw_male + raw_female
        if total_gender > 0:
            male_pct = round(raw_male / total_gender * 100, 1)
            female_pct = round(raw_female / total_gender * 100, 1)
        else:
            male_pct, female_pct = 50.0, 50.0

        gender_df = pd.DataFrame(
            {
                "성별": ["남성", "여성"],
                "비율": [male_pct, female_pct],
            }
        )
        gender_chart = (
            alt.Chart(gender_df)
            .mark_arc(innerRadius=50)
            .encode(
                theta=alt.Theta(field="비율", type="quantitative"),
                color=alt.Color(field="성별", type="nominal"),
                tooltip=[
                    alt.Tooltip("성별", title="성별"),
                    alt.Tooltip("비율", title="비율 (%)", format=".1f"),
                ],
            )
            .properties(title="성별 독자 비율", height=200)
        )
        st.altair_chart(gender_chart, width="stretch")

    with stat_col2:
        age_df = pd.DataFrame(
            {
                "연령대": ["10대", "20대", "30대", "40대", "50대 이상"],
                "비율": [
                    stats.age_10s_percent or 0,
                    stats.age_20s_percent or 0,
                    stats.age_30s_percent or 0,
                    stats.age_40s_percent or 0,
                    stats.age_50s_percent or 0,
                ],
            }
        )
        if age_df["비율"].sum() == 0:
            age_df["비율"] = [20, 20, 20, 20, 20]
        age_chart = (
            alt.Chart(age_df)
            .mark_bar()
            .encode(
                x=alt.X(
                    "연령대:N",
                    sort=None,
                    title=None,
                    axis=alt.Axis(labelAngle=0),
                ),
                y=alt.Y("비율:Q", title=None),
                color=alt.Color("연령대:N", legend=None),
                tooltip=["연령대", "비율"],
            )
            .properties(title="연령대별 독자 비중", height=200)
        )
        st.altair_chart(age_chart, width="stretch")


def render_prediction_section(
    *,
    novel: Any,
    novel_id: int,
    service: NovelService,
    prediction_service: NovelPredictionService,
) -> None:
    st.markdown("---")
    st.subheader("📈 향후 조회수 예측 시뮬레이션")

    selected_model = card_selector(
        [
            dict(
                icon=":material/smart_toy:",
                title="AI 맞춤형 예측 (Random Forest)",
                description=(
                    "작품의 장르, 분량, 독자 반응 등을 분석해 "
                    "정밀하게 예측합니다."
                ),
            ),
            dict(
                icon=":material/bar_chart:",
                title="통계 기반 예측 (전체 평균)",
                description=(
                    "전체 작품의 평균 무료→유료 전환 낙폭을 적용한 "
                    "수치를 노출합니다."
                ),
            ),
        ],
        key="prediction_model_selector",
    )

    is_ml_mode = selected_model in (0, None)

    with st.spinner("AI 예측 모델 및 그래프 데이터를 계산하는 중입니다..."):
        prediction_result = prediction_service.get_prediction_data(
            novel_id,
            is_ml=is_ml_mode,
        )

    if prediction_result is None:
        st.info("그래프를 렌더링하기 위한 회차 데이터가 없습니다.")
        return

    pred_df, drop_rate = prediction_result
    if pred_df.empty:
        st.info("그래프를 렌더링하기 위한 데이터가 부족합니다.")
        return

    pred_df = pred_df.copy()
    if not novel.free and "구분" in pred_df.columns:
        episodes_raw = service.get_episodes(novel_id)
        free_count = sum(
            1
            for episode in episodes_raw
            if str(episode.access_type).strip().upper() == "FREE"
        )
        if free_count == 0:
            free_count = int(len(pred_df) * 0.3)

        def categorize_segment(row: pd.Series) -> str:
            if row["구분"] != "실제 조회수":
                return "예상 조회수"
            if row["회차"] <= free_count:
                return "실제 조회수 (무료 회차)"
            return "실제 조회수 (유료 회차)"

        pred_df["구분"] = pred_df.apply(categorize_segment, axis=1)
        dash_condition = alt.condition(
            alt.datum.구분 == "예상 조회수",
            alt.value([5, 5]),
            alt.value([0]),
        )
    else:
        dash_condition = alt.condition(
            alt.datum.구분 == "실제 조회수",
            alt.value([0]),
            alt.value([5, 5]),
        )

    st.metric(
        label="다음 화(예측 1화) 조회수 예상 낙폭",
        value=f"-{drop_rate}%",
        delta=f"-{drop_rate}% (감소 예상)",
        delta_color="normal",
    )

    chart = (
        alt.Chart(pred_df)
        .mark_line(point=True)
        .encode(
            x=alt.X("회차:Q", title="회차", scale=alt.Scale(zero=False)),
            y=alt.Y("조회수:Q", title="조회수"),
            color=alt.Color("구분:N"),
            strokeDash=dash_condition,
            tooltip=["회차", "조회수", "구분"],
        )
        .properties(height=400)
    )
    st.altair_chart(chart, width="stretch")

    if novel.free:
        if is_ml_mode:
            st.info(
                "💡 Random Forest 모델이 작품 특성을 바탕으로 계산한 "
                "맞춤형 유료 전환 시뮬레이션입니다."
            )
        else:
            st.info(
                "💡 전체 작품의 무료→유료 전환 평균 낙폭을 적용한 "
                "시뮬레이션입니다."
            )
    else:
        st.info(
            "💡 전체 유료 작품에서 관찰된 자연 감소율을 바탕으로 한 "
            "시뮬레이션입니다."
        )
    st.caption("ℹ️ 본 시뮬레이션 모델은 ±12 내외의 오차율을 보일 수 있습니다.")


# -----------------------------------------------------------------------------
# 작품/회차 댓글 반응 분석 영역
# -----------------------------------------------------------------------------
def build_episode_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows)
    numeric_columns = [
        "episode_id",
        "episode_number",
        "view_count",
        "like_count",
        "source_comment_count",
        "stored_comment_count",
        "analyzed_comment_count",
        "positive_count",
        "neutral_count",
        "negative_count",
        "positive_ratio",
        "neutral_ratio",
        "negative_ratio",
        "reaction_score",
        "average_confidence",
    ]
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)

    if "published_at" in frame.columns:
        frame["published_at"] = pd.to_datetime(frame["published_at"], errors="coerce")

    frame["access_label"] = frame["access_type"].map(access_label)
    frame["reaction_description"] = frame["reaction_score"].map(reaction_description)
    return frame


def render_novel_reaction_overview(overview: dict[str, Any]) -> None:
    analyzed = safe_int(overview.get("analyzed_comment_count"))
    stored = safe_int(overview.get("stored_comment_count"))
    positive_ratio = safe_float(overview.get("positive_ratio"))
    neutral_ratio = safe_float(overview.get("neutral_ratio"))
    negative_ratio = safe_float(overview.get("negative_ratio"))
    reaction_score = safe_float(overview.get("reaction_score"))
    confidence = safe_float(overview.get("average_confidence")) * 100

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("수집 댓글", f"{stored:,}")
    col2.metric("분석 댓글", f"{analyzed:,}")
    col3.metric("긍정", format_percent(positive_ratio))
    col4.metric("중립", format_percent(neutral_ratio))
    col5.metric("부정", format_percent(negative_ratio))
    col6.metric(
        "독자 반응 점수",
        f"{reaction_score:+.1f}",
        help="긍정 비율 - 부정 비율, 범위 -100~+100",
    )

    st.caption(
        f"평균 모델 신뢰도 {confidence:.1f}% · "
        f"신뢰도 구간: {overview.get('reliability', '-')} · "
        f"마지막 댓글 수집 {format_datetime(overview.get('last_collected_at'))} · "
        f"마지막 분석 {format_datetime(overview.get('last_analyzed_at'))}"
    )
    if analyzed < 20:
        st.warning(reliability_help(analyzed))


def render_episode_trend_charts(frame: pd.DataFrame) -> None:
    if frame.empty or frame["analyzed_comment_count"].sum() <= 0:
        st.info("회차별 감정분석 데이터가 없습니다.")
        return

    view_col1, view_col2 = st.columns([3, 1])
    with view_col1:
        range_option = st.selectbox(
            "그래프 표시 범위",
            ["최근 50화", "최근 100화", "전체 회차"],
            index=1,
            key="reaction_chart_range",
            label_visibility="collapsed",
        )
    with view_col2:
        include_empty = st.toggle(
            "미분석 회차 포함",
            value=False,
            key="reaction_include_empty",
        )

    chart_frame = frame.copy()
    if not include_empty:
        chart_frame = chart_frame[chart_frame["analyzed_comment_count"] > 0]
    if range_option == "최근 50화":
        chart_frame = chart_frame.tail(50)
    elif range_option == "최근 100화":
        chart_frame = chart_frame.tail(100)

    ratio_tab, score_tab, count_tab = st.tabs(
        ["감정 비율", "반응 점수", "댓글 수"]
    )

    with ratio_tab:
        ratio_frame = chart_frame[
            [
                "episode_number",
                "episode_title",
                "analyzed_comment_count",
                "positive_ratio",
                "neutral_ratio",
                "negative_ratio",
            ]
        ].melt(
            id_vars=[
                "episode_number",
                "episode_title",
                "analyzed_comment_count",
            ],
            value_vars=["positive_ratio", "neutral_ratio", "negative_ratio"],
            var_name="label",
            value_name="ratio",
        )
        ratio_frame["감정"] = ratio_frame["label"].map(
            {
                "positive_ratio": "긍정",
                "neutral_ratio": "중립",
                "negative_ratio": "부정",
            }
        )
        ratio_chart = (
            alt.Chart(ratio_frame)
            .mark_bar()
            .encode(
                x=alt.X("episode_number:O", title="회차", sort=None),
                y=alt.Y(
                    "ratio:Q",
                    title="비율(%)",
                    stack="normalize",
                    axis=alt.Axis(format="%"),
                ),
                color=alt.Color(
                    "감정:N",
                    sort=["긍정", "중립", "부정"],
                ),
                order=alt.Order("감정:N", sort="ascending"),
                tooltip=[
                    alt.Tooltip("episode_number:O", title="회차"),
                    alt.Tooltip("episode_title:N", title="제목"),
                    alt.Tooltip("감정:N", title="감정"),
                    alt.Tooltip("ratio:Q", title="비율(%)", format=".1f"),
                    alt.Tooltip(
                        "analyzed_comment_count:Q",
                        title="분석 댓글",
                        format=",",
                    ),
                ],
            )
            .properties(height=360)
        )
        st.altair_chart(ratio_chart, width="stretch")

    with score_tab:
        score_chart = (
            alt.Chart(chart_frame)
            .mark_line(point=True)
            .encode(
                x=alt.X("episode_number:Q", title="회차", scale=alt.Scale(zero=False)),
                y=alt.Y(
                    "reaction_score:Q",
                    title="독자 반응 점수",
                    scale=alt.Scale(domain=[-100, 100]),
                ),
                tooltip=[
                    alt.Tooltip("episode_number:Q", title="회차"),
                    alt.Tooltip("episode_title:N", title="제목"),
                    alt.Tooltip("reaction_score:Q", title="반응 점수", format="+.1f"),
                    alt.Tooltip("positive_ratio:Q", title="긍정(%)", format=".1f"),
                    alt.Tooltip("negative_ratio:Q", title="부정(%)", format=".1f"),
                    alt.Tooltip(
                        "analyzed_comment_count:Q",
                        title="분석 댓글",
                        format=",",
                    ),
                ],
            )
            .properties(height=360)
        )
        baseline = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(strokeDash=[5, 5]).encode(y="y:Q")
        st.altair_chart(score_chart + baseline, width="stretch")

    with count_tab:
        count_chart = (
            alt.Chart(chart_frame)
            .mark_bar()
            .encode(
                x=alt.X("episode_number:O", title="회차", sort=None),
                y=alt.Y("analyzed_comment_count:Q", title="분석 댓글 수"),
                tooltip=[
                    alt.Tooltip("episode_number:O", title="회차"),
                    alt.Tooltip("episode_title:N", title="제목"),
                    alt.Tooltip(
                        "stored_comment_count:Q",
                        title="수집 댓글",
                        format=",",
                    ),
                    alt.Tooltip(
                        "analyzed_comment_count:Q",
                        title="분석 댓글",
                        format=",",
                    ),
                ],
            )
            .properties(height=360)
        )
        st.altair_chart(count_chart, width="stretch")


def filter_and_sort_episode_frame(frame: pd.DataFrame) -> pd.DataFrame:
    filter_col1, filter_col2, filter_col3 = st.columns([1.2, 2.2, 1.6])

    with filter_col1:
        access_filter = st.segmented_control(
            "회차 구분",
            ["전체", "무료 회차", "유료 회차"],
            default="전체",
            key="episode_access_filter",
            label_visibility="collapsed",
        )

    with filter_col2:
        keyword = st.text_input(
            "회차 검색",
            placeholder="회차 번호 또는 제목 검색",
            key="episode_search_keyword",
            label_visibility="collapsed",
        )

    with filter_col3:
        sort_option = st.selectbox(
            "회차 정렬",
            [
                "회차 오름차순",
                "회차 내림차순",
                "부정률 높은순",
                "댓글 많은순",
                "반응 점수 낮은순",
            ],
            key="episode_sort_option",
            label_visibility="collapsed",
        )

    filtered = frame.copy()
    if access_filter in {"무료 회차", "유료 회차"}:
        filtered = filtered[filtered["access_label"] == access_filter]

    keyword = keyword.strip()
    if keyword:
        mask = (
            filtered["episode_title"].fillna("").astype(str).str.contains(
                keyword,
                case=False,
                regex=False,
            )
            | filtered["episode_number"].astype(str).str.contains(
                keyword,
                case=False,
                regex=False,
            )
        )
        filtered = filtered[mask]

    sort_map = {
        "회차 오름차순": ("episode_number", True),
        "회차 내림차순": ("episode_number", False),
        "부정률 높은순": ("negative_ratio", False),
        "댓글 많은순": ("analyzed_comment_count", False),
        "반응 점수 낮은순": ("reaction_score", True),
    }
    column, ascending = sort_map[sort_option]
    return filtered.sort_values(column, ascending=ascending, kind="stable")


def render_episode_cards(
    frame: pd.DataFrame,
    novel_id: int,
    sentiment_service: CommentSentimentService,
) -> None:
    if frame.empty:
        st.info("현재 필터 조건에 맞는 회차가 없습니다.")
        return

    page_size = 10
    total_pages = max(1, ceil(len(frame) / page_size))
    page_key = f"episode_page_{novel_id}"

    current_page = safe_int(st.session_state.get(page_key, 1))
    current_page = min(max(current_page, 1), total_pages)
    st.session_state[page_key] = current_page

    nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
    with nav_col1:
        if st.button(
            "◀ 이전",
            disabled=current_page <= 1,
            key=f"episode_prev_{novel_id}",
            width="stretch",
        ):
            st.session_state[page_key] = current_page - 1
            st.session_state.pop("selected_episode_id", None)
            st.rerun()

    with nav_col2:
        st.markdown(
            f"<div style='text-align:center;padding-top:0.5rem;'>"
            f"{current_page} / {total_pages} 페이지 · "
            f"페이지당 10화 · 총 {len(frame):,}화"
            "</div>",
            unsafe_allow_html=True,
        )

    with nav_col3:
        if st.button(
            "다음 ▶",
            disabled=current_page >= total_pages,
            key=f"episode_next_{novel_id}",
            width="stretch",
        ):
            st.session_state[page_key] = current_page + 1
            st.session_state.pop("selected_episode_id", None)
            st.rerun()

    start_index = (current_page - 1) * page_size
    page_frame = frame.iloc[start_index : start_index + page_size]
    selected_episode_id = st.session_state.get("selected_episode_id")

    for row in page_frame.to_dict("records"):
        episode_id = safe_int(row.get("episode_id"))
        episode_number = safe_int(row.get("episode_number"))
        title = str(row.get("episode_title") or "제목 없음")
        analyzed = safe_int(row.get("analyzed_comment_count"))
        stored = safe_int(row.get("stored_comment_count"))
        positive = safe_float(row.get("positive_ratio"))
        neutral = safe_float(row.get("neutral_ratio"))
        negative = safe_float(row.get("negative_ratio"))
        score = safe_float(row.get("reaction_score"))
        is_open = (
            selected_episode_id is not None
            and int(selected_episode_id) == episode_id
        )

        with st.container(border=True):
            info_col, action_col = st.columns(
                [8.2, 1.8],
                vertical_alignment="center",
            )

            with info_col:
                st.markdown(f"### {episode_number}화 · {title}")
                st.caption(
                    f"{format_datetime(row.get('published_at')).split(' ')[0]} · "
                    f"{row.get('access_label')} · "
                    f"조회 {format_number(row.get('view_count'))} · "
                    f"원본 댓글 {format_number(row.get('source_comment_count'))} · "
                    f"수집 {stored:,} · 분석 {analyzed:,}"
                )

                if analyzed > 0:
                    st.markdown(
                        f"**🟢 긍정 {positive:.1f}%** · "
                        f"**⚪ 중립 {neutral:.1f}%** · "
                        f"**🔴 부정 {negative:.1f}%** · "
                        f"반응 점수 **{score:+.1f} "
                        f"({reaction_description(score)})**"
                    )
                else:
                    st.markdown("감정분석된 댓글이 없습니다.")

                if analyzed < 20:
                    st.caption(f"⚠ {reliability_help(analyzed)}")

            with action_col:
                button_label = "▲ 분석 닫기" if is_open else "📊 반응 분석"
                if st.button(
                    button_label,
                    key=f"episode_reaction_{episode_id}",
                    type="primary" if is_open else "secondary",
                    width="stretch",
                ):
                    if is_open:
                        st.session_state.pop("selected_episode_id", None)
                    else:
                        st.session_state.selected_episode_id = episode_id
                    st.rerun()

            if is_open:
                render_episode_detail(
                    novel_id=novel_id,
                    summary=row,
                    sentiment_service=sentiment_service,
                )


def episode_distribution_frame(summary: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "감정": ["긍정", "중립", "부정"],
            "개수": [
                safe_int(summary.get("positive_count")),
                safe_int(summary.get("neutral_count")),
                safe_int(summary.get("negative_count")),
            ],
            "비율": [
                safe_float(summary.get("positive_ratio")),
                safe_float(summary.get("neutral_ratio")),
                safe_float(summary.get("negative_ratio")),
            ],
        }
    )



def prepare_comments_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows)
    frame["감정"] = frame["predicted_label"].map(LABEL_KO).fillna("⚫ 미분석")
    frame["신뢰도"] = pd.to_numeric(frame["confidence"], errors="coerce") * 100
    frame["좋아요 수"] = pd.to_numeric(frame["like_count"], errors="coerce").fillna(0).astype(int)
    frame["싫어요 수"] = pd.to_numeric(frame["dislike_count"], errors="coerce").fillna(0).astype(int)
    frame["작성 시간"] = pd.to_datetime(frame["created_at"], errors="coerce").dt.strftime(
        "%Y-%m-%d %H:%M"
    )
    frame["작성자"] = frame["commenter_nickname"].fillna("")
    frame["댓글 내용"] = frame["comment_text"].fillna("")
    frame["구분"] = frame.apply(
        lambda row: "작가" if bool(row.get("is_novel_author")) else (
            "답글" if safe_int(row.get("reply_level")) > 0 else "독자"
        ),
        axis=1,
    )
    return frame


def render_comment_table(
    *,
    episode_id: int,
    sentiment_service: CommentSentimentService,
) -> None:
    control_col1, control_col2, control_col3, control_col4 = st.columns(
        [1.5, 1.5, 1, 1]
    )

    with control_col1:
        label_ko = st.segmented_control(
            "감정 필터",
            ["전체", "긍정", "중립", "부정", "미분석"],
            default="전체",
            key=f"comment_label_{episode_id}",
            label_visibility="collapsed",
        )

    with control_col2:
        sort_ko = st.selectbox(
            "댓글 정렬",
            ["최신순", "과거순", "좋아요순", "싫어요순", "신뢰도순", "부정 우선"],
            key=f"comment_sort_{episode_id}",
            label_visibility="collapsed",
        )

    with control_col3:
        analyzed_only = st.toggle(
            "분석 댓글만",
            value=False,
            key=f"comment_analyzed_only_{episode_id}",
        )

    with control_col4:
        limit = st.selectbox(
            "표시 개수",
            [100, 500, 1000, 2000],
            index=1,
            key=f"comment_limit_{episode_id}",
            label_visibility="collapsed",
        )

    label_map = {
        "전체": "all",
        "긍정": "positive",
        "중립": "neutral",
        "부정": "negative",
        "미분석": "unanalyzed",
    }
    sort_map = {
        "최신순": "latest",
        "과거순": "oldest",
        "좋아요순": "likes",
        "싫어요순": "dislikes",
        "신뢰도순": "confidence",
        "부정 우선": "negative_first",
    }

    rows = sentiment_service.get_episode_comments(
        episode_id,
        label=label_map[label_ko],
        sort_by=sort_map[sort_ko],
        analyzed_only=analyzed_only,
        limit=limit,
    )
    frame = prepare_comments_frame(rows)
    if frame.empty:
        st.info("현재 조건에 표시할 댓글이 없습니다.")
        return

    display_columns = [
        "감정",
        "댓글 내용",
        "신뢰도",
        "좋아요 수",
        "싫어요 수",
        "작성자",
        "구분",
        "작성 시간",
    ]
    st.caption(f"현재 조건에서 {len(frame):,}개 표시")
    st.dataframe(
        frame[display_columns],
        width="stretch",
        height=520,
        hide_index=True,
        column_config={
            "댓글 내용": st.column_config.TextColumn(width="large"),
            "신뢰도": st.column_config.NumberColumn(format="%.1f%%"),
            "좋아요 수": st.column_config.NumberColumn(format="%d"),
            "싫어요 수": st.column_config.NumberColumn(format="%d"),
        },
    )


def render_representative_group(title: str, rows: list[dict[str, Any]]) -> None:
    st.markdown(f"#### {title}")
    if not rows:
        st.info("표시할 댓글이 없습니다.")
        return

    for row in rows:
        label = LABEL_KO.get(row.get("predicted_label"), "⚫ 미분석")
        with st.container(border=True):
            st.markdown(str(row.get("comment_text") or ""))
            st.caption(
                f"{label} · 신뢰도 {safe_float(row.get('confidence')) * 100:.1f}% · "
                f"좋아요 {safe_int(row.get('like_count')):,} · "
                f"싫어요 {safe_int(row.get('dislike_count')):,} · "
                f"{format_datetime(row.get('created_at'))}"
            )


def render_episode_detail(
    *,
    novel_id: int,
    summary: dict[str, Any],
    sentiment_service: CommentSentimentService,
) -> None:
    episode_id = safe_int(summary.get("episode_id"))
    analyzed = safe_int(summary.get("analyzed_comment_count"))
    stored = safe_int(summary.get("stored_comment_count"))
    confidence = safe_float(summary.get("average_confidence")) * 100
    analysis_rate = (analyzed / stored * 100.0) if stored else 0.0

    st.markdown("---")
    st.caption(
        f"분석률 {analysis_rate:.1f}% "
        f"({analyzed:,}/{stored:,}) · "
        f"평균 신뢰도 {confidence:.1f}%"
    )

    distribution_tab, comments_tab, representative_tab, info_tab = st.tabs(
        ["📊 통계 그래프", "💬 댓글 목록", "⭐ 대표 댓글", "ℹ️ 분석 정보"]
    )

    with distribution_tab:
        dist_frame = episode_distribution_frame(summary)
        chart_col1, chart_col2 = st.columns([1.2, 1.8])

        with chart_col1:
            distribution_chart = (
                alt.Chart(dist_frame)
                .mark_arc(innerRadius=60)
                .encode(
                    theta=alt.Theta("개수:Q"),
                    color=alt.Color("감정:N", sort=["긍정", "중립", "부정"]),
                    tooltip=[
                        alt.Tooltip("감정:N"),
                        alt.Tooltip("개수:Q", format=","),
                        alt.Tooltip("비율:Q", format=".1f"),
                    ],
                )
                .properties(title="감정 분포", height=320)
            )
            st.altair_chart(distribution_chart, width="stretch")

        with chart_col2:
            analyzed_rows = sentiment_service.get_episode_comments(
                episode_id,
                analyzed_only=True,
                sort_by="latest",
                limit=5000,
            )
            analyzed_frame = pd.DataFrame(analyzed_rows)
            if not analyzed_frame.empty:
                analyzed_frame["confidence"] = pd.to_numeric(
                    analyzed_frame["confidence"],
                    errors="coerce",
                )
                confidence_chart = (
                    alt.Chart(analyzed_frame.dropna(subset=["confidence"]))
                    .mark_bar()
                    .encode(
                        x=alt.X(
                            "confidence:Q",
                            title="신뢰도",
                            bin=alt.Bin(maxbins=12),
                        ),
                        y=alt.Y("count():Q", title="댓글 수"),
                        tooltip=[alt.Tooltip("count():Q", title="댓글 수")],
                    )
                    .properties(title="모델 신뢰도 분포", height=320)
                )
                st.altair_chart(confidence_chart, width="stretch")
            else:
                st.info("신뢰도 분포를 표시할 분석 댓글이 없습니다.")

        timeline_rows = sentiment_service.get_episode_comments(
            episode_id,
            sort_by="oldest",
            limit=5000,
        )
        timeline_frame = pd.DataFrame(timeline_rows)
        if not timeline_frame.empty:
            timeline_frame["date"] = pd.to_datetime(
                timeline_frame["created_at"],
                errors="coerce",
            ).dt.date
            timeline_frame["감정"] = timeline_frame["predicted_label"].map(
                LABEL_SHORT_KO
            ).fillna("미분석")
            daily = (
                timeline_frame.dropna(subset=["date"])
                .groupby(["date", "감정"], as_index=False)
                .size()
                .rename(columns={"size": "댓글 수"})
            )
            if not daily.empty:
                timeline_chart = (
                    alt.Chart(daily)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("date:T", title="작성일"),
                        y=alt.Y("댓글 수:Q", title="댓글 수"),
                        color=alt.Color("감정:N"),
                        tooltip=["date:T", "감정:N", "댓글 수:Q"],
                    )
                    .properties(title="댓글 작성 추이", height=300)
                )
                st.altair_chart(timeline_chart, width="stretch")

    with comments_tab:
        render_comment_table(
            episode_id=episode_id,
            sentiment_service=sentiment_service,
        )

    with representative_tab:
        representatives = sentiment_service.get_representative_comments(
            episode_id,
            limit=5,
        )
        rep_col1, rep_col2 = st.columns(2)
        with rep_col1:
            render_representative_group(
                "👍 공감이 많은 긍정 댓글",
                representatives["positive"],
            )
            render_representative_group(
                "⚖️ 모델 판단이 애매한 댓글",
                representatives["ambiguous"],
            )
        with rep_col2:
            render_representative_group(
                "👎 공감이 많은 부정 댓글",
                representatives["negative"],
            )
            render_representative_group(
                "🔥 반응이 많은 논쟁 댓글",
                representatives["controversy"],
            )

    with info_tab:
        st.markdown(
            """
            **감정 통계에 포함되는 댓글**

            - 무료 회차(`access_type = FREE`)
            - `content_type = TEXT`
            - 최상위 댓글(`reply_level = 0`)
            - 작가 댓글 제외
            - 빈 댓글 제외

            댓글의 좋아요·싫어요는 감정 라벨을 결정하지 않으며, 대표 댓글의
            공감도와 정렬에만 사용합니다. `독자 반응 점수`는 **긍정 비율 - 부정 비율**입니다.
            """
        )
        st.write(f"**모델 버전:** {summary.get('model_version') or 'munpia-kcelectra-v2'}")
        st.write(f"**마지막 분석:** {format_datetime(summary.get('last_analyzed_at'))}")
        st.write(f"**표본 신뢰도:** {summary.get('reliability', '-')} ({analyzed:,}개)")


def render_reaction_section(
    *,
    novel_id: int,
    sentiment_service: CommentSentimentService,
) -> None:
    st.markdown("---")
    st.subheader("📚 회차별 독자 반응")
    st.caption(
        "DB에 저장된 기존 댓글과 V5 감정분석 결과를 조회합니다. "
        "회차의 반응 분석 버튼을 누르면 해당 카드 바로 아래에서 "
        "통계 그래프, 댓글 목록, 대표 댓글을 확인할 수 있습니다."
    )

    try:
        with st.spinner("회차별 댓글 반응 데이터를 불러오는 중입니다..."):
            overview = sentiment_service.get_novel_overview(novel_id)
            episode_rows = sentiment_service.get_episode_summaries(novel_id)
    except Exception as exc:
        st.error(f"댓글 반응 데이터를 불러오지 못했습니다: {exc}")
        st.info(
            "V5 마이그레이션으로 comment_statistics 테이블이 생성됐는지, "
            "Repository 또는 DB 환경변수 연결이 정상인지 확인하세요."
        )
        return

    render_novel_reaction_overview(overview)

    episode_frame = build_episode_frame(episode_rows)
    if episode_frame.empty:
        st.info("해당 작품의 회차 데이터가 없습니다.")
        return

    st.markdown("#### 📈 작품 전체 회차 반응 추이")
    render_episode_trend_charts(episode_frame)

    st.markdown("#### 📖 회차 선택")
    filtered_frame = filter_and_sort_episode_frame(episode_frame)
    render_episode_cards(
        filtered_frame,
        novel_id,
        sentiment_service,
    )


# -----------------------------------------------------------------------------
# 페이지 엔트리
# -----------------------------------------------------------------------------
def render_page() -> None:
    st.set_page_config(page_title="소설 기본정보 조회", layout="wide")
    st.title("📖 소설 상세정보 조회 시스템")

    try:
        repository = Repository()
        service = NovelService(repository=repository)
        prediction_service = NovelPredictionService(repository=repository)
        sentiment_service = CommentSentimentService(repository=repository)
    except Exception as exc:
        st.error(f"서비스 초기화에 실패했습니다: {exc}")
        return

    query_url = st.query_params.get("url", "")
    if (
        "last_query_url" not in st.session_state
        or st.session_state.last_query_url != query_url
    ):
        st.session_state.last_query_url = query_url
        st.session_state.input_url = query_url
        st.session_state.auto_searched = False

    user_input = st.text_input(
        "🔍 조회할 소설 ID 또는 작품 URL을 입력하세요:",
        key="input_url",
    )
    is_clicked = st.button("조회", type="primary")

    if is_clicked:
        st.session_state.has_searched = True
        st.session_state.search_target = user_input
        st.session_state.pop("selected_episode_id", None)
    elif query_url and not st.session_state.get("auto_searched", False):
        st.session_state.has_searched = True
        st.session_state.search_target = query_url
        st.session_state.auto_searched = True

    if not st.session_state.get("has_searched", False):
        return

    target_input = st.session_state.get("search_target", user_input)
    if not str(target_input).strip():
        st.warning("소설 ID 또는 작품 URL을 입력해 주세요.")
        st.session_state.has_searched = False
        return

    if "munpia.com/novel/detail/" in str(target_input):
        match = re.search(r"/detail/(\d+)", str(target_input))
        if match:
            target_input = match.group(1)

    try:
        with st.spinner("기본 작품 정보를 불러오는 중입니다..."):
            novel_id = service.parse_novel_id(str(target_input))
            novel = service.get_novel(novel_id)
            if not novel:
                st.error(f"❌ 해당 소설을 찾을 수 없습니다. (ID: {novel_id})")
                return

            render_novel_header(novel, service, novel_id)
            render_novel_statistics(service.get_novel_statistics(novel_id))

        render_prediction_section(
            novel=novel,
            novel_id=novel_id,
            service=service,
            prediction_service=prediction_service,
        )
        render_reaction_section(
            novel_id=novel_id,
            sentiment_service=sentiment_service,
        )

    except NovelServiceError as exc:
        st.error(f"⚠️ {exc}")
    except CommentSentimentServiceError as exc:
        st.error(f"⚠️ {exc}")
    except Exception as exc:
        st.error(f"시스템 오류 발생: {exc}")


if __name__ == "__main__":
    render_page()
