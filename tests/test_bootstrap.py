from __future__ import annotations

from pathlib import Path

import pytest

import bootstrap


class BootstrapCursor:
    def __init__(self) -> None:
        self.last_query = ""

    def execute(self, query, params=()):
        self.last_query = query

    def fetchone(self):
        return (1,)

    def close(self):
        pass


class BootstrapConnection:
    def __init__(self) -> None:
        self.cursor_instance = BootstrapCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def _table_counts(default: int = 1) -> dict[str, int]:
    return {table: default for table in bootstrap.ALL_HEADERS}


def _source_presence(default: bool = True) -> dict[str, bool]:
    return {table: default for table in bootstrap.ALL_HEADERS}


def test_csv_data_presence_distinguishes_header_only_and_data_rows(tmp_path):
    for table, header in bootstrap.ALL_HEADERS.items():
        rows = [",".join(header)]
        if table != "novel_ai_evaluation":
            rows.append(",".join(["value"] * len(header)))
        (tmp_path / f"{table}.csv").write_text(
            "\n".join(rows) + "\n",
            encoding="utf-8",
        )

    assert bootstrap._csv_data_presence(tmp_path) == {
        table: table != "novel_ai_evaluation"
        for table in bootstrap.ALL_HEADERS
    }


def test_existing_schema_rejects_empty_table_backed_by_nonempty_csv(
    monkeypatch,
    tmp_path,
):
    connection = BootstrapConnection()
    counts = _table_counts()
    counts["novel"] = 0
    source_presence = _source_presence()
    source_presence["novel_ai_evaluation"] = False

    monkeypatch.setattr(bootstrap, "_invalid_dataset_files", lambda _: [])
    monkeypatch.setattr(bootstrap, "_connect", lambda _: connection)
    monkeypatch.setattr(bootstrap, "_database_counts", lambda *_: counts)
    monkeypatch.setattr(
        bootstrap,
        "_csv_data_presence",
        lambda _: source_presence,
    )

    with pytest.raises(
        bootstrap.BootstrapError,
        match=r"novel\.csv has data rows but table novel is empty",
    ):
        bootstrap.initialize_database(
            tmp_path / ".env",
            {"DB_NAME": "test", "DB_PASSWORD": "password"},
            tmp_path,
        )

    assert connection.closed is True


def test_existing_schema_allows_empty_table_only_for_header_only_csv(
    monkeypatch,
    tmp_path,
    capsys,
):
    connection = BootstrapConnection()
    counts = _table_counts()
    counts["novel_ai_evaluation"] = 0
    source_presence = _source_presence()
    source_presence["novel_ai_evaluation"] = False

    monkeypatch.setattr(bootstrap, "_invalid_dataset_files", lambda _: [])
    monkeypatch.setattr(bootstrap, "_connect", lambda _: connection)
    monkeypatch.setattr(bootstrap, "_database_counts", lambda *_: counts)
    monkeypatch.setattr(
        bootstrap,
        "_csv_data_presence",
        lambda _: source_presence,
    )

    bootstrap.initialize_database(
        tmp_path / ".env",
        {"DB_NAME": "test", "DB_PASSWORD": "password"},
        tmp_path,
    )

    output = capsys.readouterr().out

    assert "Core database schema and CSV data already exist" in output
    assert (
        "Database schema, core CSV data, and comment sentiment data are ready"
        in output
    )
    assert connection.closed is True


def test_post_migration_validation_rejects_silent_zero_row_import(
    monkeypatch,
    tmp_path,
):
    connection = BootstrapConnection()
    count_results = iter([{}, _table_counts(default=0)])
    source_presence = _source_presence()
    source_presence["novel_ai_evaluation"] = False
    migrations: list[Path] = []

    monkeypatch.setattr(bootstrap, "_invalid_dataset_files", lambda _: [])
    monkeypatch.setattr(bootstrap, "_connect", lambda _: connection)
    monkeypatch.setattr(
        bootstrap,
        "_database_counts",
        lambda *_: next(count_results),
    )
    monkeypatch.setattr(
        bootstrap,
        "_csv_data_presence",
        lambda _: source_presence,
    )
    monkeypatch.setattr(
        bootstrap,
        "_execute_migration",
        lambda migration, *_: migrations.append(migration),
    )

    with pytest.raises(
        bootstrap.BootstrapError,
        match=r"tag\.csv has data rows but table tag is empty",
    ):
        bootstrap.initialize_database(
            tmp_path / ".env",
            {"DB_NAME": "test", "DB_PASSWORD": "password"},
            tmp_path,
        )

    assert [migration.name for migration in migrations] == [
    "V1__create_initial_schema.sql",
    "V2__load_csv_data.sql",
    "V3__create_recommendation_dashboard.sql",
    "V4__create_paid_conversion_prediction.sql",
    ]


def test_load_data_uses_lf_for_every_csv():
    sql = (bootstrap.MIGRATION_DIR / "V2__load_csv_data.sql").read_text(
        encoding="utf-8"
    )

    load_count = sql.count("LOAD DATA INFILE")
    assert load_count == len(bootstrap.ALL_HEADERS)
    assert sql.count(r"LINES TERMINATED BY '\n'") == load_count
    assert r"LINES TERMINATED BY '\r\n'" not in sql


def test_comment_import_matches_current_comment_csv_shape():
    sql = (bootstrap.MIGRATION_DIR / "V2__load_csv_data.sql").read_text(
        encoding="utf-8"
    )
    comment_sql = sql[sql.index("CREATE TABLE comment_import") :]

    for column in (
        "commenter_nickname",
        "commenter_blog_url",
        "is_novel_author",
        "source_parent_comment_id",
        "crawl_status",
    ):
        assert column in comment_sql
        assert f"imported.{column}" in comment_sql

    assert (
        "@commenter_nickname, @commenter_blog_url, @is_novel_author,\n"
        " @source_parent_comment_id, @crawl_status)"
    ) in comment_sql
