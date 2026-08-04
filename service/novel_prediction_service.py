from __future__ import annotations
import pandas as pd
from typing import Tuple

from repository.novel_repository import NovelRepository

class NovelPredictionService:
    
    _cached_drop_rate: float | None = None
    _cached_decay_rate: float | None = None

    def __init__(self, repository: NovelRepository) -> None:
        self.repository = repository

    def _calculate_actual_statistics(self) -> Tuple[float, float]:
        if NovelPredictionService._cached_drop_rate is not None and NovelPredictionService._cached_decay_rate is not None:
            return NovelPredictionService._cached_drop_rate, NovelPredictionService._cached_decay_rate

        try:
            if not hasattr(self.repository, "episodes_csv_path"):
                return 60.0, 0.95

            csv_path = self.repository.episodes_csv_path
            
            df = pd.read_csv(
                csv_path, 
                usecols=["work_id", "episode_number", "view_count", "access_type"],
                engine="c",
                low_memory=False
            )
            
            df = df.dropna(subset=["view_count", "access_type"])
            df["access_type"] = df["access_type"].astype(str).str.upper().str.strip()
            df = df.sort_values(["work_id", "episode_number"])
            
            df["prev_access"] = df.groupby("work_id")["access_type"].shift(1)
            df["prev_view"] = df.groupby("work_id")["view_count"].shift(1)
            
            paid_keywords = {"PAID", "유료", "BLOCK", "LOCKED"}
            transitions = df[(df["prev_access"] == "FREE") & (df["access_type"].isin(paid_keywords))]
            
            if transitions.empty:
                NovelPredictionService._cached_drop_rate = 60.0
            else:
                transitions = transitions[transitions["prev_view"] > 0]
                transitions["drop_rate"] = (transitions["prev_view"] - transitions["view_count"]) / transitions["prev_view"] * 100
                valid = transitions[(transitions["drop_rate"] >= 0) & (transitions["drop_rate"] <= 99)]
                if not valid.empty:
                    NovelPredictionService._cached_drop_rate = round(valid["drop_rate"].mean(), 1)
                else:
                    NovelPredictionService._cached_drop_rate = 60.0

            valid_views = df[df["prev_view"] > 0].copy()
            valid_views["ratio"] = valid_views["view_count"] / valid_views["prev_view"]
            normal_ratios = valid_views[(valid_views["ratio"] >= 0.5) & (valid_views["ratio"] <= 1.0)]["ratio"]
            
            if not normal_ratios.empty:
                avg_decay = normal_ratios.mean()
                NovelPredictionService._cached_decay_rate = round(min(0.99, max(0.85, avg_decay)), 3)
            else:
                NovelPredictionService._cached_decay_rate = 0.95

            return NovelPredictionService._cached_drop_rate, NovelPredictionService._cached_decay_rate

        except Exception as e:
            print(f"통계 계산 중 예외 발생: {e}")
            return 60.0, 0.95

    def get_prediction_data(self, novel_id: int) -> tuple[pd.DataFrame, float] | None:
        novel = self.repository.get_novel(novel_id)
        if not novel: return None

        episodes = self.repository.get_episodes(novel_id)
        if not episodes: return None

        db_drop_rate, db_decay_rate = self._calculate_actual_statistics()

        data = []
        for ep in episodes:
            data.append({
                "회차": ep.episode_number,
                "조회수": ep.view_count or 0,
                "구분": "실제 조회수"
            })

        last_ep_num = episodes[-1].episode_number
        last_view_count = episodes[-1].view_count or 0

        if novel.free:
            predicted_label = "예상 조회수 (유료 전환 시)"
            drop_rate = db_drop_rate 
            predicted_view = last_view_count * (1 - (drop_rate / 100))
            decay_rate = db_decay_rate
        else:
            predicted_label = "예상 조회수 (연재 지속 시)"
            drop_rate = round((1 - db_decay_rate) * 100, 1)
            predicted_view = last_view_count * db_decay_rate
            decay_rate = db_decay_rate

        for i in range(1, 31):
            data.append({
                "회차": last_ep_num + i,
                "조회수": int(predicted_view),
                "구분": predicted_label
            })
            predicted_view *= decay_rate

        return pd.DataFrame(data), drop_rate