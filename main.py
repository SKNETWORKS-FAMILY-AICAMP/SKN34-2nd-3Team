import streamlit as st


def run() -> None:
    recommendation_page = st.Page(
        "pages/recommendation_dashboard.py",
        title="무료/유료 전환 추천",
        icon=":material/recommend:",
        default=True,
    )
    crawler_page = st.Page(
        "pages/munpia_apppage.py",
        title="정보 수집",
    )
    novel_detail = st.Page(
        "pages/novel_basic_info.py",
        title="소설 분석 대시보드",
    )
    author_page = st.Page(
        "pages/author_novels.py",
        title="작가 작품 조회",
        icon=":material/person_search:",
    )

    page = st.navigation(
        [recommendation_page, crawler_page, novel_detail, author_page]
    )
    page.run()


if __name__ == "__main__":
    run()
