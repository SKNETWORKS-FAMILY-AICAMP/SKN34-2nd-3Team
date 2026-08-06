from __future__ import annotations

from pathlib import Path

import pytest

from service.recommendation_metric_service import RecommendationMetricService


class RecordingCursor:
    def __init__(self, fail_on: str | None = None) -> None:
        self.executed: list[str] = []
        self.fail_on = fail_on
        self.closed = False

    def execute(self, statement: str) -> None:
        self.executed.append(statement)
        if statement == self.fail_on:
            raise RuntimeError("statement failed")

    def close(self) -> None:
        self.closed = True


class RecordingConnection:
    def __init__(self, cursor: RecordingCursor) -> None:
        self._cursor = cursor
        self.closed = False

    def cursor(self) -> RecordingCursor:
        return self._cursor

    def close(self) -> None:
        self.closed = True


def test_refresh_all_executes_nonempty_v3_statements_in_order_and_closes(tmp_path: Path):
    sql_path = tmp_path / "V3.sql"
    sql_path.write_text(" FIRST ;\n; SECOND; ", encoding="utf-8")
    cursor = RecordingCursor()
    connection = RecordingConnection(cursor)

    RecommendationMetricService(
        connection_factory=lambda: connection, v3_sql_path=sql_path
    ).refresh_all()

    assert cursor.executed == ["FIRST", "SECOND"]
    assert cursor.closed is True
    assert connection.closed is True


def test_refresh_all_closes_cursor_and_connection_when_statement_fails(tmp_path: Path):
    sql_path = tmp_path / "V3.sql"
    sql_path.write_text("FIRST; SECOND", encoding="utf-8")
    cursor = RecordingCursor(fail_on="SECOND")
    connection = RecordingConnection(cursor)

    with pytest.raises(RuntimeError, match="statement failed"):
        RecommendationMetricService(
            connection_factory=lambda: connection, v3_sql_path=sql_path
        ).refresh_all()

    assert cursor.closed is True
    assert connection.closed is True
