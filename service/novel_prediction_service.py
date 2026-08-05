from __future__ import annotations
import pandas as pd
import os
import joblib
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

    def _predict_drop_rate_with_ml(self, novel_id: int) -> float | None:
        try:
            # 1. 모델과 스케일러 경로 설정 (상대 경로 방어적 처리)
            base_dir = os.path.dirname(os.path.abspath(__file__))
            model_path = os.path.join(base_dir, "../research/model/drop_rate_rf_model.pkl")
            scaler_path = os.path.join(base_dir, "../research/model/drop_rate_scaler.pkl")
            
            # 모델 파일이 없으면 Fallback 작동 (기존 전체 통계치 사용)
            if not os.path.exists(model_path) or not os.path.exists(scaler_path):
                print(f"⚠️ [ML Fallback] 머신러닝 모델 파일이 없습니다: {model_path}")
                return None
                
            # 2. 모델 및 스케일러 로드
            rf_model = joblib.load(model_path)
            scaler = joblib.load(scaler_path)
            
            # 3. 예측할 작품 및 최신 무료 회차 정보 가져오기
            novel = self.repository.get_novel(novel_id)
            episodes = self.repository.get_episodes(novel_id)
            if not novel or not episodes:
                return None
                
            last_ep = episodes[-1] # 마지막(최신) 회차 정보 추출
            
            # 4. 훈련 당시의 피처 컬럼들 가져오기 (컬럼 순서 및 개수를 맞추기 위함)
            expected_features = getattr(scaler, "feature_names_in_", None)
            if expected_features is None:
                print("⚠️ [ML Fallback] 모델에서 기대 피처 정보를 읽을 수 없습니다.")
                return None
                
            # 5. 빈 데이터프레임을 만들고 입력값 매핑 (0으로 초기화)
            input_df = pd.DataFrame(0.0, index=[0], columns=expected_features)
            
            # 숫자형 변수 주입
            input_df.at[0, 'episode_number_free'] = getattr(last_ep, 'episode_number', 0)
            input_df.at[0, 'page_count_free'] = getattr(last_ep, 'page_count', 0)
            input_df.at[0, 'view_count_free'] = getattr(last_ep, 'view_count', 0)
            input_df.at[0, 'like_count_free'] = getattr(last_ep, 'like_count', 0)
            input_df.at[0, 'comment_count_free'] = getattr(last_ep, 'comment_count', 0)
            
            # 범주형(원핫인코딩) 변수 주입 (True 시 1.0 세팅)
            genre = getattr(novel, 'genre_best_name', '')
            if f'genre_best_name_{genre}' in input_df.columns:
                input_df.at[0, f'genre_best_name_{genre}'] = 1.0
            elif 'genre_best_name_other_genre' in input_df.columns:
                input_df.at[0, 'genre_best_name_other_genre'] = 1.0
                
            adult = getattr(novel, 'adult', False)
            if adult and 'adult_True' in input_df.columns:
                input_df.at[0, 'adult_True'] = 1.0
                
            exclusive = getattr(novel, 'exclusive', False)
            if exclusive and 'exclusive_True' in input_df.columns:
                input_df.at[0, 'exclusive_True'] = 1.0
                
            contest = getattr(novel, 'contest', False)
            if contest and 'contest_True' in input_df.columns:
                input_df.at[0, 'contest_True'] = 1.0

            # 6. 스케일링 진행 후 Random Forest 예측
            input_scaled = scaler.transform(input_df)
            pred_drop_rate = rf_model.predict(input_scaled)[0] # 결과는 0.0 ~ 1.0 사이
            
            # 백분율로 변환하고 0% ~ 100% 사이를 벗어나지 않도록 클리핑
            final_rate = round(float(pred_drop_rate) * 100, 1)
            final_rate = max(0.0, min(100.0, final_rate))
            
            return final_rate
            
        except Exception as e:
            # 에러 발생 시 프로그램이 멈추지 않고, 평균 통계 그래프로 빠지도록 설계 (요구사항)
            print(f"⚠️ [ML Fallback] ML 예측 중 예외 발생: {e}")
            return None


    # =========================================================================
    # 기존 UI로 반환하는 메인 함수 (is_ml 파라미터 추가)
    # =========================================================================
    def get_prediction_data(self, novel_id: int, is_ml: bool = False) -> tuple[pd.DataFrame, float] | None:
        novel = self.repository.get_novel(novel_id)
        if not novel: return None

        episodes = self.repository.get_episodes(novel_id)
        if not episodes: return None

        # 기본(통계 기반) 낙폭률 및 유지율 세팅
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
            drop_rate = db_drop_rate # 기본값: 통계 기반 낙폭
            
            # ✨ 사용자가 AI 모델 예측을 선택했다면?
            if is_ml:
                ml_rate = self._predict_drop_rate_with_ml(novel_id)
                # ML 예측에 성공했다면 해당 낙폭률 덮어쓰기 (실패하면 기존 85.3% 유지)
                if ml_rate is not None:
                    drop_rate = ml_rate
                    
            predicted_view = last_view_count * (1 - (drop_rate / 100))
            decay_rate = db_decay_rate
        else:
            # 이미 유료인 작품은 자연 감소(Decay) 모델을 사용하므로 ML 분기 제외
            predicted_label = "예상 조회수 (연재 지속 시)"
            drop_rate = round((1 - db_decay_rate) * 100, 1)
            predicted_view = last_view_count * db_decay_rate
            decay_rate = db_decay_rate

        # 향후 30회차 시뮬레이션
        for i in range(1, 31):
            data.append({
                "회차": last_ep_num + i,
                "조회수": int(predicted_view),
                "구분": predicted_label
            })
            predicted_view *= decay_rate

        return pd.DataFrame(data), drop_rate