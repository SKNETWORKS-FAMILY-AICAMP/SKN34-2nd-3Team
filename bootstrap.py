from __future__ import annotations

import csv
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Mapping, Sequence

import mysql.connector
from dotenv import dotenv_values, load_dotenv
from huggingface_hub import HfApi, snapshot_download

from clawler.munpia_crawler import ALL_HEADERS


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "db" / "data"
ENV_FILE = ROOT / ".env"
COMPOSE_FILE = ROOT / "docker-compose.yml"
MIGRATION_DIR = ROOT / "db" / "migration"

DATASET_REPO_ID = "SKN34/SKN34-2nd-3Team"
DATASET_REPO_TYPE = "dataset"
DATASET_REVISION_FILE = ".hf_dataset_revision"
MYSQL_SERVICE = "mysql"
MYSQL_LOCK_NAME = "skn34_bootstrap_database"

_DATASET_LOCK = threading.Lock()


class BootstrapError(RuntimeError):
    """Raised when application prerequisites cannot be prepared safely."""


def _required_csv_files() -> list[str]:
    return [f"{table}.csv" for table in ALL_HEADERS]


def _invalid_dataset_files(data_dir: Path) -> list[str]:
    invalid_files: list[str] = []
    for table, expected_header in ALL_HEADERS.items():
        filename = f"{table}.csv"
        path = data_dir / filename
        try:
            if not path.is_file() or path.stat().st_size == 0:
                invalid_files.append(filename)
                continue
            with path.open("r", encoding="utf-8-sig", newline="") as file:
                header = next(csv.reader(file), None)
            if header != expected_header:
                invalid_files.append(filename)
        except (OSError, UnicodeError, csv.Error):
            invalid_files.append(filename)
    return invalid_files


def _read_revision(data_dir: Path) -> str | None:
    try:
        revision = (data_dir / DATASET_REVISION_FILE).read_text(
            encoding="utf-8"
        ).strip()
    except OSError:
        return None
    return revision or None


def _latest_dataset_revision() -> str:
    try:
        info = HfApi().dataset_info(DATASET_REPO_ID, revision="main")
    except Exception as error:
        raise BootstrapError(
            f"failed to check the latest Hugging Face dataset revision: {error}"
        ) from error
    if not info.sha:
        raise BootstrapError("Hugging Face returned an empty dataset revision")
    return info.sha


def download_dataset(data_dir: str | Path | None = None) -> str:
    """Validate and update the canonical CSV dataset.

    The repository's default data directory is checked against the remote
    Hugging Face revision. Explicit alternate directories are treated as
    fixtures/offline mirrors and receive integrity repair only.
    """

    resolved_data_dir = Path(DATA_DIR if data_dir is None else data_dir).resolve()
    verify_remote_revision = resolved_data_dir == DATA_DIR.resolve()

    with _DATASET_LOCK:
        load_dotenv(ENV_FILE)
        invalid_files = _invalid_dataset_files(resolved_data_dir)
        latest_revision: str | None = None
        local_revision = _read_revision(resolved_data_dir)

        if verify_remote_revision:
            latest_revision = _latest_dataset_revision()

        revision_changed = (
            latest_revision is not None and local_revision != latest_revision
        )
        if not invalid_files and not revision_changed:
            print(f"Dataset is current: {resolved_data_dir}")
            return str(resolved_data_dir)

        requested_files = (
            _required_csv_files() if revision_changed else invalid_files
        )
        resolved_data_dir.mkdir(parents=True, exist_ok=True)

        kwargs = {
            "repo_id": DATASET_REPO_ID,
            "repo_type": DATASET_REPO_TYPE,
            "local_dir": str(resolved_data_dir),
            "allow_patterns": requested_files,
            "force_download": revision_changed,
        }
        if latest_revision is not None:
            kwargs["revision"] = latest_revision

        try:
            snapshot_download(**kwargs)
        except Exception as error:
            raise BootstrapError(
                f"Hugging Face dataset download failed: {error}"
            ) from error

        remaining_invalid_files = _invalid_dataset_files(resolved_data_dir)
        if remaining_invalid_files:
            filenames = ", ".join(remaining_invalid_files)
            raise BootstrapError(
                "Dataset recovery failed; remaining invalid CSV files: "
                f"{filenames}"
            )

        if latest_revision is not None:
            try:
                (resolved_data_dir / DATASET_REVISION_FILE).write_text(
                    f"{latest_revision}\n", encoding="utf-8"
                )
            except OSError as error:
                raise BootstrapError(
                    f"failed to save dataset revision: {error}"
                ) from error

        print(
            f"Dataset ready: {resolved_data_dir} "
            f"({len(requested_files)} CSV files checked/downloaded)"
        )
        return str(resolved_data_dir)


def _load_environment(env_file: Path) -> dict[str, str]:
    if not env_file.is_file():
        raise BootstrapError(f"environment file not found: {env_file}")

    values = {
        key: str(value)
        for key, value in dotenv_values(env_file).items()
        if value is not None
    }
    missing = [key for key in ("DB_PASSWORD", "DB_NAME") if not values.get(key)]
    if missing:
        raise BootstrapError(
            f"missing required environment values: {', '.join(missing)}"
        )

    values.setdefault("DB_HOST", "127.0.0.1")
    values.setdefault("DB_USER", "root")
    values.setdefault("MYSQL_PORT", "3306")
    try:
        port = int(values["MYSQL_PORT"])
    except ValueError as error:
        raise BootstrapError("MYSQL_PORT must be an integer") from error
    if not 1 <= port <= 65535:
        raise BootstrapError("MYSQL_PORT must be between 1 and 65535")
    return values


def _runtime_environment(
    env_file: Path,
    env: Mapping[str, str],
    data_dir: Path | None = None,
) -> dict[str, str]:
    runtime = os.environ.copy()
    runtime.update(env)
    runtime["BOOTSTRAP_ENV_FILE"] = str(env_file.resolve())
    if data_dir is not None:
        runtime["DB_DATA_DIR"] = str(data_dir.resolve())
    return runtime


def _run(
    command: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=True,
            input=input_text,
            env=None if env is None else dict(env),
        )
    except FileNotFoundError as error:
        raise BootstrapError(f"command not found: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "unknown command error").strip()
        raise BootstrapError(f"command failed: {detail}") from error


def _compose_command(env_file: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        str(env_file.resolve()),
        "-f",
        str(COMPOSE_FILE),
    ]


def start_mysql(env_file: Path, env: Mapping[str, str]) -> str:
    if shutil.which("docker") is None:
        raise BootstrapError("Docker CLI is not installed or not on PATH")
    if not COMPOSE_FILE.is_file():
        raise BootstrapError(f"Docker Compose file not found: {COMPOSE_FILE}")

    runtime = _runtime_environment(env_file, env)
    compose = _compose_command(env_file)
    _run([*compose, "up", "-d", MYSQL_SERVICE], env=runtime)
    result = _run([*compose, "ps", "-q", MYSQL_SERVICE], env=runtime)
    container_id = result.stdout.strip()
    if not container_id:
        raise BootstrapError("MySQL container did not start")
    return container_id


def wait_for_mysql(
    container_id: str,
    env: Mapping[str, str],
    timeout: float = 120,
) -> None:
    deadline = time.monotonic() + timeout
    while True:
        result = _run(
            [
                "docker",
                "inspect",
                "--format",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
                container_id,
            ],
            env=_runtime_environment(ENV_FILE, env),
        )
        status = result.stdout.strip().lower()
        if status in {"healthy", "running"}:
            return
        if status in {"dead", "exited"}:
            raise BootstrapError(f"MySQL container stopped with status: {status}")
        if time.monotonic() >= deadline:
            raise BootstrapError(
                f"MySQL did not become healthy within {timeout:g} seconds "
                f"(last status: {status or 'unknown'})"
            )
        time.sleep(1)


def _connect(env: Mapping[str, str]):
    try:
        return mysql.connector.connect(
            host=env.get("DB_HOST", "127.0.0.1"),
            port=int(env.get("MYSQL_PORT", "3306")),
            user=env.get("DB_USER", "root"),
            password=env["DB_PASSWORD"],
            database=env["DB_NAME"],
            connection_timeout=10,
            autocommit=True,
        )
    except mysql.connector.Error as error:
        raise BootstrapError(f"failed to connect to MySQL: {error}") from error


def _database_counts(connection, database: str) -> dict[str, int]:
    expected_tables = tuple(ALL_HEADERS)
    placeholders = ",".join(["%s"] * len(expected_tables))
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT table_name, table_rows FROM information_schema.tables "
            f"WHERE table_schema = %s AND table_name IN ({placeholders})",
            (database, *expected_tables),
        )
        return {str(table): int(rows or 0) for table, rows in cursor.fetchall()}
    finally:
        close = getattr(cursor, "close", None)
        if close is not None:
            close()


def _execute_migration(
    migration: Path,
    env_file: Path,
    env: Mapping[str, str],
    data_dir: Path,
) -> None:
    if not migration.is_file():
        raise BootstrapError(f"migration file not found: {migration}")
    try:
        sql = migration.read_text(encoding="utf-8")
    except OSError as error:
        raise BootstrapError(f"failed to read migration {migration}: {error}") from error

    runtime = _runtime_environment(env_file, env, data_dir)
    runtime["MYSQL_PWD"] = env["DB_PASSWORD"]
    command = [
        *_compose_command(env_file),
        "exec",
        "-T",
        "-e",
        "MYSQL_PWD",
        MYSQL_SERVICE,
        "mysql",
        "--default-character-set=utf8mb4",
        "--show-warnings",
        "-u",
        env.get("DB_USER", "root"),
        env["DB_NAME"],
    ]
    _run(command, env=runtime, input_text=sql)


def initialize_database(
    env_file: Path,
    env: Mapping[str, str],
    data_dir: Path,
) -> None:
    invalid_files = _invalid_dataset_files(data_dir)
    if invalid_files:
        raise BootstrapError(
            "database initialization requires valid CSV files: "
            + ", ".join(invalid_files)
        )

    connection = _connect(env)
    cursor = connection.cursor()
    lock_acquired = False
    try:
        cursor.execute("SELECT GET_LOCK(%s, %s)", (MYSQL_LOCK_NAME, 60))
        lock_acquired = bool(cursor.fetchone()[0])
        if not lock_acquired:
            raise BootstrapError("could not acquire the database bootstrap lock")

        counts = _database_counts(connection, env["DB_NAME"])
        expected_tables = set(ALL_HEADERS)
        existing_tables = set(counts)

        if existing_tables == expected_tables:
            print("Database schema already exists; migrations skipped")
            return
        if existing_tables:
            missing = sorted(expected_tables - existing_tables)
            raise BootstrapError(
                "database is partially initialized; refusing automatic migration. "
                f"Missing tables: {', '.join(missing)}"
            )

        _execute_migration(
            MIGRATION_DIR / "V1__create_initial_schema.sql",
            env_file,
            env,
            data_dir,
        )
        _execute_migration(
            MIGRATION_DIR / "V2__load_csv_data.sql",
            env_file,
            env,
            data_dir,
        )
        _execute_migration(
            MIGRATION_DIR / "V3__create_recommendation_dashboard.sql",
            env_file,
            env,
            data_dir,
        )

        loaded_tables = set(_database_counts(connection, env["DB_NAME"]))
        if loaded_tables != expected_tables:
            missing = sorted(expected_tables - loaded_tables)
            raise BootstrapError(
                "database migrations completed without all expected tables: "
                + ", ".join(missing)
            )
        print("Database schema and CSV data are ready")
    finally:
        if lock_acquired:
            try:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (MYSQL_LOCK_NAME,))
                cursor.fetchone()
            except Exception:
                pass
        close_cursor = getattr(cursor, "close", None)
        if close_cursor is not None:
            close_cursor()
        connection.close()


def prepare_application(
    env_file: str | Path = ENV_FILE,
    data_dir: str | Path = DATA_DIR,
    mysql_timeout: float = 120,
) -> None:
    resolved_env_file = Path(env_file).resolve()
    resolved_data_dir = Path(data_dir).resolve()
    env = _load_environment(resolved_env_file)
    env["DB_DATA_DIR"] = str(resolved_data_dir)

    download_dataset(resolved_data_dir)
    container_id = start_mysql(resolved_env_file, env)
    wait_for_mysql(container_id, env, mysql_timeout)
    initialize_database(resolved_env_file, env, resolved_data_dir)


def run() -> None:
    prepare_application()


if __name__ == "__main__":
    run()
