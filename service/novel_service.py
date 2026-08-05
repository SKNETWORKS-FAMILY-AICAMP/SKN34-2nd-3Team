from __future__ import annotations
from urllib.parse import urlparse

from entity.comment import Comment
from entity.episode import Episode
from entity.novel import Novel
from entity.novel_author import NovelAuthor
from entity.novel_statistics import NovelStatistics

from repository.repository import Repository
from service.novel_service_errors import InvalidNovelInputError

class NovelService:
    def __init__(self, repository: Repository) -> None:
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

    def parse_author_id(self, author_id: str) -> int:
        value = str(author_id).strip()
        if not value or not value.isdigit():
            raise InvalidNovelInputError("작가 ID는 1 이상의 정수여야 합니다.")
        parsed_author_id = int(value)
        self._validate_author_id(parsed_author_id)
        return parsed_author_id

    def _validate_author_id(self, author_id: int) -> None:
        if (
            isinstance(author_id, bool)
            or not isinstance(author_id, int)
            or author_id <= 0
        ):
            raise InvalidNovelInputError("작가 ID는 1 이상의 정수여야 합니다.")

    def get_novel(self, novel_id: int) -> Novel | None:
        self._validate_novel_id(novel_id)
        return self.repository.get_novel(novel_id)

    def get_novel_statistics(self, novel_id: int) -> NovelStatistics | None:
        self._validate_novel_id(novel_id)
        return self.repository.get_novel_statistics(novel_id)

    def get_author(self, novel_id: int) -> NovelAuthor | None:
        self._validate_novel_id(novel_id)
        return self.repository.get_author(novel_id)

    def get_author_by_id(self, author_id: int) -> NovelAuthor | None:
        self._validate_author_id(author_id)
        return self.repository.get_author_by_id(author_id)

    def get_novels_by_author(self, author_id: int) -> list[Novel]:
        self._validate_author_id(author_id)
        return self.repository.get_novels_by_author(author_id)

    def get_episodes(self, novel_id: int) -> list[Episode]:
        self._validate_novel_id(novel_id)
        return self.repository.get_episodes(novel_id)

    def get_comments(self, novel_id: int) -> list[Comment]:
        self._validate_novel_id(novel_id)
        return self.repository.get_comments(novel_id)
