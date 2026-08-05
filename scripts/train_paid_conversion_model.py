from __future__ import annotations

from pathlib import Path

import mysql.connector
import numpy as np
import pandas as pd
from dotenv import dotenv_values
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


ROOT = Path(__file__).resolve().parents[1]
VIEW_COLUMNS = ["view_5", "view_10", "view_15", "view_20", "view_25"]
NUMERIC_COLUMNS = [
    *VIEW_COLUMNS,
    "preference_count",
    "total_view_count",
    "like_count",
]
CATEGORICAL_COLUMNS = ["genre_id"]


def connect():
    config = dotenv_values(ROOT / ".env")
    return mysql.connector.connect(
        host=config.get("DB_HOST", "127.0.0.1"),
        port=int(config.get("MYSQL_PORT", "3306")),
        user=config.get("DB_USER", "root"),
        password=config.get("DB_PASSWORD", ""),
        database=config.get("DB_NAME"),
        connection_timeout=30,
        autocommit=True,
    )


def fetch_frame(connection, query: str) -> pd.DataFrame:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(query)
        return pd.DataFrame(cursor.fetchall())
    finally:
        cursor.close()


def feature_query(training: bool) -> str:
    paid_join = """
        JOIN episode AS e26
          ON e26.novel_id = n.novel_id
         AND e26.episode_number = 26
         AND e26.view_count IS NOT NULL
        LEFT JOIN episode AS e27
          ON e27.novel_id = n.novel_id
         AND e27.episode_number = 27
    """ if training else ""
    training_filter = """
        AND (
            (
                COALESCE(e26.episode_title, '') NOT LIKE '%공지%'
                AND e26.access_type = 'PAID'
            )
            OR (
                COALESCE(e26.episode_title, '') LIKE '%공지%'
                AND e27.access_type = 'PAID'
                AND e27.view_count IS NOT NULL
            )
        )
    """ if training else ""
    candidate_filter = "" if training else """
        AND n.free = 1
        AND COALESCE(n.paid_serial, 0) = 0
        AND COALESCE(n.finish, 0) = 0
        AND COALESCE(n.pause, 0) = 0
        AND EXISTS (
            SELECT 1
            FROM episode AS e30
            WHERE e30.novel_id = n.novel_id
              AND e30.episode_number >= 30
        )
    """
    target_column = """
        , CASE
            WHEN COALESCE(e26.episode_title, '') LIKE '%공지%' THEN e27.view_count
            ELSE e26.view_count
          END AS paid_view_26
    """ if training else ""
    return f"""
        SELECT
            n.novel_id,
            COALESCE(n.genre_1, 0) AS genre_id,
            COALESCE(e5.view_count, 0) AS view_5,
            COALESCE(e10.view_count, 0) AS view_10,
            COALESCE(e15.view_count, 0) AS view_15,
            COALESCE(e20.view_count, 0) AS view_20,
            e25.view_count AS view_25,
            COALESCE(s.preference_count, 0) AS preference_count,
            COALESCE(s.view_count, 0) AS total_view_count,
            COALESCE(s.like_count, 0) AS like_count
            {target_column}
        FROM novel AS n
        JOIN episode AS e25
          ON e25.novel_id = n.novel_id
         AND e25.episode_number = 25
         AND e25.access_type = 'FREE'
         AND e25.view_count > 0
        {paid_join}
        LEFT JOIN episode AS e5
          ON e5.novel_id = n.novel_id AND e5.episode_number = 5
        LEFT JOIN episode AS e10
          ON e10.novel_id = n.novel_id AND e10.episode_number = 10
        LEFT JOIN episode AS e15
          ON e15.novel_id = n.novel_id AND e15.episode_number = 15
        LEFT JOIN episode AS e20
          ON e20.novel_id = n.novel_id AND e20.episode_number = 20
        LEFT JOIN novel_statistics AS s ON s.novel_id = n.novel_id
        WHERE 1 = 1
        {training_filter}
        {candidate_filter}
    """


def prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame[[*NUMERIC_COLUMNS, *CATEGORICAL_COLUMNS]].copy()
    for column in NUMERIC_COLUMNS:
        result[column] = np.log1p(pd.to_numeric(result[column], errors="coerce").fillna(0))
    result["genre_id"] = result["genre_id"].fillna(0).astype(str)
    return result


def build_model() -> Pipeline:
    transformer = ColumnTransformer(
        [
            ("numeric", "passthrough", NUMERIC_COLUMNS),
            (
                "genre",
                OneHotEncoder(handle_unknown="ignore"),
                CATEGORICAL_COLUMNS,
            ),
        ]
    )
    regressor = RandomForestRegressor(
        n_estimators=300,
        min_samples_leaf=10,
        max_features=0.8,
        random_state=42,
        n_jobs=-1,
    )
    return Pipeline([("features", transformer), ("model", regressor)])


def save_predictions(
    connection,
    candidates: pd.DataFrame,
    conversion_rate: np.ndarray,
    model_mae: float,
    sample_count: int,
) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute("TRUNCATE TABLE novel_paid_conversion_prediction")
        query = """
            INSERT INTO novel_paid_conversion_prediction (
                novel_id,
                predicted_purchase_count,
                predicted_conversion_rate,
                predicted_paid_dropout_rate,
                model_mae,
                training_sample_count,
                trained_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """
        rows = []
        for candidate, rate in zip(candidates.itertuples(index=False), conversion_rate):
            clipped_rate = float(np.clip(rate, 0, 1))
            rows.append(
                (
                    int(candidate.novel_id),
                    int(round(float(candidate.view_25) * clipped_rate)),
                    clipped_rate,
                    1 - clipped_rate,
                    model_mae,
                    sample_count,
                )
            )
        cursor.executemany(query, rows)
    finally:
        cursor.close()


def main() -> None:
    connection = connect()
    try:
        training = fetch_frame(connection, feature_query(training=True))
        candidates = fetch_frame(connection, feature_query(training=False))
        if len(training) < 100:
            raise RuntimeError(f"학습 표본이 부족합니다: {len(training)}건")
        if candidates.empty:
            raise RuntimeError("예측할 무료 작품이 없습니다.")

        target = (
            pd.to_numeric(training["paid_view_26"], errors="coerce")
            / pd.to_numeric(training["view_25"], errors="coerce")
        ).clip(0, 1)
        train_x = prepare_features(training)
        candidate_x = prepare_features(candidates)
        model = build_model()
        folds = KFold(n_splits=5, shuffle=True, random_state=42)
        validation_prediction = cross_val_predict(model, train_x, target, cv=folds)
        model_mae = float(mean_absolute_error(target, validation_prediction))

        model.fit(train_x, target)
        prediction = np.clip(model.predict(candidate_x), 0, 1)
        save_predictions(
            connection,
            candidates,
            prediction,
            model_mae,
            len(training),
        )
        print(
            f"trained={len(training)} candidates={len(candidates)} "
            f"conversion_mae={model_mae:.4f}"
        )
    finally:
        connection.close()


if __name__ == "__main__":
    main()
