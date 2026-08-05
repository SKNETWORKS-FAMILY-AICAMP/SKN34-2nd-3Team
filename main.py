import csv
import threading
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from huggingface_hub import snapshot_download

from clawler.munpia_crawler import ALL_HEADERS


DATA_DIR = Path(__file__).resolve().parent / "db" / "data"
_DATASET_LOCK = threading.Lock()


def run() -> None:
    download_dataset()
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


def _invalid_dataset_files(data_dir: Path) -> list[str]:
    invalid_files: list[str] = []
    for table, expected_header in ALL_HEADERS.items():
        filename = f"{table}.csv"
        path = data_dir / filename
        try:
            if not path.is_file() or path.stat().st_size == 0:
                invalid_files.append(filename)
                continue
            with path.open("r", encoding="utf-8-sig", newline="") as file:
                header = next(csv.reader(file), None)
            if header != expected_header:
                invalid_files.append(filename)
        except (OSError, UnicodeError, csv.Error):
            invalid_files.append(filename)
    return invalid_files


def download_dataset(data_dir: str | Path | None = None) -> str:
    resolved_data_dir = Path(DATA_DIR if data_dir is None else data_dir).resolve()
    with _DATASET_LOCK:
        invalid_files = _invalid_dataset_files(resolved_data_dir)
        if not invalid_files:
            return str(resolved_data_dir)

        resolved_data_dir.mkdir(parents=True, exist_ok=True)
        load_dotenv()
        download_error: Exception | None = None
        try:
            snapshot_download(
                repo_id="SKN34/SKN34-2nd-3Team",
                repo_type="dataset",
                local_dir=str(resolved_data_dir),
                allow_patterns=invalid_files,
                force_download=True,
            )
        except Exception as error:
            download_error = error

        remaining_invalid_files = _invalid_dataset_files(resolved_data_dir)
        if remaining_invalid_files:
            filenames = ", ".join(remaining_invalid_files)
            raise RuntimeError(
                f"Dataset recovery failed; remaining invalid CSV files: {filenames}"
            ) from download_error

        return str(resolved_data_dir)


if __name__ == "__main__":
    run()
