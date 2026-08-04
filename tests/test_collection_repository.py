from __future__ import annotations

import csv

from repository.collection_repository import CsvCollectionRepository
from tests.conftest import write_table


def read_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def result(novel_id: int, title: str):
    return {
        "novel_author": [{"author_id": 1, "author_name": "작가"}],
        "novel_group": [], "novel_genre": [], "tag": [], "novel_tag": [],
        "novel": {"novel_id": novel_id, "title": title, "author_id": 1},
        "novel_statistics": {"novel_id": novel_id, "view_count": 10},
        "episode": [{"episode_id": novel_id * 10, "novel_id": novel_id, "episode_number": 1}],
        "comment": [],
    }


def test_insert_and_update(data_dir):
    repo = CsvCollectionRepository(data_dir)
    assert repo.novel_exists(1) is False
    repo.save_result(1, result(1, "첫 제목"))
    assert repo.novel_exists(1) is True
    repo.save_result(1, result(1, "새 제목"))
    rows = read_rows(data_dir / "novel.csv")
    assert len(rows) == 1
    assert rows[0]["title"] == "새 제목"


def test_update_preserves_other_novel(data_dir):
    repo = CsvCollectionRepository(data_dir)
    repo.save_result(1, result(1, "A"))
    repo.save_result(2, result(2, "B"))
    repo.save_result(1, result(1, "A2"))
    rows = read_rows(data_dir / "novel.csv")
    assert {row["novel_id"]: row["title"] for row in rows} == {"1": "A2", "2": "B"}


def test_ai_evaluation_is_untouched(data_dir):
    write_table(data_dir, "novel_ai_evaluation", [{"evaluation_id": 7, "novel_id": 1}])
    before = (data_dir / "novel_ai_evaluation.csv").read_bytes()
    CsvCollectionRepository(data_dir).save_result(1, result(1, "A"))
    assert (data_dir / "novel_ai_evaluation.csv").read_bytes() == before


def test_list_and_find_page(data_dir):
    repo = CsvCollectionRepository(data_dir)
    for novel_id in range(1, 26):
        repo.save_result(novel_id, result(novel_id, f"작품 {novel_id}"))
    rows, total = repo.list_novels(2, 20)
    assert total == 25
    assert [row["novel_id"] for row in rows] == [str(i) for i in range(21, 26)]
    assert repo.find_page(21, 20) == 2
