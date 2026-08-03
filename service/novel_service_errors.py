class NovelServiceError(Exception):
    """NovelService 공통 예외."""

class InvalidNovelInputError(NovelServiceError):
    """작품 주소 또는 작품 ID 입력 오류."""

class CsvFileError(NovelServiceError):
    """CSV 파일 접근 오류."""

class CsvSchemaError(NovelServiceError):
    """CSV 구조 또는 Entity 변환 오류."""

class CollectionError(NovelServiceError):
    """문피아 공개 데이터 수집 오류."""

class CollectionHttpError(CollectionError):
    """문피아 HTTP 응답 오류."""

class CollectionBlockedError(CollectionHttpError):
    """문피아가 요청을 거부하거나 제한한 오류."""

class CollectionApiError(CollectionError):
    """문피아 API 응답 코드 또는 구조 오류."""
