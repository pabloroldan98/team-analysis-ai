"""
Training pipeline for player value prediction model.

Usage:
    # Train for a specific season (recommended)
    python -m ml.train_pipeline --season 2023-2024
    
    # Train with explicit cutoff date
    python -m ml.train_pipeline --cutoff 2023-07-01
    
    # Train with custom parameters
    python -m ml.train_pipeline --season 2022-2023 --n-estimators 300 --max-depth 8
    
    # Rebuild the dataset (e.g., after new data is scraped)
    python -m ml.train_pipeline --season 2023-2024 --rebuild-dataset
    
    # Use semi-annual cutoffs (more training data, but slower to build)
    python -m ml.train_pipeline --season 2023-2024 --cutoff-months 6 --rebuild-dataset

Output:
    ml/models/value_model_2023-2024.joblib  (trained model)
    ml/models/value_model_2023-2024.json    (metrics)
    ml/datasets/training_dataset_12m.json   (cached dataset, 12m = annual)

This will:
1. Load or build the complete training dataset:
   - If dataset exists (ml/datasets/training_dataset_Xm.json), load it
   - If not (or --rebuild-dataset), build from scratch and save
   - Dataset has multiple cutoffs per player (configurable frequency)
   - Example: Messi has rows for cutoff 2017, 2018, 2019, 2020, etc.
2. Filter dataset to only use data from seasons BEFORE the target season
   - Model for 2023-2024 uses data from 2017-2018, 2018-2019, ..., 2022-2023
   - This prevents data leakage from future seasons
3. Train XGBoost model to predict value 1 year in the future
4. Save model and metrics to ml/models/
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from ml.feature_engineering import (
    build_training_dataset,
    load_team_league_mapping,
    PlayerFeatures,
    save_training_dataset,
    load_training_dataset,
    filter_dataset_for_season,
    get_samples_for_season,
)
from ml.value_predictor import ValuePredictor, MODELS_DIR
from valuation import Valuation
from player import Player
from scraping.utils.helpers import DATA_DIR, list_json_bases, load_json

import numpy as np


def load_all_valuations(
    max_seasons: Optional[int] = None,
    verbose: bool = True,
) -> List[Valuation]:
    """
    Load all valuations from all available JSON files.
    
    Args:
        max_seasons: Optional limit on number of seasons to load
        verbose: Print progress
    
    Returns:
        List of all Valuation objects
    """
    all_valuations = []
    bases = list_json_bases("valuations_all_*.json")

    if max_seasons:
        seasons = sorted({b.replace("valuations_all_", "") for b in bases if b.startswith("valuations_all_")}, reverse=True)[:max_seasons]
        bases = [b for b in bases if b.replace("valuations_all_", "") in seasons]

    if verbose:
        print(f"Loading valuations from {len(bases)} files...")

    for base in bases:
        try:
            data = load_json(base)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        all_valuations.append(Valuation.from_dict(item))
            if verbose:
                print(f"  Loaded {base}: {len(data) if isinstance(data, list) else 0} valuations")
        except Exception as e:
            if verbose:
                print(f"  Error loading {base}: {e}")
    
    if verbose:
        print(f"Total valuations loaded: {len(all_valuations)}")
    
    return all_valuations


def load_all_players(verbose: bool = True) -> Dict[str, Player]:
    """
    Load all players from combined player files.
    
    Returns:
        Dict mapping player_id to Player object
    """
    players: Dict[str, Player] = {}
    bases = list_json_bases("players_all_*.json")

    if verbose:
        print(f"Loading players from {len(bases)} files...")

    for base in bases:
        try:
            data = load_json(base)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        p = Player.from_dict(item)
                        # Keep most recent player info
                        if p.player_id not in players:
                            players[p.player_id] = p
                            
        except Exception as e:
            if verbose:
                print(f"  Error loading {base}: {e}")

    if verbose:
        print(f"Total unique players loaded: {len(players)}")
    
    return players


def _season_to_cutoff(season: str) -> datetime:
    """Convert season string to cutoff date (01/07 of start year)."""
    start_year = int(season.split("-")[0])
    return datetime(start_year, 7, 1)


def _evaluate_predictions(
    predictor: ValuePredictor,
    eval_data: List[PlayerFeatures],
    season: str,
    verbose: bool = True,
) -> Dict[str, float]:
    """
    Evaluate model predictions on target season data.
    
    Args:
        predictor: Trained ValuePredictor
        eval_data: List of PlayerFeatures from target season (with target_value)
        season: Target season string (e.g., "2023-2024")
        verbose: Print detailed results
    
    Returns:
        Dict with evaluation metrics
    """
    from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
    
    if not eval_data:
        if verbose:
            print(f"\nNo evaluation data for season {season}")
        return {}
    
    # Get predictions and actual values
    predictions = predictor.predict_batch(eval_data)
    actuals = [f.target_value for f in eval_data]
    
    # Convert to millions for readability
    preds_m = np.array(predictions) / 1_000_000
    actuals_m = np.array(actuals) / 1_000_000
    
    # Calculate metrics
    rmse = float(np.sqrt(mean_squared_error(actuals_m, preds_m)))
    mae = float(mean_absolute_error(actuals_m, preds_m))
    r2 = float(r2_score(actuals_m, preds_m))
    
    # Calculate percentage errors (MAPE, MdAPE)
    pct_errors = []
    for pred, actual in zip(predictions, actuals):
        if actual > 100_000:  # Ignore very small values (< €100k)
            pct_error = abs(pred - actual) / actual * 100
            pct_errors.append(pct_error)
    
    mean_pct_error = float(np.mean(pct_errors)) if pct_errors else 0
    median_pct_error = float(np.median(pct_errors)) if pct_errors else 0
    
    # Calculate accuracy within thresholds
    within_10pct = sum(1 for e in pct_errors if e <= 10) / len(pct_errors) * 100 if pct_errors else 0
    within_25pct = sum(1 for e in pct_errors if e <= 25) / len(pct_errors) * 100 if pct_errors else 0
    within_50pct = sum(1 for e in pct_errors if e <= 50) / len(pct_errors) * 100 if pct_errors else 0
    
    if verbose:
        print(f"\nEvaluation on {season} players (predicting 01/07/{int(season.split('-')[1])}):")
        print(f"  Samples:           {len(eval_data)}")
        print(f"  RMSE:              €{rmse:.2f}M")
        print(f"  MAE:               €{mae:.2f}M")
        print(f"  R² Score:          {r2:.4f}")
        print(f"  MAPE:              {mean_pct_error:.1f}%")
        print(f"  MdAPE:             {median_pct_error:.1f}%")
        print(f"  Within 10% error:  {within_10pct:.1f}%")
        print(f"  Within 25% error:  {within_25pct:.1f}%")
        print(f"  Within 50% error:  {within_50pct:.1f}%")
        
        # Show sample predictions (top 10 by actual value)
        print(f"\nSample predictions (top 10 by value):")
        print(f"  {'Player':<25} {'Current':>12} {'Predicted':>12} {'Actual':>12} {'Error %':>10}")
        print(f"  {'-'*25} {'-'*12} {'-'*12} {'-'*12} {'-'*10}")
        
        sorted_by_value = sorted(
            zip(eval_data, predictions, actuals),
            key=lambda x: x[2],
            reverse=True
        )[:10]
        
        for f, pred, actual in sorted_by_value:
            current = f.current_value
            pct_err = abs(pred - actual) / actual * 100 if actual > 0 else 0
            print(f"  {f.player_name[:25]:<25} €{current/1e6:>10.1f}M €{pred/1e6:>10.1f}M €{actual/1e6:>10.1f}M {pct_err:>9.1f}%")
    
    return {
        "eval_season": season,
        "eval_samples": len(eval_data),
        "eval_rmse_M": rmse,
        "eval_mae_M": mae,
        "eval_r2": r2,
        "eval_mape": mean_pct_error,
        "eval_mdape": median_pct_error,
        "eval_within_10pct": within_10pct,
        "eval_within_25pct": within_25pct,
        "eval_within_50pct": within_50pct,
    }


def _cutoff_to_season(cutoff_date: datetime) -> str:
    """Convert cutoff date to season string."""
    # If cutoff is in July or later, season starts that year
    # If before July, season started previous year
    if cutoff_date.month >= 7:
        start_year = cutoff_date.year
    else:
        start_year = cutoff_date.year - 1
    return f"{start_year}-{start_year + 1}"


def _season_to_int(season: str) -> int:
    """Convert season string to integer for comparison (start year)."""
    return int(season.split("-")[0])


def train_model(
    season: Optional[str] = None,
    cutoff_date: Optional[datetime] = None,
    output_name: Optional[str] = None,
    min_valuations: int = 5,
    verbose: bool = True,
    rebuild_dataset: bool = False,
    cutoff_months: int = 12,
    test_years: int = 1,
    n_jobs: int = 1,
    **xgb_params,
) -> Path:
    """
    Train value prediction model.
    
    Loads (or builds if needed) a complete training dataset, then filters
    to only use data up to and including the target season.
    
    Args:
        season: Season string (e.g., "2023-2024"). Includes cutoff 01/07/2023.
        cutoff_date: Explicit cutoff date. Ignored if season is provided.
        output_name: Optional model filename (without path)
        min_valuations: Minimum valuations required per player per cutoff
        verbose: Print progress
        rebuild_dataset: If True, regenerate dataset even if it exists
        cutoff_months: Months between cutoffs (12=annual, 6=semi-annual)
        test_years: Number of most recent years for validation (temporal split)
        **xgb_params: Additional XGBoost parameters
    
    Returns:
        Path to saved model
    """
    # Determine cutoff and season
    if season:
        cutoff_date = _season_to_cutoff(season)
    elif cutoff_date:
        season = _cutoff_to_season(cutoff_date)
    else:
        raise ValueError("Either season or cutoff_date must be provided")
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"Training Value Prediction Model")
        print(f"Target Season: {season}")
        print(f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d')}")
        print(f"Cutoff frequency: every {cutoff_months} months")
        print(f"Temporal validation: last {test_years} year(s)")
        print(f"Will use data from seasons <= {season}")
        print(f"{'='*60}\n")
    
    # Try to load existing dataset, or build if needed
    full_dataset = None
    if not rebuild_dataset:
        if verbose:
            print(f"Checking for existing dataset (cutoff_months={cutoff_months})...")
        full_dataset = load_training_dataset(cutoff_months=cutoff_months)
    
    if full_dataset is None:
        if verbose:
            if rebuild_dataset:
                print(f"Rebuilding dataset as requested...")
            else:
                print(f"Dataset not found. Building new dataset...")
        
        # Load raw data
        all_valuations = load_all_valuations(verbose=verbose)
        players = load_all_players(verbose=verbose)
        
        if not all_valuations:
            raise ValueError("No valuations found in data directory")
        
        # Load all transfers for club assignment
        if verbose:
            print(f"Loading all transfers for club assignment...")
        from ml.feature_engineering import _load_all_transfers
        all_transfers = _load_all_transfers(verbose=verbose)
        if verbose:
            print(f"  Loaded {len(all_transfers)} transfers")
        
        # Load team -> league mapping for ALL seasons
        if verbose:
            print(f"Loading team league mapping (all seasons)...")
        team_league_mapping = load_team_league_mapping(verbose=verbose)
        if verbose:
            print(f"  Found {len(team_league_mapping)} unique teams across all seasons")
        
        # Build complete training dataset with ALL cutoffs
        if verbose:
            print(f"\nBuilding complete training dataset...")
        
        full_dataset = build_training_dataset(
            all_valuations,
            players=players,
            team_league_mapping=team_league_mapping,
            min_valuations=min_valuations,
            cutoff_months=cutoff_months,
            all_transfers=all_transfers,
            n_jobs=n_jobs,
        )
        
        # Save dataset for future use
        if full_dataset:
            save_training_dataset(full_dataset, cutoff_months=cutoff_months)
    
    if verbose:
        print(f"\nFull dataset: {len(full_dataset)} samples")
    
    # Filter to only use data from seasons BEFORE the target season
    training_data = filter_dataset_for_season(full_dataset, season)
    
    if verbose:
        # Show breakdown by season
        seasons_used = {}
        for f in training_data:
            seasons_used[f.cutoff_season] = seasons_used.get(f.cutoff_season, 0) + 1
        print(f"\nFiltered for training (seasons <= {season}):")
        for s in sorted(seasons_used.keys()):
            print(f"  {s}: {seasons_used[s]} samples")
        print(f"Total training samples: {len(training_data)}")
    
    if len(training_data) < 100:
        raise ValueError(
            f"Insufficient training data ({len(training_data)} samples). "
            "Need at least 100 players with enough valuation history."
        )
    
    # Train model with temporal split
    if verbose:
        print(f"\nTraining XGBoost model...")
    
    predictor = ValuePredictor()
    metrics = predictor.train(
        training_data,
        test_years=test_years,
        verbose=verbose,
        **xgb_params,
    )
    
    # Save model with season name
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    if output_name:
        model_path = MODELS_DIR / output_name
    else:
        model_path = MODELS_DIR / f"value_model_{season}.joblib"
    
    predictor.save(model_path)
    
    if verbose:
        print(f"\nModel saved to: {model_path}")
        
        # Print feature importance
        print(f"\nFeature Importance:")
        importance = predictor.get_feature_importance()
        sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)
        for name, score in sorted_imp[:10]:
            print(f"  {name}: {score:.4f}")
    
    # Evaluate on target season data (the last cutoff)
    # This shows how well the model predicts the target season's values
    if verbose:
        print(f"\n{'='*60}")
        print(f"Evaluating predictions for {season}")
        print(f"{'='*60}")
    
    eval_data = get_samples_for_season(full_dataset, season)
    eval_metrics = _evaluate_predictions(predictor, eval_data, season, verbose)
    metrics.update(eval_metrics)
    
    # Save metrics
    metrics_path = model_path.with_suffix(".json")
    metrics["season"] = season
    metrics["cutoff_date"] = cutoff_date.isoformat()
    metrics["min_valuations"] = min_valuations
    metrics["cutoff_months"] = cutoff_months
    metrics["full_dataset_size"] = len(full_dataset)
    metrics["filtered_dataset_size"] = len(training_data)
    
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    
    if verbose:
        print(f"\nMetrics saved to: {metrics_path}")
    
    return model_path


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Train player value prediction model"
    )
    parser.add_argument(
        "--season",
        type=str,
        default=None,
        help="Season to train for (e.g., 2023-2024). Cutoff will be 01/07 of start year.",
    )
    parser.add_argument(
        "--cutoff",
        type=str,
        default=None,
        help="Alternative: explicit cutoff date (YYYY-MM-DD). Ignored if --season provided.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output model filename (saved to ml/models/)",
    )
    parser.add_argument(
        "--min-valuations",
        type=int,
        default=5,
        help="Minimum valuations per player. Default: 5",
    )
    parser.add_argument(
        "--n-estimators",
        type=int,
        default=200,
        help="Number of XGBoost trees. Default: 200",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=6,
        help="Max tree depth. Default: 6",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.1,
        help="Learning rate. Default: 0.1",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output",
    )
    parser.add_argument(
        "--rebuild-dataset",
        action="store_true",
        help="Rebuild training dataset even if it exists",
    )
    parser.add_argument(
        "--cutoff-months",
        type=int,
        default=12,
        help="Months between cutoffs (12=annual, 6=semi-annual). Default: 12",
    )
    parser.add_argument(
        "--test-years",
        type=int,
        default=1,
        help="Number of most recent years for validation split (temporal). Default: 1",
    )
    parser.add_argument(
        "--n-jobs",
        type=int,
        default=1,
        help="Parallel workers for dataset building (e.g., 4 for 4 cores). Default: 1",
    )
    
    args = parser.parse_args()
    
    # Determine season or cutoff
    season = args.season
    cutoff_date = None
    
    if not season and not args.cutoff:
        # Default to 2023-2024
        season = "2023-2024"
    elif args.cutoff and not season:
        try:
            cutoff_date = datetime.strptime(args.cutoff, "%Y-%m-%d")
        except ValueError:
            print(f"Error: Invalid date format '{args.cutoff}'. Use YYYY-MM-DD")
            sys.exit(1)
    
    # Train
    try:
        model_path =         train_model(
            season=season,
            cutoff_date=cutoff_date,
            output_name=args.output,
            min_valuations=args.min_valuations,
            verbose=not args.quiet,
            rebuild_dataset=args.rebuild_dataset,
            cutoff_months=args.cutoff_months,
            test_years=args.test_years,
            n_jobs=args.n_jobs,
            n_estimators=args.n_estimators,
            max_depth=args.max_depth,
            learning_rate=args.learning_rate,
        )
        
        if not args.quiet:
            print(f"\n{'='*60}")
            print(f"Training complete!")
            print(f"Model: {model_path}")
            print(f"{'='*60}")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
