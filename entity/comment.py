from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Comment:
    comment_id: int
    novel_id: int
    episode_id: int

    parent_comment_id: int | None = None
    reply_level: int | None = None
    content_type: str | None = None
    comment_text: str | None = None

    like_count: int | None = None
    dislike_count: int | None = None
    created_at: datetime | None = None

    secret: bool | None = None
    report_status: str | None = None
    block_status: bool | None = None
    collected_at: datetime | None = None