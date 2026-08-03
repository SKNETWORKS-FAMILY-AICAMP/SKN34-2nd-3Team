class NovelServiceError(Exception):
    """NovelService 공통 예외."""

class InvalidNovelInputError(NovelServiceError):
    """작품 주소 또는 작품 ID 입력 오류."""

class CsvFileError(NovelServiceError):
    """CSV 파일 접근 오류."""

class CsvSchemaError(NovelServiceError):
    """CSV 구조 또는 Entity 변환 오류."""