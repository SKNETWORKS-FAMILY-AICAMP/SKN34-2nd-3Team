from typing import TYPE_CHECKING

from service.novel_service_errors import (
    CsvFileError,
    CsvSchemaError,
    CollectionApiError,
    CollectionBlockedError,
    CollectionError,
    CollectionHttpError,
    InvalidNovelInputError,
    NovelServiceError,
)

if TYPE_CHECKING:
    from service.collection_service import CollectionService
    from service.novel_service import NovelService


def __getattr__(name: str):
    if name == "CollectionService":
        from service.collection_service import CollectionService

        return CollectionService
    if name == "NovelService":
        from service.novel_service import NovelService

        return NovelService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "NovelService",
    "CollectionService",
    "NovelServiceError",
    "InvalidNovelInputError",
    "CsvFileError",
    "CsvSchemaError",
    "CollectionError",
    "CollectionHttpError",
    "CollectionBlockedError",
    "CollectionApiError",
]
