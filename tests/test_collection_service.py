from __future__ import annotations

from service.collection_service import CollectionService


class StubRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[int, dict]] = []

    def novel_exists(self, novel_id: int) -> bool:
        return bool(self.saved)

    def save_result(self, novel_id: int, result: dict) -> dict[str, int]:
        self.saved.append((novel_id, result))
        return {"novel": 1, "episode": len(result.get("episode", []))}


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
