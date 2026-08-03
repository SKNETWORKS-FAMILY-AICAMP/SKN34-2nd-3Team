from typing import TYPE_CHECKING

from service.novel_service_errors import (
    CsvFileError,
    CsvSchemaError,
    InvalidNovelInputError,
    NovelServiceError,
)

if TYPE_CHECKING:
    from service.novel_service import NovelService


def __getattr__(name: str):
    if name == "NovelService":
        from service.novel_service import NovelService

        return NovelService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "NovelService",
    "NovelServiceError",
    "InvalidNovelInputError",
    "CsvFileError",
    "CsvSchemaError",
]
