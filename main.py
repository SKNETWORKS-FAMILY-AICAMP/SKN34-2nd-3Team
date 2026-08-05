import streamlit as st


def run() -> None:
    crawler_page = st.Page(
        "pages/munpia_apppage.py",
        title="정보 수집",
        default=True,
    )
    novel_detail = st.Page(
        "pages/novel_basic_info.py",
        title="소설분석 대쉬보드",
    )

    page = st.navigation([crawler_page, novel_detail])
    page.run()


if __name__ == "__main__":
    run()
