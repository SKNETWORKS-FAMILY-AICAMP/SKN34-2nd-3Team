from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import mysql.connector
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_V3_SQL_PATH = ROOT / "db" / "migration" / "V3__create_recommendation_dashboard.sql"


class RecommendationMetricService:
    def __init__(
        self,
        connection_factory: Callable[[], Any] | None = None,
        v3_sql_path: str | Path = DEFAULT_V3_SQL_PATH,
    ) -> None:
        self._connection_factory = connection_factory or self._connect
        self._v3_sql_path = Path(v3_sql_path)

    @staticmethod
    def _connect():
        config = dotenv_values(ROOT / ".env")
        return mysql.connector.connect(
            host=config.get("DB_HOST", "127.0.0.1"),
            port=int(config.get("MYSQL_PORT", "3306")),
            user=config.get("DB_USER", "root"),
            password=config.get("DB_PASSWORD", ""),
            database=config.get("DB_NAME"),
            connection_timeout=15,
            autocommit=True,
        )

    def refresh_all(self) -> None:
        connection = self._connection_factory()
        cursor = None
        try:
            sql = self._v3_sql_path.read_text(encoding="utf-8")
            cursor = connection.cursor()
            for statement in (part.strip() for part in sql.split(";")):
                if statement:
                    cursor.execute(statement)
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()
