"""
Machine Learning module for player value prediction.

Uses XGBoost to predict future market values based on historical valuations.

Modules:
    - feature_engineering: Extract features from valuation history
    - value_predictor: XGBoost model for value prediction
    - train_pipeline: Training script and utilities
"""

from ml.value_predictor import ValuePredictor
from ml.feature_engineering import extract_player_features, build_training_dataset

__all__ = [
    "ValuePredictor",
    "extract_player_features",
    "build_training_dataset",
]
