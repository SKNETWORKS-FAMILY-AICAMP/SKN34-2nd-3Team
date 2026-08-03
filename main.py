import streamlit as st
from dotenv import load_dotenv
from huggingface_hub import snapshot_download


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
    download_dataset()
    page.run()


@st.cache_resource(show_spinner="데이터셋 확인 중...")
def download_dataset() -> str:
    load_dotenv()
    return snapshot_download(
        repo_id="SKN34/SKN34-2nd-3Team",
        repo_type="dataset",
        local_dir="db/data",
    )


if __name__ == "__main__":
    run()