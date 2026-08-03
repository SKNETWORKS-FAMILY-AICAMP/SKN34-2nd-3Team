from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class NovelStatistics:
    novel_id: int

    view_count: int | None = None
    preference_count: int | None = None
    like_count: int | None = None
    chapter_count: int | None = None
    free_chapter_count: int | None = None
    characters: int | None = None

    male_count: int | None = None
    female_count: int | None = None

    age_10s_percent: float | None = None
    age_20s_percent: float | None = None
    age_30s_percent: float | None = None
    age_40s_percent: float | None = None
    age_50s_percent: float | None = None

    source_notice_count: int | None = None
    collected_at: datetime | None = None