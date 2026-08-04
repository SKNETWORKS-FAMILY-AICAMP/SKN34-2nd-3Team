from __future__ import annotations

from repository.collection_repository import CsvCollectionRepository
from service.collection_service import CollectionService


class FakeCrawler:
    def __init__(self):
        self.active_states = {}
        self.stop_event = None

    async def process_single_work(self, novel_id, session=None):
        return {
            "type": "SUCCESS",
            "novel_author": [], "novel_group": [], "novel_genre": [], "tag": [], "novel_tag": [],
            "novel": {"novel_id": novel_id, "title": "테스트"},
            "novel_statistics": {"novel_id": novel_id},
            "episode": [], "comment": [],
        }


def test_collect_insert_then_update(data_dir):
    repo = CsvCollectionRepository(data_dir)
    service = CollectionService(repo, crawler_factory=FakeCrawler)
    first = service.collect_stream("123")
    events = list(first)
    assert events[-1].result.change_type == "INSERT"
    events = list(service.collect_stream("123"))
    assert events[-1].result.change_type == "UPDATE"


def test_progress_message():
    message = CollectionService._progress_message({
        "phase": "EPISODE_PARALLEL", "chapter_done": 12,
        "chapter_total": 100, "chapter_in_flight": 20, "chapter_failed": 2,
    })
    assert "완료 12/100" in message
    assert "처리 중 20개" in message
    assert "실패 2개" in message
