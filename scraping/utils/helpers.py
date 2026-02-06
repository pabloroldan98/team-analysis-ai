# scraping/utils/helpers.py
"""
Utility functions for scraping and file management.
Based on useful_functions.py from knapsack-football-formations.
"""
from __future__ import annotations
import json
import os
import re
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from difflib import SequenceMatcher
from unidecode import unidecode


ROOT_DIR = Path(__file__).parent.parent.parent
DATA_DIR = ROOT_DIR / "data"


# =============================================================================
# FILE OPERATIONS WITH VALIDATION AND BACKUP
# =============================================================================

def ensure_data_dir():
    """Ensure data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def write_dict_to_json(data: Any, file_name: str) -> bool:
    """
    Write data to JSON file.
    
    Args:
        data: Data to save (dict, list, etc.)
        file_name: Base filename without extension
    
    Returns:
        True if successful
    """
    ensure_data_dir()
    file_path = DATA_DIR / f"{file_name}.json"
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return True
    except Exception as e:
        print(f"Error writing to {file_name}: {e}")
        return False


def read_dict_from_json(file_name: str) -> Optional[Any]:
    """
    Read data from JSON file.
    
    Args:
        file_name: Base filename without extension
    
    Returns:
        Data or None if file doesn't exist
    """
    file_path = DATA_DIR / f"{file_name}.json"
    
    if not file_path.exists():
        return None
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading from {file_name}: {e}")
        return None


# Aliases for compatibility
write_dict_data = write_dict_to_json
read_dict_data = read_dict_from_json


def is_valid_data(
    data: Any,
    min_items: int = 10,
    min_players_per_team: int = 11,
    data_type: str = "teams"
) -> bool:
    """
    Validate scraped data to ensure it has minimum required content.
    
    Args:
        data: Data to validate (list or dict)
        min_items: Minimum number of items (teams, players, etc.)
        min_players_per_team: Minimum players per team (for team data)
        data_type: Type of data ("teams", "players", "transfers", "logos")
    
    Returns:
        True if data is valid
    """
    if data is None:
        return False
    
    # List format (our standard format)
    if isinstance(data, list):
        if len(data) < min_items:
            return False
        
        # For teams, check if they have player counts
        if data_type == "teams":
            for item in data:
                if isinstance(item, dict):
                    squad_size = item.get("squad_size", 0) or 0
                    if squad_size < min_players_per_team:
                        # Allow some teams with incomplete data
                        continue
        return True
    
    # Dict format (league -> items)
    if isinstance(data, dict):
        if len(data) < 1:
            return False
        
        total_items = 0
        for key, items in data.items():
            if isinstance(items, list):
                total_items += len(items)
            elif isinstance(items, dict):
                total_items += len(items)
        
        return total_items >= min_items
    
    return False


def merge_with_old_data(
    new_data: List[Dict],
    old_data: List[Dict],
    id_field: str = "team_id"
) -> List[Dict]:
    """
    Merge new data with old data, keeping items from old that are missing in new.
    
    Args:
        new_data: New scraped data
        old_data: Previous data
        id_field: Field to use as unique identifier
    
    Returns:
        Merged data list
    """
    if not old_data:
        return new_data
    
    if not new_data:
        return old_data
    
    # Create lookup by ID
    new_ids = {item.get(id_field) for item in new_data if item.get(id_field)}
    
    # Add missing items from old data
    merged = list(new_data)
    for old_item in old_data:
        old_id = old_item.get(id_field)
        if old_id and old_id not in new_ids:
            merged.append(old_item)
            print(f"  Recovered from old data: {old_item.get('name', old_id)}")
    
    return merged


def overwrite_dict_data(
    data: Any,
    file_name: str,
    ignore_valid_file: bool = True,
    ignore_old_data: bool = False,
    min_items: int = 10,
    id_field: str = "team_id",
    data_type: str = "teams"
) -> bool:
    """
    Overwrite JSON file with validation and backup.
    
    - Creates _OLD backup of previous file
    - Validates new data before overwriting
    - Merges with old data if new data is incomplete
    
    Args:
        data: New data to save
        file_name: Base filename without extension
        ignore_valid_file: If True, always save (skip validation)
        ignore_old_data: If True, don't merge with old data
        min_items: Minimum items for validation
        id_field: Field for unique ID when merging
        data_type: Type of data for validation
    
    Returns:
        True if successful
    """
    ensure_data_dir()
    
    file_path = DATA_DIR / f"{file_name}.json"
    file_path_old = DATA_DIR / f"{file_name}_OLD.json"
    
    # Read old data for potential merge
    old_data = None
    if not ignore_old_data and file_path.exists():
        old_data = read_dict_from_json(file_name)
    
    # Validate new data
    if not ignore_valid_file:
        if not is_valid_data(data, min_items=min_items, data_type=data_type):
            print(f"Warning: New data for {file_name} failed validation")
            
            # Try to merge with old data
            if old_data and isinstance(data, list) and isinstance(old_data, list):
                print(f"  Attempting to merge with old data...")
                data = merge_with_old_data(data, old_data, id_field)
                
                # Re-validate after merge
                if not is_valid_data(data, min_items=min_items, data_type=data_type):
                    print(f"  Still invalid after merge. Skipping save.")
                    return False
            else:
                return False
    
    # Merge with old data if requested
    if not ignore_old_data and old_data:
        if isinstance(data, list) and isinstance(old_data, list):
            data = merge_with_old_data(data, old_data, id_field)
    
    # Create backup of current file
    if file_path.exists():
        try:
            # Remove old backup if exists
            if file_path_old.exists():
                os.remove(file_path_old)
            
            # Copy current to _OLD
            shutil.copy(file_path, file_path_old)
            print(f"  Backup created: {file_name}_OLD.json")
            
            # Remove current
            os.remove(file_path)
        except Exception as e:
            print(f"  Warning: Could not create backup: {e}")
    
    # Write new data
    return write_dict_to_json(data, file_name)


def delete_file(file_name: str) -> bool:
    """
    Delete a JSON file.
    
    Args:
        file_name: Base filename without extension
    
    Returns:
        True if deleted successfully
    """
    file_path = DATA_DIR / f"{file_name}.json"
    
    try:
        if file_path.exists():
            os.remove(file_path)
            print(f"File '{file_path}' deleted successfully.")
            return True
        else:
            print(f"File '{file_path}' not found.")
            return False
    except PermissionError:
        print(f"Permission denied: Unable to delete '{file_path}'.")
        return False
    except Exception as e:
        print(f"Error deleting '{file_path}': {e}")
        return False


def list_json_files(pattern: str = "*.json") -> List[str]:
    """
    List JSON files in data directory.
    
    Args:
        pattern: Glob pattern (default: "*.json")
    
    Returns:
        List of filenames (without extension)
    """
    if not DATA_DIR.exists():
        return []
    
    files = []
    for f in DATA_DIR.glob(pattern):
        if not f.name.endswith("_OLD.json"):
            files.append(f.stem)
    
    return sorted(files)


# =============================================================================
# PARSING UTILITIES
# =============================================================================

def parse_market_value(value_str: str) -> Optional[float]:
    """
    Parse market value string to float (in euros).
    
    Examples:
        "€50.00m" -> 50000000
        "€800k" -> 800000
        "€1.2bn" -> 1200000000
    """
    if not value_str:
        return None
    
    value_str = value_str.strip().lower().replace(",", ".").replace(" ", "")
    
    # Remove currency symbol
    value_str = re.sub(r"[€$£]", "", value_str)
    
    multiplier = 1
    if "bn" in value_str or "b" in value_str:
        multiplier = 1_000_000_000
        value_str = re.sub(r"bn?", "", value_str)
    elif "m" in value_str or "mill" in value_str:
        multiplier = 1_000_000
        value_str = re.sub(r"m(ill)?", "", value_str)
    elif "k" in value_str or "th" in value_str:
        multiplier = 1_000
        value_str = re.sub(r"k|th", "", value_str)
    
    try:
        return float(value_str) * multiplier
    except ValueError:
        return None


def parse_age(age_str: str) -> Optional[int]:
    """Parse age string to integer."""
    if not age_str:
        return None
    
    match = re.search(r"\d+", str(age_str))
    if match:
        return int(match.group())
    return None


def parse_height(height_str: str) -> Optional[int]:
    """Parse height string to cm."""
    if not height_str:
        return None
    
    height_str = str(height_str).strip().lower()
    
    if "cm" in height_str:
        match = re.search(r"(\d+)", height_str)
        if match:
            return int(match.group(1))
    
    match = re.search(r"(\d)[,.](\d{2})", height_str)
    if match:
        return int(match.group(1)) * 100 + int(match.group(2))
    
    match = re.search(r"(\d+)", height_str)
    if match:
        val = int(match.group(1))
        return val if val > 100 else val * 100
    
    return None


def get_season_year(season: str) -> int:
    """Get the starting year of a season."""
    if not season:
        from datetime import datetime
        return datetime.now().year
    
    match = re.search(r"(\d{4})", str(season))
    if match:
        return int(match.group(1))
    
    return 2024


def format_season(year: int) -> str:
    """Format season string from starting year."""
    return f"{year}-{year + 1}"
