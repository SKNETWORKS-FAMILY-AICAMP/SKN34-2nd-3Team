from __future__ import annotations

import threading

from repository.repository import Repository


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def is_connected(self) -> bool:
        return not self.closed

    def close(self) -> None:
        self.closed = True


def test_repository_connects_with_pure_python_driver(monkeypatch):
    repository = Repository()
    repository.close()
    connect_kwargs: dict[str, object] = {}

    def fake_connect(**kwargs) -> FakeConnection:
        connect_kwargs.update(kwargs)
        return FakeConnection()

    monkeypatch.setattr("repository.repository.mysql.connector.connect", fake_connect)

    repository.get_connection()

    assert connect_kwargs["use_pure"] is True


def test_repository_reuses_connection_per_thread_without_sharing(monkeypatch):
    repository = Repository()
    repository.close()
    created: list[FakeConnection] = []

    def fake_connect(**_kwargs) -> FakeConnection:
        connection = FakeConnection()
        created.append(connection)
        return connection

    monkeypatch.setattr("repository.repository.mysql.connector.connect", fake_connect)
    first_thread_ready = threading.Event()
    second_thread_finished = threading.Event()
    results: dict[str, tuple[FakeConnection, FakeConnection]] = {}

    def first_worker() -> None:
        first = repository.get_connection()
        first_thread_ready.set()
        second_thread_finished.wait(timeout=5)
        results["first"] = (first, repository.get_connection())

    def second_worker() -> None:
        first_thread_ready.wait(timeout=5)
        results["second"] = (
            repository.get_connection(),
            repository.get_connection(),
        )
        second_thread_finished.set()

    threads = [
        threading.Thread(target=first_worker),
        threading.Thread(target=second_worker),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert results["first"][0] is results["first"][1]
    assert results["second"][0] is results["second"][1]
    assert results["first"][0] is not results["second"][0]
    assert len(created) == 2


def test_close_only_closes_and_clears_current_thread_connection(monkeypatch):
    repository = Repository()
    repository.close()
    created: list[FakeConnection] = []

    def fake_connect(**_kwargs) -> FakeConnection:
        connection = FakeConnection()
        created.append(connection)
        return connection

    monkeypatch.setattr("repository.repository.mysql.connector.connect", fake_connect)
    worker_ready = threading.Event()
    main_closed = threading.Event()
    worker_connection: list[FakeConnection] = []

    def worker() -> None:
        connection = repository.get_connection()
        worker_connection.append(connection)
        worker_ready.set()
        main_closed.wait(timeout=5)
        assert repository.get_connection() is connection

    thread = threading.Thread(target=worker)
    thread.start()
    worker_ready.wait(timeout=5)
    main_connection = repository.get_connection()
    repository.close()
    main_closed.set()
    thread.join(timeout=5)
    assert not thread.is_alive()

    assert main_connection.closed is True
    assert worker_connection[0].closed is False
    assert repository.get_connection() is not main_connection
