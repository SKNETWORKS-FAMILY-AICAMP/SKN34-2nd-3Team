from typing import TYPE_CHECKING

from service.novel_service_errors import (
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
    from service.paid_conversion_model_service import PaidConversionModelService
    from service.recommendation_metric_service import RecommendationMetricService
    from service.recommendation_service import RecommendationService

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

    if name == "RecommendationService":
        from service.recommendation_service import RecommendationService
        return RecommendationService

    if name == "RecommendationMetricService":
        from service.recommendation_metric_service import RecommendationMetricService
        return RecommendationMetricService

    if name == "PaidConversionModelService":
        from service.paid_conversion_model_service import PaidConversionModelService
        return PaidConversionModelService
        
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "NovelService",
    "CollectionService",
    "NovelPredictionService", 
    "RecommendationService",
    "RecommendationMetricService",
    "PaidConversionModelService",
    "NovelServiceError",
    "InvalidNovelInputError",
    "CollectionError",
    "CollectionHttpError",
    "CollectionBlockedError",
    "CollectionApiError",
]
