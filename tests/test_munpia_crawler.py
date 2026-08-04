from clawler.munpia_crawler import (
    ALL_HEADERS,
    MunpiaAsyncCrawler,
    SINGLE_NOVEL_EPISODE_CONCURRENCY,
)


def test_erd_tables_exist():
    assert {"novel", "novel_author", "novel_statistics", "episode", "comment"} <= set(ALL_HEADERS)


def test_episode_concurrency_enabled():
    assert SINGLE_NOVEL_EPISODE_CONCURRENCY >= 2


def test_async_adapter_contract():
    assert hasattr(MunpiaAsyncCrawler, "process_single_work")
