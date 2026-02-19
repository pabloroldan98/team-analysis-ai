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
from valuation import Valuation
from player import Player

# Model directory
MODELS_DIR = Path(__file__).parent / "models"


class ValuePredictor:
    """
    XGBoost-based predictor for player market values.
    
    Predicts what a player's market value will be in 1 year.
    """
    
    # Feature names (must match to_feature_dict order; categorical handled by XGBoost enable_categorical)
    FEATURE_NAMES = [
        "current_value_M",
        "age",
        "position",  # Categorical
        "player_nationality_bin",  # Categorical
        "current_club_bin",  # Categorical
        "current_league",  # Categorical
        "league_tier",  # Categorical
        "current_club_value_M",
        "is_in_top_league",
        "is_in_home_league",
        "valuation_year",
        "max_value_M",
        "min_value_M",
        "avg_value_M",
        "value_6m_ago_M",
        "value_1y_ago_M",
        "value_2y_ago_M",
        "value_3y_ago_M",
        "value_4y_ago_M",
        "value_5y_ago_M",
        "trend_6m",
        "trend_1y",
        "trend_2y",
        "trend_4y",
        "trend_5y",
        "pct_6m",
        "pct_1y",
        "pct_2y",
        "pct_4y",
        "pct_5y",
        "diff_6m_M",
        "diff_1y_M",
        "diff_2y_M",
        "diff_4y_M",
        "diff_5y_M",
        "months_since_peak",
        "num_valuations",
        "months_of_history",
        "current_value_percentile",
        "value_6m_ago_percentile",
        "value_1y_ago_percentile",
        "value_2y_ago_percentile",
        "value_3y_ago_percentile",
        "value_4y_ago_percentile",
        "value_5y_ago_percentile",
        "diff_percentile_6m",
        "diff_percentile_1y",
        "diff_percentile_2y",
        "diff_percentile_3y",
        "diff_percentile_4y",
        "diff_percentile_5y",
        "trend_percentile_6m",
        "trend_percentile_1y",
        "trend_percentile_2y",
        "trend_percentile_3y",
        "trend_percentile_4y",
        "trend_percentile_5y",
        "pct_percentile_6m",
        "pct_percentile_1y",
        "pct_percentile_2y",
        "pct_percentile_3y",
        "pct_percentile_4y",
        "pct_percentile_5y",
    ]
    
    # Categorical feature names for XGBoost
    CATEGORICAL_FEATURES = ["position", "player_nationality_bin", "current_club_bin", "current_league", "league_tier"]

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
            "North Macedonia", "Norway", "Other", "Paraguay", "Peru", "Poland",
            "Portugal", "Qatar", "Romania", "Russia", "Saudi Arabia", "Scotland",
            "Senegal", "Serbia", "Slovakia", "Slovenia", "South Africa", "Spain",
            "Sweden", "Switzerland", "Ukraine", "United Arab Emirates",
            "United States", "Uruguay", "Wales",
        },
        "current_club_bin": set(TOP_CLUBS) | {"Other"},
        "current_league": {
            "laliga", "premier", "seriea", "bundesliga", "ligue1", "Other",
        },
        "league_tier": {"1", "Other"},
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
        
        # Unify categories: val may have values unseen in train → map to "Other"
        for col in self.CATEGORICAL_FEATURES:
            if col not in X_train.columns:
                continue
            train_cats = set(X_train[col].dropna().unique())
            X_val[col] = X_val[col].apply(
                lambda v, cats=train_cats: v if v in cats else "Other"
            )
            all_cats = sorted(train_cats | {"Other"})
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
            col: set(X_train[col].dropna().astype(str).unique()) | {"Other"}
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
            X[col] = X[col].fillna("Other").astype(str).apply(
                lambda v: v if v in valid else "Other"
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
        X = self._coerce_categories_for_prediction(X)
        for col in self.CATEGORICAL_FEATURES:
            if col in X.columns:
                X[col] = X[col].astype("category")
        
        pred_millions = self.model.predict(X)[0]
        
        return max(0, pred_millions * 1_000_000)  # Convert back to euros
    
    def predict_batch(self, features_list: List[PlayerFeatures]) -> List[float]:
        """
        Predict future values for multiple players.
        
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


def predict_player_values(
    valuations: List[Valuation],
    cutoff_date: datetime,
    model: ValuePredictor,
    players: Optional[Dict[str, Player]] = None,
) -> Dict[str, float]:
    """
    Predict future values for all players.
    
    Args:
        valuations: All valuations up to cutoff_date
        cutoff_date: Current date for prediction
        model: Trained ValuePredictor
        players: Optional player info dict
    
    Returns:
        Dict mapping player_id to predicted value (euros)
    """
    # Build prediction dataset
    features_list = build_prediction_dataset(
        valuations,
        cutoff_date,
        players=players,
    )
    
    if not features_list:
        return {}
    
    # Predict
    predictions = model.predict_batch(features_list)
    
    # Map to player IDs
    return {
        f.player_id: pred
        for f, pred in zip(features_list, predictions)
    }
