from dataclasses import dataclass


@dataclass(frozen=True)
class NovelAuthor:
    author_id: int
    author_name: str
    author_url: str | None
    is_illustrator: bool