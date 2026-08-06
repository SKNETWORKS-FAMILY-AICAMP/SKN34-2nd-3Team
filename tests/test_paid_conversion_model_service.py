from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from service.paid_conversion_model_service import PaidConversionModelService


class StubModel:
    def __init__(self) -> None:
        self.fit_args = None

    def fit(self, features, target):
        self.fit_args = (features, target)
        return self

    def predict(self, features):
        return np.full(len(features), 1.2)


class StubConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class RecordingCursor:
    def __init__(self) -> None:
        self.executed = []
        self.rows = None
        self.closed = False

    def execute(self, query):
        self.executed.append(query)

    def executemany(self, query, rows):
        self.rows = rows

    def close(self):
        self.closed = True


def make_training(size: int = 100) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "novel_id": range(size),
            "genre_id": [1] * size,
            "view_5": [10] * size,
            "view_10": [20] * size,
            "view_15": [30] * size,
            "view_20": [40] * size,
            "view_25": [50] * size,
            "preference_count": [5] * size,
            "total_view_count": [100] * size,
            "like_count": [3] * size,
            "paid_view_26": [25] * size,
        }
    )


def test_train_and_predict_all_preserves_target_clipping_and_returns_summary(monkeypatch):
    connection = StubConnection()
    model = StubModel()
    training = make_training()
    candidates = training.drop(columns="paid_view_26").iloc[:2].copy()
    saved = {}
    frames = iter([training, candidates])
    service = PaidConversionModelService(
        connection_factory=lambda: connection,
        model_factory=lambda: model,
        validation_predictor=lambda estimator, features, target, cv: np.full(len(target), 0.4),
    )
    monkeypatch.setattr(service, "fetch_frame", lambda connection, query: next(frames))
    monkeypatch.setattr(
        service,
        "save_predictions",
        lambda connection, candidates, rates, model_mae, sample_count: saved.update(
            rates=rates, model_mae=model_mae, sample_count=sample_count
        ),
    )

    result = service.train_and_predict_all()

    assert result.trained_count == 100
    assert result.candidate_count == 2
    assert result.model_mae == pytest.approx(0.1)
    assert saved["rates"].tolist() == [1.0, 1.0]
    assert saved["sample_count"] == 100
    assert connection.closed is True


@pytest.mark.parametrize(
    ("training", "candidates", "message"),
    [
        (make_training(99), make_training(1).drop(columns="paid_view_26"), "학습 표본이 부족합니다: 99건"),
        (make_training(), make_training(0).drop(columns="paid_view_26"), "예측할 무료 작품이 없습니다."),
    ],
)
def test_train_and_predict_all_preserves_validation_errors(monkeypatch, training, candidates, message):
    connection = StubConnection()
    frames = iter([training, candidates])
    service = PaidConversionModelService(connection_factory=lambda: connection)
    monkeypatch.setattr(service, "fetch_frame", lambda connection, query: next(frames))

    with pytest.raises(RuntimeError, match=message):
        service.train_and_predict_all()

    assert connection.closed is True


def test_feature_query_keeps_training_and_candidate_contracts():
    service = PaidConversionModelService(connection_factory=lambda: None)

    training_query = service.feature_query(training=True)
    candidate_query = service.feature_query(training=False)

    assert "AS paid_view_26" in training_query
    assert "e26.access_type = 'PAID'" in training_query
    assert "n.free = 1" not in training_query
    assert "AS paid_view_26" not in candidate_query
    assert "n.free = 1" in candidate_query
    assert "e30.episode_number >= 30" in candidate_query


def test_save_predictions_preserves_clipping_purchase_and_dropout_semantics():
    cursor = RecordingCursor()
    connection = type("Connection", (), {"cursor": lambda self: cursor})()
    candidates = pd.DataFrame({"novel_id": [10, 20], "view_25": [101, 50]})

    PaidConversionModelService.save_predictions(
        connection, candidates, np.array([-0.2, 1.4]), model_mae=0.3, sample_count=100
    )

    assert cursor.executed == ["TRUNCATE TABLE novel_paid_conversion_prediction"]
    assert cursor.rows == [
        (10, 0, 0.0, 1.0, 0.3, 100),
        (20, 50, 1.0, 0.0, 0.3, 100),
    ]
    assert cursor.closed is True
