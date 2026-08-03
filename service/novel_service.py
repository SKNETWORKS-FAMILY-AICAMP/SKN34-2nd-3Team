from __future__ import annotations
from urllib.parse import urlparse

from entity.comment import Comment
from entity.episode import Episode
from entity.novel import Novel
from entity.novel_author import NovelAuthor
from entity.novel_statistics import NovelStatistics

from repository.novel_repository import NovelRepository
from service.novel_service_errors import InvalidNovelInputError

class NovelService:
    def __init__(self, repository: NovelRepository) -> None:
        self.repository = repository

    def parse_novel_id(self, url_or_id: str) -> int:
        value = str(url_or_id).strip()
        if not value: raise InvalidNovelInputError("작품 주소 또는 작품 ID를 입력해주세요.")
        
        if value.isdigit():
            novel_id = int(value)
            self._validate_novel_id(novel_id)
            return novel_id

        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            raise InvalidNovelInputError("올바른 문피아 작품 주소 또는 숫자 ID가 아닙니다.")

        host = parsed.netloc.lower().split(":")[0]
        path_parts = [part for part in parsed.path.strip("/").split("/") if part]

        novel_id: int | None = None
        if host == "novel.munpia.com" and len(path_parts) >= 1 and path_parts[0].isdigit():
            novel_id = int(path_parts[0])
        elif host in {"munpia.com", "www.munpia.com"} and len(path_parts) >= 3 and path_parts[0] == "novel" and path_parts[1] == "detail" and path_parts[2].isdigit():
            novel_id = int(path_parts[2])

        if novel_id is None:
            raise InvalidNovelInputError("올바른 문피아 작품 주소 또는 숫자 ID가 아닙니다.")
            
        self._validate_novel_id(novel_id)
        return novel_id

    def _validate_novel_id(self, novel_id: int) -> None:
        if isinstance(novel_id, bool) or not isinstance(novel_id, int) or novel_id <= 0:
            raise InvalidNovelInputError("작품 ID는 1 이상의 정수여야 합니다.")

    def get_novel(self, novel_id: int) -> Novel | None:
        self._validate_novel_id(novel_id)
        return self.repository.get_novel(novel_id)

    def get_novel_statistics(self, novel_id: int) -> NovelStatistics | None:
        self._validate_novel_id(novel_id)
        return self.repository.get_novel_statistics(novel_id)

    def get_author(self, novel_id: int) -> NovelAuthor | None:
        self._validate_novel_id(novel_id)
        return self.repository.get_author(novel_id)

    def get_episodes(self, novel_id: int) -> list[Episode]:
        self._validate_novel_id(novel_id)
        return self.repository.get_episodes(novel_id)

    def get_comments(self, novel_id: int) -> list[Comment]:
        self._validate_novel_id(novel_id)
        return self.repository.get_comments(novel_id)