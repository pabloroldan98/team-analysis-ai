"""
XGBoost model for player value prediction.

Predicts future market value based on historical valuations and player features.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from ml.feature_engineering import (
    PlayerFeatures,
    TOP_CLUBS,
    TOP_NATIONALITIES,
    build_training_dataset,
    build_prediction_dataset,
    extract_player_features,
)
from entities.valuation import Valuation
from entities.player import Player

# Model directory
MODELS_DIR = Path(__file__).parent / "models"


class ValuePredictor:
    """
    XGBoost-based predictor for player market values.
    
    Predicts what a player's market value will be in 1 year.
    """
    
    FEATURE_NAMES = [
        "current_value_M", "age",
        "position", "player_nationality_bin", "current_club_bin",
        "current_league", "league_tier",
        "current_club_value_M", "is_in_top_league", "is_in_home_league",
        "valuation_year",
        "max_value_M", "min_value_M", "avg_value_M",
        "last_valuation_date_num",
        "value_1y_ago_M", "value_2y_ago_M",
        "value_3y_ago_M", "value_4y_ago_M", "value_5y_ago_M",
        "trend_1y", "trend_2y", "trend_4y", "trend_5y",
        "pct_1y", "pct_2y", "pct_4y", "pct_5y",
        "diff_1y_M", "diff_2y_M", "diff_4y_M", "diff_5y_M",
        "months_since_peak", "num_valuations", "months_of_history",
        "current_value_percentile",
        "value_1y_ago_percentile",
        "value_2y_ago_percentile", "value_3y_ago_percentile",
        "value_4y_ago_percentile", "value_5y_ago_percentile",
        "diff_percentile_1y", "diff_percentile_2y",
        "diff_percentile_3y", "diff_percentile_4y", "diff_percentile_5y",
        "trend_percentile_1y", "trend_percentile_2y",
        "trend_percentile_3y", "trend_percentile_4y", "trend_percentile_5y",
        "pct_percentile_1y", "pct_percentile_2y",
        "pct_percentile_3y", "pct_percentile_4y", "pct_percentile_5y",
        # v2 extended features
        "height", "preferred_foot", "num_positions",
        "value_volatility", "value_acceleration", "peak_ratio",
        "age_value_ratio", "log_current_value",
        "on_loan",
        "fair_price_M",
    ]
    
    CATEGORICAL_FEATURES = [
        "position", "player_nationality_bin", "current_club_bin",
        "current_league", "league_tier", "preferred_foot",
    ]

    # Fallback allowed values when model has no category mappings (old models).
    # Any value not in these sets is mapped to "Other" to avoid XGBoost "category not in training set" errors.
    # These must match what the training dataset actually contained (top-5 leagues only).
    FALLBACK_CATEGORY_VALUES = {
        "position": {"GK", "DEF", "MID", "ATT"},
        "player_nationality_bin": {
            "Albania", "Argentina", "Australia", "Austria", "Belgium", "Brazil",
            "Cameroon", "Canada", "Chile", "China", "Colombia", "Croatia",
            "Czech Republic", "Denmark", "Ecuador", "Egypt", "England", "France",
            "Germany", "Ghana", "Greece", "Hungary", "Iran", "Italy", "Japan",
            "Kosovo", "Mexico", "Morocco", "Netherlands", "Nigeria",
            "North Macedonia", "Norway", "Other", "None", "Paraguay", "Peru",
            "Poland", "Portugal", "Qatar", "Romania", "Russia", "Saudi Arabia",
            "Scotland", "Senegal", "Serbia", "Slovakia", "Slovenia",
            "South Africa", "Spain", "Sweden", "Switzerland", "Ukraine",
            "United Arab Emirates", "United States", "Uruguay", "Wales",
        },
        "current_club_bin": set(TOP_CLUBS) | {"Other", "None"},
        "current_league": {
            "laliga", "premier", "seriea", "bundesliga", "ligue1", "Other", "None",
        },
        "league_tier": {"1", "Other", "None"},
        "preferred_foot": {"left", "right", "both", "Left", "Right", "Both", "Unknown"},
    }
    
    def __init__(self, model_path: Optional[Path] = None):
        """
        Initialize predictor.
        
        Args:
            model_path: Path to saved model. If None, model must be trained.
        """
        self.model = None
        self.model_path = model_path
        self.is_trained = False
        
        if model_path and model_path.exists():
            self.load(model_path)
    
    def train(
        self,
        training_data: List[PlayerFeatures],
        test_years: int = 1,
        verbose: bool = True,
        **xgb_params,
    ) -> Dict[str, float]:
        """
        Train the XGBoost model with temporal train/validation split.
        
        Args:
            training_data: List of PlayerFeatures with target values
            test_years: Number of most recent years to use for validation (default: 1)
            verbose: Print training progress
            **xgb_params: Additional XGBoost parameters
        
        Returns:
            Dict with training metrics (train_rmse, val_rmse, train_mae, val_mae, etc.)
        """
        try:
            import pandas as pd
            import xgboost as xgb
            from sklearn.metrics import mean_squared_error, mean_absolute_error
        except ImportError as e:
            raise ImportError(
                "Required packages not installed. Run: pip install xgboost scikit-learn pandas"
            ) from e
        
        if not training_data:
            raise ValueError("No training data provided")
        
        # Temporal split: sort by cutoff_season and split by years
        # Get unique seasons sorted
        seasons = sorted(set(f.cutoff_season for f in training_data if f.cutoff_season))
        if len(seasons) < test_years + 1:
            raise ValueError(
                f"Not enough seasons ({len(seasons)}) for temporal split with test_years={test_years}"
            )
        
        # Train on older seasons, validate on most recent ones
        train_seasons = set(seasons[:-test_years])
        val_seasons = set(seasons[-test_years:])
        
        train_data = [f for f in training_data if f.cutoff_season in train_seasons]
        val_data = [f for f in training_data if f.cutoff_season in val_seasons]
        
        if verbose:
            print(f"Temporal split:")
            print(f"  Train seasons: {sorted(train_seasons)}")
            print(f"  Val seasons:   {sorted(val_seasons)}")
            print(f"  Train samples: {len(train_data)}, Val samples: {len(val_data)}")
        
        # Prepare data as DataFrame (for enable_categorical support)
        X_train = pd.DataFrame([f.to_feature_dict() for f in train_data])
        X_val = pd.DataFrame([f.to_feature_dict() for f in val_data])
        
        # Target: value in millions (optimizes for absolute errors)
        y_train = np.array([f.target_value / 1_000_000 for f in train_data])
        y_val = np.array([f.target_value / 1_000_000 for f in val_data])
        
        # Sample weights: more recent seasons get higher weight (inflation / relevance)
        # weight = (year - min_year + 1) / (max_year - min_year + 1)
        years = [
            int(f.cutoff_season.split("-")[0])
            for f in train_data
            if f.cutoff_season and "-" in f.cutoff_season
        ]
        if years:
            min_year = min(years)
            max_year = max(years)
            n_years = max_year - min_year + 1
            sample_weight = np.array([
                (int(f.cutoff_season.split("-")[0]) - min_year + 1) / n_years
                if f.cutoff_season and "-" in f.cutoff_season
                else 1.0
                for f in train_data
            ])
            if verbose:
                print(f"Sample weights: year range {min_year}-{max_year}, n={n_years}")
        else:
            sample_weight = None
        
        # ALTERNATIVE: Log-transform target (optimizes for percentage errors)
        # Use this if you care more about relative accuracy across all price ranges.
        # A €5M error on a €10M player would be penalized more than on a €100M player.
        # 
        # self._use_log_transform = True
        # y_train = np.log1p(np.array([f.target_value for f in train_data]))
        # y_val = np.log1p(np.array([f.target_value for f in val_data]))
        # 
        # Then in predict(): return np.expm1(self.model.predict(X))
        
        # Unify categories: val may have values unseen in train → map to "Other" / "None"
        for col in self.CATEGORICAL_FEATURES:
            if col not in X_train.columns:
                continue
            train_cats = set(X_train[col].dropna().unique())
            X_val[col] = X_val[col].apply(
                lambda v, cats=train_cats: v if v in cats else (
                    "None" if v in (None, "", "nan", "None") else "Other"
                )
            )
            all_cats = sorted(train_cats | {"Other", "None"})
            cat_type = pd.CategoricalDtype(categories=all_cats)
            X_train[col] = X_train[col].astype(cat_type)
            X_val[col] = X_val[col].astype(cat_type)
        
        if verbose:
            print(f"Features: {len(X_train.columns)} ({self.CATEGORICAL_FEATURES} are categorical)")
        
        # Default XGBoost parameters with enable_categorical
        default_params = {
            "n_estimators": 200,
            "max_depth": 6,
            "learning_rate": 0.1,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 3,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "random_state": 42,
            "n_jobs": -1,
            "enable_categorical": True,  # Native categorical support
        }
        default_params.update(xgb_params)
        
        # Train model
        self.model = xgb.XGBRegressor(**default_params)
        
        fit_kwargs = {
            "X": X_train,
            "y": y_train,
            "eval_set": [(X_val, y_val)],
            "verbose": verbose,
        }
        if sample_weight is not None:
            fit_kwargs["sample_weight"] = sample_weight
        
        self.model.fit(**fit_kwargs)
        
        self.is_trained = True
        self._category_mappings = {
            col: set(X_train[col].dropna().astype(str).unique()) | {"Other", "None"}
            for col in self.CATEGORICAL_FEATURES
            if col in X_train.columns
        }
        
        # Compute metrics
        train_pred = self.model.predict(X_train)
        val_pred = self.model.predict(X_val)
        
        # MAPE calculation (avoid division by zero)
        def mape(y_true, y_pred):
            mask = y_true > 0.1  # Ignore very small values (< €100k)
            if mask.sum() == 0:
                return 0.0
            return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)
        
        # Median Absolute Percentage Error (more robust to outliers)
        def mdape(y_true, y_pred):
            mask = y_true > 0.1
            if mask.sum() == 0:
                return 0.0
            return float(np.median(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)
        
        metrics = {
            "train_rmse": float(np.sqrt(mean_squared_error(y_train, train_pred))),
            "val_rmse": float(np.sqrt(mean_squared_error(y_val, val_pred))),
            "train_mae": float(mean_absolute_error(y_train, train_pred)),
            "val_mae": float(mean_absolute_error(y_val, val_pred)),
            "train_mape": mape(y_train, train_pred),
            "val_mape": mape(y_val, val_pred),
            "train_mdape": mdape(y_train, train_pred),
            "val_mdape": mdape(y_val, val_pred),
            "num_train_samples": len(X_train),
            "num_val_samples": len(X_val),
            "num_features": len(X_train.columns),
            "train_seasons": sorted(train_seasons),
            "val_seasons": sorted(val_seasons),
        }
        
        if verbose:
            print(f"\nTraining complete:")
            print(f"  Train RMSE:  €{metrics['train_rmse']:.2f}M  |  Val RMSE:  €{metrics['val_rmse']:.2f}M")
            print(f"  Train MAE:   €{metrics['train_mae']:.2f}M  |  Val MAE:   €{metrics['val_mae']:.2f}M")
            print(f"  Train MAPE:  {metrics['train_mape']:.1f}%    |  Val MAPE:  {metrics['val_mape']:.1f}%")
            print(f"  Train MdAPE: {metrics['train_mdape']:.1f}%    |  Val MdAPE: {metrics['val_mdape']:.1f}%")
        
        return metrics

    def _coerce_categories_for_prediction(self, X):
        """
        Map categorical values not seen during training to "Other".
        Prevents XGBoostError when prediction data has categories the model wasn't trained on.
        """
        allowed = getattr(self, "_category_mappings", None) or self.FALLBACK_CATEGORY_VALUES

        X = X.copy()
        for col in self.CATEGORICAL_FEATURES:
            if col not in X.columns:
                continue
            valid = allowed.get(col)
            if valid is None:
                continue
            X[col] = X[col].fillna("None").astype(str).apply(
                lambda v: v if v in valid else ("None" if v in ("", "nan", "None") else "Other")
            )
        return X
    
    def predict(self, features: PlayerFeatures) -> float:
        """
        Predict future value for a single player.
        
        Args:
            features: PlayerFeatures object
        
        Returns:
            Predicted value in euros (not millions)
        """
        import pandas as pd
        
        if not self.is_trained:
            raise RuntimeError("Model not trained. Call train() or load() first.")
        
        X = pd.DataFrame([features.to_feature_dict()])

        model_features = getattr(self.model, "feature_names_in_", None)
        if model_features is not None:
            missing = [c for c in model_features if c not in X.columns]
            for c in missing:
                X[c] = float("nan")
            X = X[[c for c in model_features if c in X.columns]]

        X = self._coerce_categories_for_prediction(X)
        for col in self.CATEGORICAL_FEATURES:
            if col in X.columns:
                X[col] = X[col].astype("category")
        
        pred_millions = self.model.predict(X)[0]
        
        return max(0, pred_millions * 1_000_000)
    
    def predict_batch(self, features_list: List[PlayerFeatures]) -> List[float]:
        """
        Predict future values for multiple players.
        
        Automatically filters features to match what the loaded model expects
        (backward compatible with v1 models that lack v2 features).
        
        Args:
            features_list: List of PlayerFeatures
        
        Returns:
            List of predicted values in euros
        """
        import pandas as pd
        
        if not self.is_trained:
            raise RuntimeError("Model not trained. Call train() or load() first.")
        
        if not features_list:
            return []
        
        X = pd.DataFrame([f.to_feature_dict() for f in features_list])

        model_features = getattr(self.model, "feature_names_in_", None)
        if model_features is not None:
            missing = [c for c in model_features if c not in X.columns]
            for c in missing:
                X[c] = float("nan")
            X = X[[c for c in model_features if c in X.columns]]

        X = self._coerce_categories_for_prediction(X)
        for col in self.CATEGORICAL_FEATURES:
            if col in X.columns:
                X[col] = X[col].astype("category")
        
        preds_millions = self.model.predict(X)
        
        return [max(0, p * 1_000_000) for p in preds_millions]
    
    def save(self, path: Optional[Path] = None) -> Path:
        """
        Save trained model to disk.
        
        Args:
            path: Path to save model. If None, uses default in models/
        
        Returns:
            Path where model was saved
        """
        if not self.is_trained:
            raise RuntimeError("No trained model to save")
        
        try:
            import joblib
        except ImportError:
            raise ImportError("joblib required. Run: pip install joblib")
        
        if path is None:
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = MODELS_DIR / f"value_model_{timestamp}.joblib"
        
        payload = {
            "model": self.model,
            "category_mappings": getattr(self, "_category_mappings", None),
        }
        joblib.dump(payload, path)
        self.model_path = path
        
        return path
    
    def load(self, path: Path) -> None:
        """
        Load trained model from disk.
        
        Args:
            path: Path to saved model
        """
        try:
            import joblib
        except ImportError:
            raise ImportError("joblib required. Run: pip install joblib")
        
        if not path.exists():
            raise FileNotFoundError(f"Model not found: {path}")
        
        loaded = joblib.load(path)
        if isinstance(loaded, dict) and "model" in loaded:
            self.model = loaded["model"]
            self._category_mappings = loaded.get("category_mappings")
        else:
            self.model = loaded
            self._category_mappings = None
        self.model_path = path
        self.is_trained = True
    
    def get_feature_importance(self) -> Dict[str, float]:
        """
        Get feature importance from trained model.
        
        Returns:
            Dict mapping feature name to importance score
        """
        if not self.is_trained:
            raise RuntimeError("Model not trained")
        
        importances = self.model.feature_importances_
        # Use model's feature names if available (sklearn 1.0+), else fallback to FEATURE_NAMES
        names = getattr(self.model, "feature_names_in_", None)
        if names is not None:
            return dict(zip(names, importances))
        return dict(zip(self.FEATURE_NAMES, importances))
    
    @classmethod
    def get_latest_model(cls) -> Optional[Path]:
        """Get path to most recently saved model."""
        if not MODELS_DIR.exists():
            return None

        models = list(MODELS_DIR.glob("value_model_*.joblib"))
        if not models:
            return None

        return max(models, key=lambda p: p.stat().st_mtime)

    @classmethod
    def find_model_with_fallback(cls, season: str, max_fallback: int = 5) -> Optional[Path]:
        """Find the model for *season*, falling back to previous seasons."""
        start_year = int(season.split("-")[0])
        for offset in range(max_fallback + 1):
            yr = start_year - offset
            path = MODELS_DIR / f"value_model_{yr}-{yr + 1}.joblib"
            if path.exists():
                return path
        return None


MAX_ANNUAL_GROWTH = {
    "under_1M": 10.0,     # can 10x (youth breakout)
    "1M_10M": 5.0,        # can 5x
    "10M_100M": 3.0,      # can 3x
    "over_100M": 2.0,     # can 2x at most
}
MAX_ANNUAL_DECLINE = 0.10  # floor: never predict < 10% of current value


def clamp_prediction(pred: float, current_value: float) -> float:
    """Clamp prediction to avoid anomalous values based on value segment."""
    if current_value <= 0:
        return max(pred, 0)
    seg = _segment_for_value(current_value)
    max_growth = MAX_ANNUAL_GROWTH.get(seg, 3.0)
    ceiling = current_value * max_growth
    floor = current_value * MAX_ANNUAL_DECLINE
    return max(floor, min(pred, ceiling))


SEGMENT_THRESHOLDS = [
    ("under_1M", 0, 1_000_000),
    ("1M_10M", 1_000_000, 10_000_000),
    ("10M_100M", 10_000_000, 100_000_000),
    ("over_100M", 100_000_000, float("inf")),
]

BLEND_ZONE = 0.15


def _segment_for_value(value: float) -> str:
    """Return segment name for a given market value."""
    for name, lo, hi in SEGMENT_THRESHOLDS:
        if lo <= value < hi:
            return name
    return SEGMENT_THRESHOLDS[-1][0]


class SegmentedValuePredictor:
    """
    Ensemble of 4 segment-specific ValuePredictor models.

    Routes each player to the model trained on their value range.
    At segment boundaries a soft blend (weighted average) avoids discontinuities.
    Falls back to the global model when a segment model is missing.
    """

    def __init__(self, season: str, models_dir: Optional[Path] = None):
        self.season = season
        self.models_dir = models_dir or MODELS_DIR
        self.global_model: Optional[ValuePredictor] = None
        self.segment_models: Dict[str, ValuePredictor] = {}
        self._load(season)

    def _load(self, season: str) -> None:
        global_path = self.models_dir / f"value_model_{season}.joblib"
        if global_path.exists():
            self.global_model = ValuePredictor(global_path)

        for seg_name, _, _ in SEGMENT_THRESHOLDS:
            seg_path = self.models_dir / f"value_model_{season}_{seg_name}.joblib"
            if seg_path.exists():
                self.segment_models[seg_name] = ValuePredictor(seg_path)

    @property
    def is_trained(self) -> bool:
        return bool(self.segment_models) or (self.global_model is not None and self.global_model.is_trained)

    def _get_model(self, segment: str) -> ValuePredictor:
        return self.segment_models.get(segment) or self.global_model

    def predict_batch(self, features_list: List[PlayerFeatures]) -> List[float]:
        """Predict with segment routing, boundary blending and anomaly clamping.

        Blending is batched: players near segment boundaries are collected
        per (lo_model, hi_model) pair and predicted in two batch calls
        instead of 2 × N individual calls.
        """
        if not features_list:
            return []
        if not self.segment_models:
            if self.global_model and self.global_model.is_trained:
                raw = self.global_model.predict_batch(features_list)
                return [clamp_prediction(p, f.current_value) for p, f in zip(raw, features_list)]
            raise RuntimeError("No models loaded")

        results = [0.0] * len(features_list)
        seg_indices: Dict[str, List[int]] = {s: [] for s, _, _ in SEGMENT_THRESHOLDS}

        for i, f in enumerate(features_list):
            seg_indices[_segment_for_value(f.current_value)].append(i)

        for seg_name, indices in seg_indices.items():
            if not indices:
                continue
            model = self._get_model(seg_name)
            if model is None:
                continue
            seg_features = [features_list[i] for i in indices]
            preds = model.predict_batch(seg_features)
            for idx, pred in zip(indices, preds):
                results[idx] = pred

        # Batch blending: group boundary players by (lo_model, hi_model) pair
        blend_groups: Dict[Tuple[str, str], List[Tuple[int, float]]] = {}
        for i, f in enumerate(features_list):
            val = f.current_value
            for j, (_, _lo, hi) in enumerate(SEGMENT_THRESHOLDS[:-1]):
                boundary = hi
                zone = boundary * BLEND_ZONE
                if abs(val - boundary) < zone:
                    lo_seg = SEGMENT_THRESHOLDS[j][0]
                    hi_seg = SEGMENT_THRESHOLDS[j + 1][0]
                    m_lo = self._get_model(lo_seg)
                    m_hi = self._get_model(hi_seg)
                    if m_lo and m_hi and m_lo is not m_hi:
                        alpha = max(0.0, min(1.0, (val - (boundary - zone)) / (2 * zone)))
                        blend_groups.setdefault((lo_seg, hi_seg), []).append((i, alpha))
                    break

        for (lo_seg, hi_seg), items in blend_groups.items():
            if not items:
                continue
            indices_blend = [it[0] for it in items]
            alphas = [it[1] for it in items]
            blend_features = [features_list[i] for i in indices_blend]
            preds_lo = self._get_model(lo_seg).predict_batch(blend_features)
            preds_hi = self._get_model(hi_seg).predict_batch(blend_features)
            for idx, a, p_lo, p_hi in zip(indices_blend, alphas, preds_lo, preds_hi):
                results[idx] = (1 - a) * p_lo + a * p_hi

        return [clamp_prediction(p, f.current_value) for p, f in zip(results, features_list)]


def predict_player_values(
    valuations: List[Valuation],
    cutoff_date: datetime,
    model,
    players: Optional[Dict[str, Player]] = None,
) -> Dict[str, float]:
    """
    Predict future values for all players.
    
    Args:
        valuations: All valuations up to cutoff_date
        cutoff_date: Current date for prediction
        model: Trained ValuePredictor or SegmentedValuePredictor
        players: Optional player info dict
    
    Returns:
        Dict mapping player_id to predicted value (euros)
    """
    features_list = build_prediction_dataset(
        valuations,
        cutoff_date,
        players=players,
    )
    
    if not features_list:
        return {}
    
    predictions = model.predict_batch(features_list)
    
    return {
        f.player_id: pred
        for f, pred in zip(features_list, predictions)
    }
