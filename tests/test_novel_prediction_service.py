from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from service.novel_prediction_service import NovelPredictionService


class StubRepository:
    def __init__(self, genre_name: str | None) -> None:
        self.genre_name = genre_name

    def get_novel(self, novel_id: int):
        return SimpleNamespace(adult=False, exclusive=False, contest=False)

    def get_episodes(self, novel_id: int):
        return [SimpleNamespace(
            episode_number=10,
            page_count=20,
            view_count=300,
            like_count=40,
            comment_count=5,
        )]

    def get_primary_genre_name(self, novel_id: int):
        return self.genre_name


class RecordingScaler:
    feature_names_in_ = np.array([
        "episode_number_free",
        "page_count_free",
        "view_count_free",
        "like_count_free",
        "comment_count_free",
        "genre_best_name_현대판타지",
        "genre_best_name_other_genre",
    ])

    def __init__(self) -> None:
        self.input_df = None

    def transform(self, input_df):
        self.input_df = input_df.copy()
        return input_df


class StubModel:
    def predict(self, input_scaled):
        return [0.25]


@pytest.mark.parametrize(
    ("genre_name", "expected_column"),
    [
        ("현대판타지", "genre_best_name_현대판타지"),
        ("미지원장르", "genre_best_name_other_genre"),
        (None, "genre_best_name_other_genre"),
    ],
)
def test_ml_prediction_sets_genre_one_hot_or_fallback(
    monkeypatch, genre_name, expected_column
):
    scaler = RecordingScaler()
    loaded = iter([StubModel(), scaler])
    monkeypatch.setattr("service.novel_prediction_service.os.path.exists", lambda path: True)
    monkeypatch.setattr(
        "service.novel_prediction_service.joblib.load", lambda path: next(loaded)
    )
    service = NovelPredictionService(StubRepository(genre_name))

    prediction = service._predict_drop_rate_with_ml(7)

    assert prediction == 25.0
    assert scaler.input_df.at[0, expected_column] == 1.0
    genre_columns = [
        column for column in scaler.input_df.columns
        if column.startswith("genre_best_name_")
    ]
    assert scaler.input_df[genre_columns].sum(axis=1).iloc[0] == 1.0
