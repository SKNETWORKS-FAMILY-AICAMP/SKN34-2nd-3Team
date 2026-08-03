from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
import pandas as pd

from entity.comment import Comment
from entity.episode import Episode
from entity.novel import Novel
from entity.novel_author import NovelAuthor
from entity.novel_statistics import NovelStatistics
from service.novel_service_errors import CsvFileError, CsvSchemaError

NOVEL_REQUIRED_COLUMNS = {"work_id", "source_url", "title", "introduction", "origin_cover_url", "author_id", "free", "paid_serial", "exclusive", "pre_exclusive", "adult", "contest", "rental", "pause", "finish", "epub", "ebook", "cp_novel", "created_at", "updated_at", "paid_conversion_open_at", "isbn", "period", "unit_type", "collected_at"}
STATISTICS_REQUIRED_COLUMNS = {"work_id", "view_count", "preference_count", "like_count", "chapter_count", "free_chapter_count", "characters", "male_count", "female_count", "age_10s_percent", "age_20s_percent", "age_30s_percent", "age_40s_percent", "age_50s_percent", "notice_count", "collected_at"}
AUTHOR_REQUIRED_COLUMNS = {"author_id", "author_name", "author_url", "is_illustrator"}
EPISODE_REQUIRED_COLUMNS = {"work_id", "episode_id", "episode_number", "episode_title", "published_at", "access_type", "view_count", "like_count", "comment_count", "page_count", "adult", "paid_conversion_before_entry", "up", "collected_at"}
COMMENT_REQUIRED_COLUMNS = {"work_id", "episode_id", "comment_id", "parent_comment_id", "reply_level", "content_type", "comment_text", "like_count", "dislike_count", "created_at", "secret", "report_status", "block_status", "collected_at"}

NOVEL_REQUIRED_COLUMNS = {"work_id", "source_url", "title", "introduction", "origin_cover_url", "author_id", "free", "paid_serial", "exclusive", "pre_exclusive", "adult", "contest", "rental", "pause", "finish", "epub", "ebook", "cp_novel", "created_at", "updated_at", "paid_conversion_open_at", "isbn", "period", "unit_type", "collected_at"}
# (이하 코드 동일)

class NovelRepository(ABC):
    """데이터 조회 계약(인터페이스)"""
    @abstractmethod
    def get_novel(self, novel_id: int) -> Novel | None: pass
    @abstractmethod
    def get_novel_statistics(self, novel_id: int) -> NovelStatistics | None: pass
    @abstractmethod
    def get_author(self, novel_id: int) -> NovelAuthor | None: pass
    @abstractmethod
    def get_episodes(self, novel_id: int) -> list[Episode]: pass
    @abstractmethod
    def get_comments(self, novel_id: int) -> list[Comment]: pass

class CsvNovelRepository(NovelRepository):
    """CSV 데이터를 다루는 DAO 구현체"""
    def __init__(
        self,
        works_csv_path: str | Path,
        authors_csv_path: str | Path,
        episodes_csv_path: str | Path,
        comments_csv_path: str | Path,
        *,
        works_chunk_size: int = 50_000,
        child_chunk_size: int = 500_000,
    ) -> None:
        self.works_csv_path = Path(works_csv_path)
        self.authors_csv_path = Path(authors_csv_path)
        self.episodes_csv_path = Path(episodes_csv_path)
        self.comments_csv_path = Path(comments_csv_path)
        
        self.works_chunk_size = works_chunk_size
        self.child_chunk_size = child_chunk_size

        self._work_row_cache: dict[int, pd.Series | None] = {}
        self._author_cache: dict[int, NovelAuthor | None] = {}
        self._episode_cache: dict[int, list[Episode]] = {}
        self._comment_cache: dict[int, list[Comment]] = {}

    def get_novel(self, novel_id: int) -> Novel | None:
        row = self._find_work_row(novel_id)
        if row is None: return None
        self._validate_columns(row.index, NOVEL_REQUIRED_COLUMNS, "works.csv")
        return self._row_to_novel(row)

    def get_novel_statistics(self, novel_id: int) -> NovelStatistics | None:
        row = self._find_work_row(novel_id)
        if row is None: return None
        self._validate_columns(row.index, STATISTICS_REQUIRED_COLUMNS, "works.csv")
        return self._row_to_novel_statistics(row)

    def get_author(self, novel_id: int) -> NovelAuthor | None:
        novel = self.get_novel(novel_id)
        if novel is None or novel.author_id is None: return None
        
        author_id = novel.author_id
        if author_id in self._author_cache: return self._author_cache[author_id]
        
        self._ensure_csv_file(self.authors_csv_path)
        self._validate_csv_header(self.authors_csv_path, AUTHOR_REQUIRED_COLUMNS, "authors.csv")
        
        try:
            rows = pd.read_csv(self.authors_csv_path, usecols=sorted(AUTHOR_REQUIRED_COLUMNS), dtype={"author_id": "int64"}, engine="c", low_memory=False, memory_map=True)
        except pd.errors.EmptyDataError:
            self._author_cache[author_id] = None
            return None
            
        matched_rows = rows[rows["author_id"] == author_id]
        if matched_rows.empty:
            self._author_cache[author_id] = None
            return None
            
        author = self._row_to_author(matched_rows.iloc[0])
        self._author_cache[author_id] = author
        return author

    def get_episodes(self, novel_id: int) -> list[Episode]:
        if novel_id in self._episode_cache: return self._episode_cache[novel_id]
        rows = self._read_rows_by_work_id(self.episodes_csv_path, EPISODE_REQUIRED_COLUMNS, novel_id, "episodes.csv")
        if rows.empty:
            self._episode_cache[novel_id] = []
            return []
        episodes = self._rows_to_episodes(rows)
        episodes.sort(key=lambda episode: episode.episode_number)
        self._episode_cache[novel_id] = episodes
        return episodes

    def get_comments(self, novel_id: int) -> list[Comment]:
        if novel_id in self._comment_cache: return self._comment_cache[novel_id]
        rows = self._read_rows_by_work_id(self.comments_csv_path, COMMENT_REQUIRED_COLUMNS, novel_id, "comments.csv")
        if rows.empty:
            self._comment_cache[novel_id] = []
            return []
        comments = self._rows_to_comments(rows)
        self._comment_cache[novel_id] = comments
        return comments

    def _find_work_row(self, novel_id: int) -> pd.Series | None:
        if novel_id in self._work_row_cache:
            return self._work_row_cache[novel_id]
        self._ensure_csv_file(self.works_csv_path)
        try:
            for chunk in pd.read_csv(self.works_csv_path, chunksize=self.works_chunk_size, engine="c", low_memory=False, memory_map=True):
                numeric_work_ids = pd.to_numeric(chunk["work_id"], errors="coerce")
                matched_rows = chunk[numeric_work_ids == novel_id]
                if not matched_rows.empty:
                    row = matched_rows.iloc[0].copy()
                    self._work_row_cache[novel_id] = row
                    return row
        except Exception: pass
        self._work_row_cache[novel_id] = None
        return None

    def _read_rows_by_work_id(self, csv_path: Path, columns: set[str], novel_id: int, csv_name: str) -> pd.DataFrame:
        self._ensure_csv_file(csv_path)
        matched_chunks = []
        found_target = False
        try:
            for chunk in pd.read_csv(csv_path, usecols=sorted(columns), dtype={"work_id": "int64"}, chunksize=self.child_chunk_size, engine="c", low_memory=False, memory_map=True):
                if chunk.empty: continue
                work_ids = chunk["work_id"]
                if int(work_ids.iloc[-1]) < novel_id: continue
                if int(work_ids.iloc[0]) > novel_id: break
                matched_rows = chunk[work_ids == novel_id]
                if not matched_rows.empty:
                    found_target = True
                    matched_chunks.append(matched_rows.copy())
                if found_target and int(work_ids.iloc[-1]) > novel_id: break
        except Exception: pass
        if not matched_chunks: return pd.DataFrame(columns=sorted(columns))
        return pd.concat(matched_chunks, ignore_index=True)

    def _ensure_csv_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file() or path.stat().st_size == 0:
            raise CsvFileError(f"CSV 파일을 확인하세요: {path}")

    def _validate_csv_header(self, path: Path, required_columns: set[str], csv_name: str) -> None:
        header = pd.read_csv(path, nrows=0)
        self._validate_columns(header.columns, required_columns, csv_name)

    def _validate_columns(self, columns: Any, required_columns: set[str], csv_name: str) -> None:
        missing = required_columns - set(columns)
        if missing: raise CsvSchemaError(f"{csv_name} 필수 컬럼 누락: {missing}")

    def _row_to_novel(self, row: pd.Series) -> Novel:
        return Novel(novel_id=int(row["work_id"]), source_url=str(row["source_url"]), title=str(row["title"]), introduction=str(row.get("introduction")), author_id=int(row.get("author_id", 0)) if pd.notna(row.get("author_id")) else None, origin_cover_url=str(row.get("origin_cover_url")), free=bool(row.get("free")))
    def _row_to_novel_statistics(self, row: pd.Series) -> NovelStatistics:
        return NovelStatistics(novel_id=int(row["work_id"]), view_count=int(row.get("view_count", 0)), preference_count=int(row.get("preference_count", 0)), chapter_count=int(row.get("chapter_count", 0)))
    def _row_to_author(self, row: pd.Series) -> NovelAuthor:
        return NovelAuthor(author_id=int(row["author_id"]), author_name=str(row["author_name"]), author_url=str(row.get("author_url")), is_illustrator=bool(row.get("is_illustrator", False)))
    def _rows_to_episodes(self, rows: pd.DataFrame) -> list[Episode]:
        return [Episode(episode_id=int(r.episode_id), novel_id=int(r.work_id), episode_number=int(r.episode_number), episode_title=str(r.episode_title)) for r in rows.itertuples()]
    def _rows_to_comments(self, rows: pd.DataFrame) -> list[Comment]:
        return [Comment(comment_id=int(r.comment_id), novel_id=int(r.work_id), episode_id=int(r.episode_id), comment_text=str(r.comment_text)) for r in rows.itertuples()]