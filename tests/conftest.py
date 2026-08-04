from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest

from clawler.munpia_crawler import ALL_HEADERS


def write_table(data_dir: Path, table: str, rows: list[dict[str, Any]] | None = None) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / f"{table}.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=ALL_HEADERS[table], extrasaction="ignore")
        writer.writeheader()
        for row in rows or []:
            writer.writerow({column: row.get(column, "") for column in ALL_HEADERS[table]})


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    path = tmp_path / "data"
    for table in ALL_HEADERS:
        write_table(path, table)
    return path
