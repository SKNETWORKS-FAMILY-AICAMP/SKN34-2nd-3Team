from __future__ import annotations

import random
import time
from copy import deepcopy
from pathlib import Path

import mysql.connector
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import torch
from dotenv import dotenv_values
from sklearn.ensemble import (
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from matplotlib.ticker import PercentFormatter
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from xgboost import XGBRegressor


OUTPUT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = OUTPUT_DIR.parent


SEED = 42
TEST_SIZE = 0.20
VALID_SIZE = 0.20
MAX_EPOCHS = 120
PATIENCE = 12
BATCH_SIZE = 128


def connect():
    config = dotenv_values(PROJECT_ROOT / ".env")
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


def training_feature_query() -> str:
    return """
        SELECT n.novel_id, COALESCE(n.genre_1, 0) AS genre_id,
               COALESCE(e5.view_count, 0) AS view_5,
               COALESCE(e10.view_count, 0) AS view_10,
               COALESCE(e15.view_count, 0) AS view_15,
               COALESCE(e20.view_count, 0) AS view_20,
               e25.view_count AS view_25,
               COALESCE(s.preference_count, 0) AS preference_count,
               COALESCE(s.view_count, 0) AS total_view_count,
               COALESCE(s.like_count, 0) AS like_count,
               CASE WHEN COALESCE(e26.episode_title, '') LIKE '%공지%'
                    THEN e27.view_count ELSE e26.view_count END AS paid_view_26
        FROM novel AS n
        JOIN episode AS e25 ON e25.novel_id = n.novel_id
             AND e25.episode_number = 25 AND e25.access_type = 'FREE'
             AND e25.view_count > 0
        JOIN episode AS e26 ON e26.novel_id = n.novel_id
             AND e26.episode_number = 26 AND e26.view_count IS NOT NULL
        LEFT JOIN episode AS e27 ON e27.novel_id = n.novel_id
             AND e27.episode_number = 27
        LEFT JOIN episode AS e5 ON e5.novel_id = n.novel_id AND e5.episode_number = 5
        LEFT JOIN episode AS e10 ON e10.novel_id = n.novel_id AND e10.episode_number = 10
        LEFT JOIN episode AS e15 ON e15.novel_id = n.novel_id AND e15.episode_number = 15
        LEFT JOIN episode AS e20 ON e20.novel_id = n.novel_id AND e20.episode_number = 20
        LEFT JOIN novel_statistics AS s ON s.novel_id = n.novel_id
        WHERE (COALESCE(e26.episode_title, '') NOT LIKE '%공지%'
               AND e26.access_type = 'PAID')
           OR (COALESCE(e26.episode_title, '') LIKE '%공지%'
               AND e27.access_type = 'PAID' AND e27.view_count IS NOT NULL)
    """


def set_seed() -> None:
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)


def load_training_data() -> tuple[pd.DataFrame, pd.Series]:
    connection = connect()
    try:
        frame = fetch_frame(connection, training_feature_query())
    finally:
        connection.close()

    target = (
        pd.to_numeric(frame["paid_view_26"], errors="coerce")
        / pd.to_numeric(frame["view_25"], errors="coerce")
    ).clip(0, 1)
    numeric_columns = [
        "view_5",
        "view_10",
        "view_15",
        "view_20",
        "view_25",
        "preference_count",
        "total_view_count",
        "like_count",
    ]
    features = frame[["novel_id", "genre_id", *numeric_columns]].copy()
    for column in numeric_columns:
        features[column] = np.log1p(
            pd.to_numeric(features[column], errors="coerce").fillna(0)
        )
    genre = pd.get_dummies(
        features.pop("genre_id").fillna(0).astype(str),
        prefix="genre",
        dtype=float,
    )
    features = pd.concat([features, genre], axis=1)
    return features, target


def metrics(name: str, family: str, true: np.ndarray, predicted: np.ndarray, seconds: float) -> dict:
    clipped = np.clip(predicted, 0, 1)
    error = np.abs(true - clipped)
    return {
        "model": name,
        "family": family,
        "mae": float(mean_absolute_error(true, clipped)),
        "rmse": float(np.sqrt(mean_squared_error(true, clipped))),
        "r2": float(r2_score(true, clipped)),
        "within_5pp_accuracy": float(np.mean(error <= 0.05)),
        "training_seconds": round(seconds, 3),
    }


class ConversionMLP(nn.Module):
    def __init__(self, input_dim: int, activation: str) -> None:
        super().__init__()
        activation_layers = {
            "SiLU": nn.SiLU,
            "ReLU": nn.ReLU,
            "LeakyReLU": lambda: nn.LeakyReLU(0.01),
            "GELU": nn.GELU,
        }
        activation_factory = activation_layers[activation]
        self.network = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.BatchNorm1d(128),
            activation_factory(),
            nn.Dropout(0.25),
            nn.Linear(128, 64),
            nn.BatchNorm1d(64),
            activation_factory(),
            nn.Dropout(0.20),
            nn.Linear(64, 32),
            activation_factory(),
            nn.Linear(32, 1),
            nn.Sigmoid(),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.network(inputs)


def train_deep_model(
    activation: str,
    train_x: np.ndarray,
    train_y: np.ndarray,
    valid_x: np.ndarray,
    valid_y: np.ndarray,
) -> tuple[ConversionMLP, int]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = ConversionMLP(train_x.shape[1], activation).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=1e-4)
    criterion = nn.MSELoss()
    loader = DataLoader(
        TensorDataset(
            torch.tensor(train_x, dtype=torch.float32),
            torch.tensor(train_y[:, None], dtype=torch.float32),
        ),
        batch_size=BATCH_SIZE,
        shuffle=True,
    )
    valid_inputs = torch.tensor(valid_x, dtype=torch.float32, device=device)
    valid_targets = torch.tensor(valid_y[:, None], dtype=torch.float32, device=device)
    best_loss = float("inf")
    best_state = None
    stale_epochs = 0

    for epoch in range(1, MAX_EPOCHS + 1):
        model.train()
        for inputs, targets in loader:
            inputs = inputs.to(device)
            targets = targets.to(device)
            optimizer.zero_grad()
            loss = criterion(model(inputs), targets)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

        model.eval()
        with torch.no_grad():
            valid_loss = criterion(model(valid_inputs), valid_targets).item()
        if valid_loss < best_loss - 1e-6:
            best_loss = valid_loss
            best_state = deepcopy(model.state_dict())
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= PATIENCE:
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    return model, epoch


def predict_deep(model: ConversionMLP, features: np.ndarray) -> np.ndarray:
    device = next(model.parameters()).device
    model.eval()
    with torch.no_grad():
        inputs = torch.tensor(features, dtype=torch.float32, device=device)
        return model(inputs).cpu().numpy().ravel()


def train_and_compare() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    set_seed()
    features, target = load_training_data()
    novel_ids = features.pop("novel_id").astype(int)
    indices = np.arange(len(features))
    train_valid_idx, test_idx = train_test_split(
        indices,
        test_size=TEST_SIZE,
        random_state=SEED,
    )
    train_idx, valid_idx = train_test_split(
        train_valid_idx,
        test_size=VALID_SIZE,
        random_state=SEED,
    )

    scaler = StandardScaler()
    train_x = scaler.fit_transform(features.iloc[train_idx])
    valid_x = scaler.transform(features.iloc[valid_idx])
    test_x = scaler.transform(features.iloc[test_idx])
    train_y = target.iloc[train_idx].to_numpy(dtype=float)
    valid_y = target.iloc[valid_idx].to_numpy(dtype=float)
    test_y = target.iloc[test_idx].to_numpy(dtype=float)

    machine_models = {
        "Random Forest": RandomForestRegressor(
            n_estimators=300,
            min_samples_leaf=10,
            max_features=0.8,
            random_state=SEED,
            n_jobs=-1,
        ),
        "XGBoost": XGBRegressor(
            n_estimators=500,
            learning_rate=0.03,
            max_depth=5,
            subsample=0.85,
            colsample_bytree=0.85,
            objective="reg:squarederror",
            random_state=SEED,
            n_jobs=-1,
        ),
        "Gradient Boosting": GradientBoostingRegressor(
            n_estimators=300,
            learning_rate=0.03,
            max_depth=3,
            min_samples_leaf=10,
            random_state=SEED,
        ),
        "Extra Trees": ExtraTreesRegressor(
            n_estimators=300,
            min_samples_leaf=10,
            max_features=0.8,
            random_state=SEED,
            n_jobs=-1,
        ),
    }

    comparison = []
    predictions = pd.DataFrame(
        {
            "novel_id": novel_ids.iloc[test_idx].to_numpy(),
            "actual_conversion_rate": test_y,
        }
    )
    for name, model in machine_models.items():
        started = time.perf_counter()
        model.fit(train_x, train_y)
        predicted = np.clip(model.predict(test_x), 0, 1)
        elapsed = time.perf_counter() - started
        comparison.append(metrics(name, "machine_learning", test_y, predicted, elapsed))
        predictions[name] = predicted
        print(f"{name}: MAE={comparison[-1]['mae']:.4f}")

    for activation in ("SiLU", "ReLU", "LeakyReLU", "GELU"):
        name = f"MLP {activation}"
        set_seed()
        started = time.perf_counter()
        model, epochs = train_deep_model(
            activation,
            train_x,
            train_y,
            valid_x,
            valid_y,
        )
        predicted = np.clip(predict_deep(model, test_x), 0, 1)
        elapsed = time.perf_counter() - started
        result = metrics(name, "deep_learning", test_y, predicted, elapsed)
        result["epochs"] = epochs
        comparison.append(result)
        predictions[name] = predicted
        print(f"{name}: MAE={result['mae']:.4f} epochs={epochs}")

    comparison_frame = pd.DataFrame(comparison).sort_values("mae").reset_index(drop=True)
    comparison_frame.insert(0, "rank", np.arange(1, len(comparison_frame) + 1))
    best = comparison_frame.iloc[0].to_dict()

    summary = {
        "best_model": best,
        "feature_columns": list(features.columns),
        "selection_metric": "lowest test MAE",
        "training_samples": int(len(train_idx)),
        "validation_samples": int(len(valid_idx)),
        "test_samples": int(len(test_idx)),
        "total_samples": int(len(features)),
        "target": "first paid episode purchases / episode 25 free views",
        "notice_rule": "if episode 26 title contains 공지, use paid episode 27",
        "random_seed": SEED,
        "torch_device": "cuda" if torch.cuda.is_available() else "cpu",
    }
    return comparison_frame, predictions, summary


def comparison_table(comparison: pd.DataFrame) -> pd.DataFrame:
    table = comparison.sort_values("rank").copy()
    table["MAE (%p)"] = (table["mae"] * 100).round(2)
    table["RMSE (%p)"] = (table["rmse"] * 100).round(2)
    table["R2"] = table["r2"].round(4)
    table["±5%p 적중률 (%)"] = (table["within_5pp_accuracy"] * 100).round(1)
    return table[["rank", "model", "family", "MAE (%p)", "RMSE (%p)",
                  "R2", "±5%p 적중률 (%)", "training_seconds"]]


def _chart_style() -> None:
    sns.set_theme(style="whitegrid")
    plt.rc("font", family="Malgun Gothic")
    plt.rcParams["axes.unicode_minus"] = False


def plot_model_ranking(comparison: pd.DataFrame) -> None:
    _chart_style()
    frame = comparison.sort_values("mae", ascending=False)
    colors = frame["family"].map(
        {"machine_learning": "#19A974", "deep_learning": "#6C63FF"}
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(frame["model"], frame["mae"], color=colors)
    for index, value in enumerate(frame["mae"]):
        ax.text(value + frame["mae"].max() * 0.012, index, f"{value:.4f}", va="center")
    ax.set(title="전체 모델 MAE 순위", xlabel="MAE (낮을수록 좋음)", ylabel="")
    ax.set_xlim(0, frame["mae"].max() * 1.16)
    plt.show()


def plot_best_prediction(
    comparison: pd.DataFrame, predictions: pd.DataFrame
) -> None:
    _chart_style()
    best = comparison.sort_values("mae").iloc[0]
    actual = predictions["actual_conversion_rate"].to_numpy()
    predicted = predictions[best["model"]].to_numpy()
    slope, intercept = np.polyfit(actual, predicted, 1)
    line = np.linspace(0, max(actual.max(), predicted.max()), 200)
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.scatter(actual, predicted, s=20, alpha=0.28, color="#6C63FF", edgecolors="none")
    ax.plot(line, line, "--", color="#98A2B3", label="이상적인 예측")
    ax.plot(line, slope * line + intercept, color="#F79009", linewidth=2.5,
            label=f"추세선 (기울기={slope:.2f})")
    ax.set(title=f"{best['model']}: 실제값과 예측값 | MAE={best['mae']:.4f}",
           xlabel="실제 전환율", ylabel="예측 전환율")
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.legend()
    plt.show()


def plot_family_errors(
    comparison: pd.DataFrame, predictions: pd.DataFrame, family: str
) -> None:
    _chart_style()
    models = comparison.loc[comparison["family"] == family, "model"].tolist()
    frame = pd.DataFrame(
        {model: predictions[model] - predictions["actual_conversion_rate"] for model in models}
    ).melt(var_name="모델", value_name="예측 오차")
    title = "머신러닝" if family == "machine_learning" else "딥러닝"
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.boxplot(data=frame, x="예측 오차", y="모델", hue="모델",
                palette="Set2", showfliers=False, legend=False, ax=ax)
    ax.axvline(0, color="#667085", linestyle="--")
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax.set(title=f"{title} 모델별 예측 오차 분포", ylabel="")
    plt.show()


def plot_conversion_bands(
    comparison: pd.DataFrame, predictions: pd.DataFrame
) -> None:
    _chart_style()
    best_model = comparison.sort_values("mae").iloc[0]["model"]
    labels = ["낮음 (<10%)", "보통 (10~20%)", "높음 (20~35%)", "매우 높음 (35% 이상)"]
    edges = [-np.inf, 0.10, 0.20, 0.35, np.inf]
    actual = pd.cut(predictions["actual_conversion_rate"], edges, labels=labels)
    predicted = pd.cut(predictions[best_model], edges, labels=labels)
    matrix = pd.crosstab(actual, predicted, dropna=False).reindex(
        index=labels, columns=labels, fill_value=0
    )
    accuracy = np.trace(matrix.to_numpy()) / matrix.to_numpy().sum()
    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(matrix, annot=True, fmt="d", cmap="Purples", cbar=False, ax=ax)
    ax.set(title=f"{best_model}: 전환율 구간 정확도 {accuracy:.1%}",
           xlabel="예측 구간", ylabel="실제 구간")
    plt.show()


def print_summary(comparison: pd.DataFrame, summary: dict) -> None:
    best = comparison.sort_values("mae").iloc[0]
    print(f"최종 선택 모델: {best['model']}")
    print(f"MAE: {best['mae'] * 100:.2f}%p | RMSE: {best['rmse'] * 100:.2f}%p")
    print(f"R2: {best['r2']:.4f} | ±5%p 적중률: {best['within_5pp_accuracy']:.1%}")
    print(f"테스트 작품: {summary['test_samples']:,}개")


def main() -> None:
    comparison, _, summary = train_and_compare()
    print(comparison.to_string(index=False))
    best = summary["best_model"]
    print(f"BEST={best['model']} MAE={best['mae']:.4f}")


if __name__ == "__main__":
    main()
