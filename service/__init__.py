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
    from service.novel_prediction_service import NovelPredictionService 

def __getattr__(name: str):
    if name == "CollectionService":
        from service.collection_service import CollectionService
        return CollectionService
    
    if name == "NovelService":
        from service.novel_service import NovelService
        return NovelService

    if name == "NovelPredictionService":
        from service.novel_prediction_service import NovelPredictionService
        return NovelPredictionService
        
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "NovelService",
    "CollectionService",
    "NovelPredictionService", 
    "NovelServiceError",
    "InvalidNovelInputError",
    "CsvFileError",
    "CsvSchemaError",
    "CollectionError",
    "CollectionHttpError",
    "CollectionBlockedError",
    "CollectionApiError",
]