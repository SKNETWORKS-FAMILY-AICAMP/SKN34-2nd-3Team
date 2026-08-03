from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Novel:
    novel_id: int
    source_url: str
    title: str

    introduction: str | None = None
    author_id: int | None = None
    illustrator_id: int | None = None
    origin_cover_url: str | None = None
    group_id: int | None = None

    free: bool | None = None
    paid_serial: bool | None = None
    exclusive: bool | None = None
    pre_exclusive: bool | None = None
    adult: bool | None = None
    contest: bool | None = None
    rental: bool | None = None
    pause: bool | None = None
    finish: bool | None = None
    epub: bool | None = None
    ebook: bool | None = None
    cp_novel: bool | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None
    paid_conversion_open_at: datetime | None = None

    isbn: str | None = None
    period: int | None = None
    unit_type: str | None = None
    collected_at: datetime | None = None

    genre_1: int | None = None
    genre_2: int | None = None