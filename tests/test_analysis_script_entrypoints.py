from __future__ import annotations

import ast
import runpy
from dataclasses import dataclass
from pathlib import Path

import service


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    ROOT / "scripts" / "refresh_recommendation_metrics.py",
    ROOT / "scripts" / "train_paid_conversion_model.py",
]
FORBIDDEN_IMPORTS = {"dotenv", "mysql", "numpy", "pandas", "sklearn"}


def test_analysis_scripts_are_thin_wrappers():
    for script in SCRIPTS:
        tree = ast.parse(script.read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert imports.isdisjoint(FORBIDDEN_IMPORTS), script
        functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
        assert functions == ["main"]


def test_refresh_entrypoint_delegates_without_database(monkeypatch, capsys):
    calls = []

    class StubService:
        def refresh_all(self):
            calls.append("refresh_all")

    monkeypatch.setattr(service, "RecommendationMetricService", StubService)

    runpy.run_path(str(SCRIPTS[0]), run_name="__main__")

    assert calls == ["refresh_all"]
    assert capsys.readouterr().out == "Recommendation metrics refreshed\n"


def test_training_entrypoint_delegates_and_prints_summary(monkeypatch, capsys):
    @dataclass
    class Result:
        trained_count: int = 120
        candidate_count: int = 7
        model_mae: float = 0.12345

    class StubService:
        def train_and_predict_all(self):
            return Result()

    monkeypatch.setattr(service, "PaidConversionModelService", StubService)

    runpy.run_path(str(SCRIPTS[1]), run_name="__main__")

    assert capsys.readouterr().out == "trained=120 candidates=7 conversion_mae=0.1235\n"
