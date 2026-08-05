"""MySQL repository for the web-novel domain.

This module uses only the root project's entities and database schema. It is
independent from project_1 and project_2.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Sequence

import mysql.connector
from dotenv import load_dotenv
from mysql.connector.connection import MySQLConnection

from entity.comment import Comment
from entity.episode import Episode
from entity.novel import Novel
from entity.novel_author import NovelAuthor
from entity.novel_statistics import NovelStatistics


load_dotenv()


class Repository:
    """Singleton MySQL repository for novels and collected child records."""

    _instance: Repository | None = None
    connection: MySQLConnection | None

    def __new__(cls) -> Repository:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.connection = None
        return cls._instance

    def get_connection(self) -> MySQLConnection:
        """Return a live connection, reconnecting when necessary."""
        if self.connection is None or not self.connection.is_connected():
            self.connection = mysql.connector.connect(
                host=os.getenv("DB_HOST", "127.0.0.1"),
                port=int(os.getenv("MYSQL_PORT", os.getenv("DB_PORT", "3306"))),
                user=os.getenv("DB_USER", os.getenv("MYSQL_USER")),
                password=os.getenv("DB_PASSWORD", os.getenv("MYSQL_PASSWORD")),
                database=os.getenv("DB_NAME", os.getenv("MYSQL_DATABASE")),
                charset="utf8mb4",
                use_unicode=True,
                autocommit=False,
            )
        return self.connection

    def close(self) -> None:
        """Close the cached connection."""
        if self.connection is not None and self.connection.is_connected():
            self.connection.close()
        self.connection = None

    @contextmanager
    def _cursor(self, *, dictionary: bool = False) -> Iterator[Any]:
        cursor = self.get_connection().cursor(dictionary=dictionary)
        try:
            yield cursor
        finally:
            cursor.close()

    def get_novel(self, novel_id: int) -> Novel | None:
        with self._cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM novel WHERE novel_id = %s", (novel_id,))
            row = cursor.fetchone()
        return self._row_to_novel(row) if row else None

    def find_novel(self, novel_id: int) -> Novel | None:
        """Compatibility alias matching the supplied repository style."""
        return self.get_novel(novel_id)

    def get_novel_statistics(self, novel_id: int) -> NovelStatistics | None:
        with self._cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT * FROM novel_statistics WHERE novel_id = %s",
                (novel_id,),
            )
            row = cursor.fetchone()
        return self._row_to_statistics(row) if row else None

    def get_author(self, novel_id: int) -> NovelAuthor | None:
        with self._cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT a.*
                FROM novel AS n
                JOIN novel_author AS a ON a.author_id = n.author_id
                WHERE n.novel_id = %s
                """,
                (novel_id,),
            )
            row = cursor.fetchone()
        return self._row_to_author(row) if row else None

    def get_episodes(self, novel_id: int) -> list[Episode]:
        with self._cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT * FROM episode WHERE novel_id = %s ORDER BY episode_number",
                (novel_id,),
            )
            rows = cursor.fetchall()
        return [self._row_to_episode(row) for row in rows]

    def get_comments(self, novel_id: int) -> list[Comment]:
        with self._cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT * FROM comment
                WHERE novel_id = %s
                ORDER BY episode_id, created_at, comment_id
                """,
                (novel_id,),
            )
            rows = cursor.fetchall()
        return [self._row_to_comment(row) for row in rows]

    def find_free_novels(self, *, limit: int | None = None) -> list[Novel]:
        """Return free, non-paid, unfinished novels from the current DB state."""
        query = (
            "SELECT * FROM novel "
            "WHERE free = 1 AND paid_serial = 0 AND finish = 0 "
            "ORDER BY collected_at DESC, novel_id"
        )
        params: tuple[Any, ...] = ()
        if limit is not None:
            if limit <= 0:
                raise ValueError("limit must be greater than zero")
            query += " LIMIT %s"
            params = (limit,)
        with self._cursor(dictionary=True) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [self._row_to_novel(row) for row in rows]

    def novel_exists(self, novel_id: int) -> bool:
        with self._cursor() as cursor:
            cursor.execute("SELECT 1 FROM novel WHERE novel_id = %s", (novel_id,))
            return cursor.fetchone() is not None

    def list_novels(
        self, page: int, page_size: int
    ) -> tuple[list[dict[str, Any]], int]:
        """Return one DB-backed page for the collection screen."""
        if page_size <= 0:
            raise ValueError("page_size must be greater than zero")
        page = max(1, int(page))
        with self._cursor(dictionary=True) as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM novel")
            total = int(cursor.fetchone()["total"])
            cursor.execute(
                """
                SELECT n.novel_id, n.title, COALESCE(a.author_name, '') AS author_name,
                       n.free, n.paid_serial, n.finish, s.view_count,
                       s.preference_count, s.chapter_count, n.collected_at
                FROM novel AS n
                LEFT JOIN novel_author AS a ON a.author_id = n.author_id
                LEFT JOIN novel_statistics AS s ON s.novel_id = n.novel_id
                ORDER BY n.novel_id
                LIMIT %s OFFSET %s
                """,
                (page_size, (page - 1) * page_size),
            )
            rows = cursor.fetchall()
        return rows, total

    def find_page(self, novel_id: int, page_size: int) -> int:
        if page_size <= 0:
            raise ValueError("page_size must be greater than zero")
        with self._cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS preceding FROM novel WHERE novel_id < %s",
                (novel_id,),
            )
            preceding = int(cursor.fetchone()["preceding"])
        return preceding // page_size + 1

    def get_episode_statistics(self) -> list[dict[str, Any]]:
        """Return episode data used to calculate global prediction rates."""
        with self._cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT novel_id, episode_number, view_count, access_type
                FROM episode
                WHERE view_count IS NOT NULL AND access_type IS NOT NULL
                ORDER BY novel_id, episode_number
                """
            )
            return cursor.fetchall()

    def list_recommendation_genres(self) -> list[dict[str, Any]]:
        """Return genres that contain at least one scored novel."""
        with self._cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT g.genre_id, g.genre_name, COUNT(DISTINCT n.novel_id) AS novel_count
                FROM novel_genre AS g
                JOIN novel AS n ON g.genre_id = n.genre_1
                JOIN novel_recommendation_score AS r ON r.novel_id = n.novel_id
                  AND r.scored_episode_count >= 1
                  AND r.free_score IS NOT NULL
                WHERE n.free = 1
                  AND COALESCE(n.paid_serial, 0) = 0
                  AND COALESCE(n.finish, 0) = 0
                  AND COALESCE(n.pause, 0) = 0
                  AND EXISTS (
                      SELECT 1
                      FROM episode AS e50
                      WHERE e50.novel_id = n.novel_id
                        AND e50.episode_number >= 30
                  )
                GROUP BY g.genre_id, g.genre_name
                ORDER BY
                    CASE
                        WHEN LEFT(g.genre_name, 1) BETWEEN '가' AND '힣' THEN 0
                        ELSE 1
                    END,
                    g.genre_name
                """
            )
            return cursor.fetchall()

    def find_recommendations_by_genre(
        self, genre_id: int, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return the highest-scoring novels in a genre."""
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        with self._cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT
                    n.novel_id, n.title, n.source_url, n.introduction,
                    COALESCE(a.author_name, '') AS author_name,
                    g.genre_name,
                    r.free_score AS recommendation_score,
                    r.free_score, r.paid_score,
                    r.retention_score, r.reference_view_count,
                    r.view_scale_max, r.view_grade,
                    r.scored_episode_count, r.average_dropout_rate,
                    COALESCE(s.view_count, 0) AS view_count,
                    COALESCE(s.preference_count, 0) AS preference_count,
                    COALESCE(s.like_count, 0) AS like_count,
                    GREATEST(
                        COALESCE(s.chapter_count, 0),
                        COALESCE(
                            (
                                SELECT MAX(e2.episode_number)
                                FROM episode AS e2
                                WHERE e2.novel_id = n.novel_id
                            ),
                            0
                        )
                    ) AS chapter_count,
                    COALESCE(c.positive_count, 0) AS positive_count,
                    COALESCE(c.negative_count, 0) AS negative_count,
                    COALESCE(c.neutral_count, 0) AS neutral_count,
                    COALESCE(c.total_count, 0) AS comment_count,
                    COALESCE(p.predicted_purchase_count, 0) AS predicted_purchase_count,
                    COALESCE(p.predicted_conversion_rate, 0) AS predicted_conversion_rate,
                    COALESCE(p.predicted_paid_dropout_rate, 1) AS predicted_paid_dropout_rate,
                    COALESCE(p.model_mae, 0) AS conversion_model_mae,
                    COALESCE(p.training_sample_count, 0) AS conversion_training_samples
                FROM novel AS n
                JOIN novel_genre AS g
                  ON g.genre_id = %s AND g.genre_id = n.genre_1
                JOIN novel_recommendation_score AS r ON r.novel_id = n.novel_id
                  AND r.scored_episode_count >= 1
                  AND r.free_score IS NOT NULL
                LEFT JOIN novel_author AS a ON a.author_id = n.author_id
                LEFT JOIN novel_statistics AS s ON s.novel_id = n.novel_id
                LEFT JOIN novel_comment_sentiment AS c ON c.novel_id = n.novel_id
                LEFT JOIN novel_paid_conversion_prediction AS p
                  ON p.novel_id = n.novel_id
                WHERE n.free = 1
                  AND COALESCE(n.paid_serial, 0) = 0
                  AND COALESCE(n.finish, 0) = 0
                  AND COALESCE(n.pause, 0) = 0
                  AND EXISTS (
                      SELECT 1
                      FROM episode AS e50
                      WHERE e50.novel_id = n.novel_id
                        AND e50.episode_number >= 30
                  )
                ORDER BY r.free_score DESC,
                         r.average_dropout_rate ASC,
                         r.scored_episode_count DESC,
                         n.novel_id
                LIMIT %s
                """,
                (genre_id, limit),
            )
            return cursor.fetchall()

    def get_recommendation_episode_scores(
        self, novel_id: int
    ) -> list[dict[str, Any]]:
        """Return notebook-compatible per-episode decline inputs for one novel."""
        with self._cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                WITH ordered_episode AS (
                    SELECT
                        episode_id, novel_id, episode_number, access_type, view_count,
                        LAG(access_type) OVER (
                            PARTITION BY novel_id ORDER BY episode_number, episode_id
                        ) AS previous_access_type,
                        LAG(view_count) OVER (
                            PARTITION BY novel_id ORDER BY episode_number, episode_id
                        ) AS previous_view_count
                    FROM episode
                    WHERE novel_id = %s
                )
                SELECT
                    episode_number, access_type, previous_view_count, view_count,
                    CASE
                        WHEN view_count = 0 THEN 1.0
                        ELSE GREATEST(
                            0.0,
                            (previous_view_count - view_count) / previous_view_count
                        )
                    END AS dropout_rate
                FROM ordered_episode
                WHERE episode_number > 25
                  AND access_type = previous_access_type
                  AND (view_count = 0 OR previous_view_count > 0)
                  AND view_count IS NOT NULL
                  AND access_type IN ('FREE', 'PAID')
                ORDER BY episode_number
                """,
                (novel_id,),
            )
            return cursor.fetchall()

    def save_result(self, novel_id: int, result: dict[str, Any]) -> dict[str, int]:
        """Atomically upsert a crawler result directly into MySQL."""
        novel_data = result.get("novel")
        if not isinstance(novel_data, dict):
            raise ValueError("crawler result does not contain novel data")
        if int(novel_data.get("novel_id", novel_id)) != novel_id:
            raise ValueError("crawler result novel_id does not match")

        changed = {
            table: len(value) if isinstance(value, list) else int(bool(value))
            for table, value in result.items()
            if table in self._TABLE_COLUMNS
        }
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            for table in ("novel_author", "novel_group", "novel_genre", "tag"):
                self._upsert_raw_rows(cursor, table, self._as_rows(result.get(table)))
            self._upsert_raw_rows(cursor, "novel", [novel_data])

            cursor.execute("DELETE FROM comment WHERE novel_id = %s", (novel_id,))
            cursor.execute("DELETE FROM episode WHERE novel_id = %s", (novel_id,))
            cursor.execute("DELETE FROM novel_statistics WHERE novel_id = %s", (novel_id,))
            cursor.execute("DELETE FROM novel_tag WHERE novel_id = %s", (novel_id,))

            for table in ("novel_tag", "novel_statistics", "episode"):
                self._upsert_raw_rows(cursor, table, self._as_rows(result.get(table)))

            comments = self._as_rows(result.get("comment"))
            parent_ids = {row.get("comment_id") for row in comments}
            self._upsert_raw_rows(
                cursor,
                "comment",
                [dict(row, parent_comment_id=None) for row in comments],
            )
            for row in comments:
                parent_id = row.get("parent_comment_id")
                if parent_id not in (None, "") and parent_id in parent_ids:
                    cursor.execute(
                        "UPDATE comment SET parent_comment_id = %s WHERE comment_id = %s",
                        (parent_id, row.get("comment_id")),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
        return changed

    _TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
        "tag": ("tag_id", "tag_name"),
        "novel_genre": ("genre_id", "genre_name"),
        "novel_author": ("author_id", "author_name", "author_url", "is_illustrator"),
        "novel_group": ("novel_group_id", "group_name"),
        "novel": (
            "novel_id", "source_url", "title", "introduction", "author_id",
            "illustrator_id", "origin_cover_url", "group_id", "free", "paid_serial",
            "exclusive", "pre_exclusive", "adult", "contest", "rental", "pause",
            "finish", "epub", "ebook", "cp_novel", "created_at", "updated_at",
            "paid_conversion_open_at", "isbn", "period", "unit_type", "collected_at",
            "genre_1", "genre_2",
        ),
        "novel_tag": ("novel_id", "tag_id"),
        "episode": (
            "episode_id", "novel_id", "episode_number", "episode_title", "published_at",
            "access_type", "view_count", "like_count", "comment_count", "page_count",
            "adult", "paid_conversion_before_entry", "up", "collected_at",
        ),
        "novel_statistics": (
            "novel_id", "view_count", "preference_count", "like_count", "chapter_count",
            "free_chapter_count", "characters", "male_count", "female_count",
            "age_10s_percent", "age_20s_percent", "age_30s_percent", "age_40s_percent",
            "age_50s_percent", "source_notice_count", "collected_at",
        ),
        "comment": (
            "comment_id", "novel_id", "episode_id", "parent_comment_id", "reply_level",
            "content_type", "comment_text", "like_count", "dislike_count", "created_at",
            "secret", "report_status", "block_status", "collected_at",
        ),
    }
    _PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
        "tag": ("tag_id",), "novel_genre": ("genre_id",),
        "novel_author": ("author_id",), "novel_group": ("novel_group_id",),
        "novel": ("novel_id",), "novel_tag": ("novel_id", "tag_id"),
        "episode": ("episode_id",), "novel_statistics": ("novel_id",),
        "comment": ("comment_id",),
    }

    @staticmethod
    def _as_rows(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        return []

    def _upsert_raw_rows(
        self, cursor: Any, table: str, rows: Sequence[dict[str, Any]]
    ) -> None:
        columns = self._TABLE_COLUMNS[table]
        primary_keys = self._PRIMARY_KEYS[table]
        quoted = ", ".join(f"`{column}`" for column in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        update_columns = [column for column in columns if column not in primary_keys]
        if update_columns:
            assignments = ", ".join(
                f"`{column}` = new.`{column}`" for column in update_columns
            )
        else:
            assignments = "`novel_id` = new.`novel_id`"
        query = (
            f"INSERT INTO `{table}` ({quoted}) VALUES ({placeholders}) AS new "
            f"ON DUPLICATE KEY UPDATE {assignments}"
        )
        for row in rows:
            cursor.execute(
                query,
                tuple(None if row.get(column) == "" else row.get(column) for column in columns),
            )

    def save_collection(
        self,
        novel: Novel,
        statistics: NovelStatistics,
        author: NovelAuthor | None,
        episodes: list[Episode],
        comments: list[Comment],
    ) -> None:
        """Atomically insert or update one complete crawl result."""
        self._validate_collection(novel, statistics, author, episodes, comments)
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            if author is not None:
                self._upsert_author(cursor, author)
            self._ensure_reference_rows(cursor, novel, author)
            self._upsert_novel(cursor, novel)
            self._upsert_statistics(cursor, statistics)
            self._upsert_episodes(cursor, episodes)
            self._upsert_comments(cursor, comments)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()

    def create_novel(self, novel: Novel) -> None:
        """Insert or update a novel without child records."""
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            self._ensure_reference_rows(cursor, novel, None)
            self._upsert_novel(cursor, novel)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()

    def _ensure_reference_rows(
        self,
        cursor: Any,
        novel: Novel,
        author: NovelAuthor | None,
    ) -> None:
        if novel.author_id is not None and author is None:
            cursor.execute(
                "INSERT IGNORE INTO novel_author (author_id) VALUES (%s)",
                (novel.author_id,),
            )
        if novel.illustrator_id is not None:
            cursor.execute(
                "INSERT IGNORE INTO novel_author (author_id, is_illustrator) VALUES (%s, 1)",
                (novel.illustrator_id,),
            )
        if novel.group_id is not None:
            cursor.execute(
                "INSERT IGNORE INTO novel_group (novel_group_id) VALUES (%s)",
                (novel.group_id,),
            )
        for genre_id in (novel.genre_1, novel.genre_2):
            if genre_id is not None:
                cursor.execute(
                    "INSERT IGNORE INTO novel_genre (genre_id) VALUES (%s)",
                    (genre_id,),
                )

    def _upsert_author(self, cursor: Any, author: NovelAuthor) -> None:
        cursor.execute(
            """
            INSERT INTO novel_author (author_id, author_name, author_url, is_illustrator)
            VALUES (%s, %s, %s, %s) AS new
            ON DUPLICATE KEY UPDATE
                author_name = new.author_name,
                author_url = new.author_url,
                is_illustrator = new.is_illustrator
            """,
            (
                author.author_id,
                author.author_name,
                author.author_url,
                author.is_illustrator,
            ),
        )

    def _upsert_novel(self, cursor: Any, novel: Novel) -> None:
        columns = (
            "novel_id", "source_url", "title", "introduction", "author_id",
            "illustrator_id", "origin_cover_url", "group_id", "free", "paid_serial",
            "exclusive", "pre_exclusive", "adult", "contest", "rental", "pause",
            "finish", "epub", "ebook", "cp_novel", "created_at", "updated_at",
            "paid_conversion_open_at", "isbn", "period", "unit_type", "collected_at",
            "genre_1", "genre_2",
        )
        values = tuple(getattr(novel, column) for column in columns)
        self._upsert(cursor, "novel", columns, values, "novel_id")

    def _upsert_statistics(self, cursor: Any, statistics: NovelStatistics) -> None:
        columns = (
            "novel_id", "view_count", "preference_count", "like_count",
            "chapter_count", "free_chapter_count", "characters", "male_count",
            "female_count", "age_10s_percent", "age_20s_percent", "age_30s_percent",
            "age_40s_percent", "age_50s_percent", "source_notice_count", "collected_at",
        )
        values = tuple(getattr(statistics, column) for column in columns)
        self._upsert(cursor, "novel_statistics", columns, values, "novel_id")

    def _upsert_episodes(self, cursor: Any, episodes: Sequence[Episode]) -> None:
        columns = (
            "episode_id", "novel_id", "episode_number", "episode_title", "published_at",
            "access_type", "view_count", "like_count", "comment_count", "page_count",
            "adult", "paid_conversion_before_entry", "up", "collected_at",
        )
        for episode in episodes:
            values = tuple(getattr(episode, column) for column in columns)
            self._upsert(cursor, "episode", columns, values, "episode_id")

    def _upsert_comments(self, cursor: Any, comments: Sequence[Comment]) -> None:
        columns = (
            "comment_id", "novel_id", "episode_id", "parent_comment_id", "reply_level",
            "content_type", "comment_text", "like_count", "dislike_count", "created_at",
            "secret", "report_status", "block_status", "collected_at",
        )
        # Insert without the self-reference first so replies may arrive before parents.
        for comment in comments:
            values = tuple(
                None if column == "parent_comment_id" else getattr(comment, column)
                for column in columns
            )
            self._upsert(cursor, "comment", columns, values, "comment_id")
        for comment in comments:
            if comment.parent_comment_id is not None:
                cursor.execute(
                    "UPDATE comment SET parent_comment_id = %s WHERE comment_id = %s",
                    (comment.parent_comment_id, comment.comment_id),
                )

    @staticmethod
    def _upsert(
        cursor: Any,
        table: str,
        columns: Sequence[str],
        values: Sequence[Any],
        primary_key: str,
    ) -> None:
        quoted = [f"`{column}`" for column in columns]
        assignments = ", ".join(
            f"`{column}` = new.`{column}`" for column in columns if column != primary_key
        )
        placeholders = ", ".join(["%s"] * len(columns))
        query = (
            f"INSERT INTO `{table}` ({', '.join(quoted)}) "
            f"VALUES ({placeholders}) AS new "
            f"ON DUPLICATE KEY UPDATE {assignments}"
        )
        cursor.execute(query, tuple(values))

    @staticmethod
    def _validate_collection(
        novel: Novel,
        statistics: NovelStatistics,
        author: NovelAuthor | None,
        episodes: Sequence[Episode],
        comments: Sequence[Comment],
    ) -> None:
        if statistics.novel_id != novel.novel_id:
            raise ValueError("novel and statistics IDs do not match")
        if author is not None and novel.author_id != author.author_id:
            raise ValueError("novel and author IDs do not match")
        if any(item.novel_id != novel.novel_id for item in (*episodes, *comments)):
            raise ValueError("child entity novel IDs do not match")
        episode_ids = {episode.episode_id for episode in episodes}
        if any(comment.episode_id not in episode_ids for comment in comments):
            raise ValueError("a comment references an episode outside this collection")
        comment_ids = {comment.comment_id for comment in comments}
        if any(
            comment.parent_comment_id is not None
            and comment.parent_comment_id not in comment_ids
            for comment in comments
        ):
            raise ValueError("a comment references a parent outside this collection")

    @staticmethod
    def _row_to_novel(row: dict[str, Any]) -> Novel:
        return Novel(**{field: row.get(field) for field in Novel.__dataclass_fields__})

    @staticmethod
    def _row_to_statistics(row: dict[str, Any]) -> NovelStatistics:
        return NovelStatistics(
            **{field: row.get(field) for field in NovelStatistics.__dataclass_fields__}
        )

    @staticmethod
    def _row_to_author(row: dict[str, Any]) -> NovelAuthor:
        return NovelAuthor(
            author_id=row["author_id"],
            author_name=row.get("author_name") or "",
            author_url=row.get("author_url"),
            is_illustrator=bool(row.get("is_illustrator")),
        )

    @staticmethod
    def _row_to_episode(row: dict[str, Any]) -> Episode:
        return Episode(**{field: row.get(field) for field in Episode.__dataclass_fields__})

    @staticmethod
    def _row_to_comment(row: dict[str, Any]) -> Comment:
        return Comment(**{field: row.get(field) for field in Comment.__dataclass_fields__})
