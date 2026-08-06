from __future__ import annotations

from service.collection_service import CollectionService


class StubRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[int, dict]] = []
        self.calls: list[tuple[str, tuple, dict]] = []

    def novel_exists(self, novel_id: int) -> bool:
        return bool(self.saved)

    def save_result(self, novel_id: int, result: dict) -> dict[str, int]:
        self.saved.append((novel_id, result))
        return {"novel": 1, "episode": len(result.get("episode", []))}

    def list_genre_options(self):
        self.calls.append(("list_genre_options", (), {}))
        return [(1, "판타지")]

    def find_page(self, novel_id, page_size):
        self.calls.append(("find_page", (novel_id, page_size), {}))
        return 3

    def list_novels(self, page, page_size, **filters):
        self.calls.append(("list_novels", (page, page_size), filters))
        return ([{"novel_id": 123}], 1)


class FakeCrawler:
    def __init__(self):
        self.active_states = {}

    async def process_single_work(self, novel_id, session=None):
        return {
            "type": "SUCCESS",
            "novel_author": [], "novel_group": [], "novel_genre": [],
            "tag": [], "novel_tag": [],
            "novel": {"novel_id": novel_id, "title": "테스트"},
            "novel_statistics": {"novel_id": novel_id},
            "episode": [], "comment": [],
        }


def test_collect_saves_directly_to_repository():
    repository = StubRepository()
    service = CollectionService(repository, crawler_factory=FakeCrawler)

    first = list(service.collect_stream("123"))[-1]
    second = list(service.collect_stream("123"))[-1]

    assert first.result.change_type == "INSERT"
    assert second.result.change_type == "UPDATE"
    assert len(repository.saved) == 2
    assert first.message == "DB 저장까지 완료했습니다."


def test_progress_message():
    message = CollectionService._progress_message({
        "phase": "EPISODE_PARALLEL", "chapter_done": 12,
        "chapter_total": 100, "chapter_in_flight": 20, "chapter_failed": 2,
    })
    assert "완료 12/100" in message
    assert "처리 중 20개" in message
    assert "실패 2개" in message


def test_collection_page_queries_delegate_to_repository_with_unchanged_arguments():
    repository = StubRepository()
    service = CollectionService(repository)
    filters = {
        "genre_id": 7,
        "serial_status": "paused",
        "min_view_count": 1000,
        "min_preference_count": 100,
        "min_chapter_count": 10,
    }

    assert service.list_genre_options() == [(1, "판타지")]
    assert service.find_page(123, 20) == 3
    assert service.list_novels(2, 20, **filters) == ([{"novel_id": 123}], 1)
    assert repository.calls == [
        ("list_genre_options", (), {}),
        ("find_page", (123, 20), {}),
        ("list_novels", (2, 20), filters),
    ]
