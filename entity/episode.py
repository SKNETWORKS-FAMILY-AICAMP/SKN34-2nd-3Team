from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Episode:
    episode_id: int
    novel_id: int
    episode_number: int

    episode_title: str | None = None
    published_at: datetime | None = None
    access_type: str | None = None

    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    page_count: int | None = None

    adult: bool | None = None
    paid_conversion_before_entry: bool | None = None
    up: bool | None = None
    collected_at: datetime | None = None