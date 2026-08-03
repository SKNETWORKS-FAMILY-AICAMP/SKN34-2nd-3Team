from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st

from service import NovelService, NovelServiceError


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "db" / "data"


service = NovelService(
    works_csv_path=DATA_DIR / "works.csv",
    authors_csv_path=DATA_DIR / "authors.csv",
    episodes_csv_path=DATA_DIR / "episodes.csv",
    comments_csv_path=DATA_DIR / "comments.csv",
)


st.set_page_config(
    page_title="문피아 작품 데이터 조회",
    layout="wide",
)


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
        background-color: #1E1E2E;
        padding: 1.2rem 2rem;
        border-radius: 0.5rem;
        margin-top: -1rem;
        margin-bottom: 2rem;
        border-bottom: 2px solid #3b82f6;
    ">
        <h2 style="margin: 0; color: white;">
            📚 문피아 작품 & 작가 데이터 조회
        </h2>
    </div>
    """,
    unsafe_allow_html=True,
)


if "novel" not in st.session_state:
    st.session_state.novel = None

if "statistics" not in st.session_state:
    st.session_state.statistics = None

if "author" not in st.session_state:
    st.session_state.author = None

if "episodes" not in st.session_state:
    st.session_state.episodes = []

if "comments" not in st.session_state:
    st.session_state.comments = []

if "current_view" not in st.session_state:
    st.session_state.current_view = "work"


raw_input = st.text_input(
    "작품 주소 또는 작품 ID 입력",
    placeholder=(
        "예: 12345 또는 "
        "https://novel.munpia.com/12345"
    ),
)


if st.button(
    "데이터 조회",
    type="primary",
):
    try:
        novel_id = service.parse_novel_id(raw_input)

        with st.status(
            f"작품 ID {novel_id} 조회 중...",
            expanded=True,
        ) as status_box:
            novel = service.get_novel(novel_id)

            if novel is None:
                st.session_state.novel = None
                st.session_state.statistics = None
                st.session_state.author = None
                st.session_state.episodes = []
                st.session_state.comments = []

                status_box.update(
                    label="❌ 작품을 찾을 수 없습니다.",
                    state="error",
                    expanded=False,
                )

                st.error(
                    "해당 작품을 찾을 수 없습니다."
                )

            else:
                statistics = (
                    service.get_novel_statistics(
                        novel_id
                    )
                )

                author = service.get_author(
                    novel_id
                )

                episodes = service.get_episodes(
                    novel_id
                )

                comments = service.get_comments(
                    novel_id
                )

                st.session_state.novel = novel
                st.session_state.statistics = statistics
                st.session_state.author = author
                st.session_state.episodes = episodes
                st.session_state.comments = comments
                st.session_state.current_view = "work"

                status_box.update(
                    label="✅ 데이터 조회 완료!",
                    state="complete",
                    expanded=False,
                )

                st.success(
                    f"'{novel.title}' 조회를 완료했습니다."
                )

    except NovelServiceError as exc:
        st.error(str(exc))

    except Exception as exc:
        st.error(
            f"예상하지 못한 오류가 발생했습니다: {exc}"
        )


if st.session_state.novel is not None:
    novel = st.session_state.novel
    statistics = st.session_state.statistics
    author = st.session_state.author
    episodes = st.session_state.episodes
    comments = st.session_state.comments

    st.markdown("---")

    work_button_column, author_button_column = (
        st.columns(2)
    )

    with work_button_column:
        if st.button(
            "📖 작품 정보",
            width="stretch",
        ):
            st.session_state.current_view = "work"

    with author_button_column:
        if st.button(
            "✍️ 작가 정보",
            width="stretch",
        ):
            st.session_state.current_view = "author"

    if st.session_state.current_view == "work":
        st.subheader("📌 작품 상세 정보")

        st.markdown(f"### {novel.title}")

        if author is not None:
            st.markdown(
                f"**✍️ 작가:** {author.author_name}"
            )
        elif novel.author_id is not None:
            st.markdown(
                f"**✍️ 작가 ID:** {novel.author_id}"
            )
        else:
            st.markdown(
                "**✍️ 작가:** 정보 없음"
            )

        metric1, metric2, metric3 = st.columns(3)

        view_count = (
            statistics.view_count
            if (
                statistics is not None
                and statistics.view_count is not None
            )
            else None
        )

        preference_count = (
            statistics.preference_count
            if (
                statistics is not None
                and statistics.preference_count is not None
            )
            else None
        )

        chapter_count = (
            statistics.chapter_count
            if (
                statistics is not None
                and statistics.chapter_count is not None
            )
            else len(episodes)
        )

        metric1.metric(
            "👁️ 조회수",
            (
                f"{view_count:,}"
                if view_count is not None
                else "정보 없음"
            ),
        )

        metric2.metric(
            "❤️ 선호작수",
            (
                f"{preference_count:,}"
                if preference_count is not None
                else "정보 없음"
            ),
        )

        metric3.metric(
            "📝 총 회차",
            f"{chapter_count:,}",
        )

        st.markdown("**📖 작품 소개**")

        st.info(
            novel.introduction
            if novel.introduction
            else "소개글이 없습니다."
        )

        st.markdown("---")

        st.subheader(
            f"📑 회차 목록 "
            f"(총 {len(episodes):,}개)"
        )

        if episodes:
            st.dataframe(
                pd.DataFrame(
                    [
                        asdict(episode)
                        for episode in episodes
                    ]
                ),
                width="stretch",
                hide_index=True,
            )
        else:
            st.info(
                "조회된 회차 정보가 없습니다."
            )

        st.subheader(
            f"💬 댓글 목록 "
            f"(총 {len(comments):,}개)"
        )

        if comments:
            st.dataframe(
                pd.DataFrame(
                    [
                        asdict(comment)
                        for comment in comments
                    ]
                ),
                width="stretch",
                hide_index=True,
            )
        else:
            st.info(
                "조회된 댓글 정보가 없습니다."
            )

    elif st.session_state.current_view == "author":
        st.subheader("📌 작가 상세 정보")

        if author is None:
            st.warning(
                "해당 작품에 연결된 작가 정보가 없습니다."
            )

        else:
            st.markdown(
                f"### {author.author_name}"
            )

            author_metric1, author_metric2 = (
                st.columns(2)
            )

            author_metric1.metric(
                "작가 ID",
                f"{author.author_id:,}",
            )

            author_metric2.metric(
                "삽화가 여부",
                (
                    "예"
                    if author.is_illustrator
                    else "아니오"
                ),
            )

            if author.author_url:
                st.markdown(
                    f"**작가 서재:** "
                    f"[{author.author_url}]"
                    f"({author.author_url})"
                )

            st.dataframe(
                pd.DataFrame(
                    [asdict(author)]
                ),
                width="stretch",
                hide_index=True,
            )