# scraping/utils/helpers.py
from __future__ import annotations
import csv
import json
import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from difflib import SequenceMatcher
from unidecode import unidecode


ROOT_DIR = Path(__file__).parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
JSON_DIR = DATA_DIR / "json"
CSV_DIR = DATA_DIR / "csv"


def ensure_data_dirs():
    """Ensure data directories exist."""
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    CSV_DIR.mkdir(parents=True, exist_ok=True)


def normalize_string(s: str) -> str:
    """Normalize string for comparison (lowercase, no accents, no special chars)."""
    if not s:
        return ""
    return unidecode(str(s)).lower().replace(" ", "").replace("-", "").replace(".", "")


def similarity_ratio(a: str, b: str) -> float:
    """Calculate similarity ratio between two strings."""
    return SequenceMatcher(None, normalize_string(a), normalize_string(b)).ratio()


def find_similar_string(
    target: str,
    candidates: List[str],
    similarity_threshold: float = 0.8,
    fallback_none: bool = True,
    verbose: bool = False,
) -> Optional[str]:
    """
    Find the most similar string from a list of candidates.
    
    Args:
        target: String to match
        candidates: List of possible matches
        similarity_threshold: Minimum similarity ratio (0-1)
        fallback_none: If True, return None when no match found; otherwise return best match
        verbose: Print debug information
    
    Returns:
        Best matching string or None
    """
    if not target or not candidates:
        return None
    
    target_normalized = normalize_string(target)
    
    # Exact match first
    for c in candidates:
        if normalize_string(c) == target_normalized:
            return c
    
    # Substring match
    for c in candidates:
        c_normalized = normalize_string(c)
        if target_normalized in c_normalized or c_normalized in target_normalized:
            if verbose:
                print(f"Substring match: '{target}' -> '{c}'")
            return c
    
    # Similarity match
    best_match = None
    best_ratio = 0.0
    
    for c in candidates:
        ratio = similarity_ratio(target, c)
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = c
    
    if verbose:
        print(f"Best match for '{target}': '{best_match}' (ratio: {best_ratio:.3f})")
    
    if best_ratio >= similarity_threshold:
        return best_match
    
    return None if fallback_none else best_match


# Team name normalization mapping
TEAM_NAME_MAPPING = {
    # Spanish
    "atletico de madrid": "Atlético de Madrid",
    "atletico madrid": "Atlético de Madrid",
    "atlético madrid": "Atlético de Madrid",
    "atl. madrid": "Atlético de Madrid",
    "atlético": "Atlético de Madrid",
    "real madrid cf": "Real Madrid",
    "fc barcelona": "Barcelona",
    "barça": "Barcelona",
    "athletic club": "Athletic Club",
    "athletic bilbao": "Athletic Club",
    "real sociedad": "Real Sociedad",
    "real betis": "Real Betis",
    "villarreal cf": "Villarreal",
    "sevilla fc": "Sevilla",
    "valencia cf": "Valencia",
    "rcd espanyol": "Espanyol",
    "getafe cf": "Getafe",
    "ca osasuna": "Osasuna",
    "rcd mallorca": "Mallorca",
    "ud las palmas": "Las Palmas",
    "deportivo alavés": "Alavés",
    "real valladolid": "Valladolid",
    "rc celta": "Celta de Vigo",
    "celta de vigo": "Celta de Vigo",
    "cd leganés": "Leganés",
    "girona fc": "Girona",
    "rayo vallecano": "Rayo Vallecano",
    
    # English
    "manchester united fc": "Manchester United",
    "manchester city fc": "Manchester City",
    "liverpool fc": "Liverpool",
    "chelsea fc": "Chelsea",
    "arsenal fc": "Arsenal",
    "tottenham hotspur": "Tottenham",
    "spurs": "Tottenham",
    "newcastle united": "Newcastle",
    "west ham united": "West Ham",
    "aston villa fc": "Aston Villa",
    "brighton & hove albion": "Brighton",
    "wolverhampton wanderers": "Wolves",
    "crystal palace fc": "Crystal Palace",
    "fulham fc": "Fulham",
    "brentford fc": "Brentford",
    "nottingham forest": "Nottm Forest",
    "everton fc": "Everton",
    "bournemouth": "Bournemouth",
    "leicester city": "Leicester",
    "ipswich town": "Ipswich",
    "southampton fc": "Southampton",
    
    # Italian
    "inter milan": "Inter",
    "fc internazionale": "Inter",
    "ac milan": "Milan",
    "juventus fc": "Juventus",
    "ssc napoli": "Napoli",
    "as roma": "Roma",
    "ss lazio": "Lazio",
    "atalanta bc": "Atalanta",
    "acf fiorentina": "Fiorentina",
    "bologna fc": "Bologna",
    "torino fc": "Torino",
    
    # German
    "fc bayern münchen": "Bayern Munich",
    "bayern munich": "Bayern Munich",
    "bayern münchen": "Bayern Munich",
    "borussia dortmund": "Borussia Dortmund",
    "bvb": "Borussia Dortmund",
    "rb leipzig": "RB Leipzig",
    "bayer 04 leverkusen": "Bayer Leverkusen",
    "vfb stuttgart": "Stuttgart",
    "eintracht frankfurt": "Eintracht Frankfurt",
    "borussia m'gladbach": "Borussia M'Gladbach",
    "vfl wolfsburg": "Wolfsburg",
    
    # French
    "paris saint-germain": "PSG",
    "paris sg": "PSG",
    "olympique de marseille": "Marseille",
    "as monaco": "Monaco",
    "olympique lyonnais": "Lyon",
    "losc lille": "Lille",
    
    # Portuguese
    "sl benfica": "Benfica",
    "fc porto": "Porto",
    "sporting cp": "Sporting",
    "sporting portugal": "Sporting",
}


def normalize_team_name(name: str) -> str:
    """
    Normalize team name to a standard format.
    
    Args:
        name: Raw team name
    
    Returns:
        Normalized team name
    """
    if not name:
        return name
    
    normalized = name.strip()
    key = normalize_string(normalized)
    
    # Check mapping
    for pattern, replacement in TEAM_NAME_MAPPING.items():
        if normalize_string(pattern) == key or pattern in key:
            return replacement
    
    return normalized


def write_dict_data(data: Dict[str, Any], file_name: str, as_json: bool = True) -> bool:
    """
    Write dictionary data to file (JSON and/or CSV).
    
    Args:
        data: Dictionary to save
        file_name: Base filename without extension
        as_json: Whether to save as JSON (default True)
    
    Returns:
        True if successful
    """
    ensure_data_dirs()
    
    try:
        if as_json:
            json_path = JSON_DIR / f"{file_name}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        
        return True
    except Exception as e:
        print(f"Error writing data to {file_name}: {e}")
        return False


def read_dict_data(file_name: str) -> Optional[Dict[str, Any]]:
    """
    Read dictionary data from JSON file.
    
    Args:
        file_name: Base filename without extension
    
    Returns:
        Dictionary or None if file doesn't exist
    """
    json_path = JSON_DIR / f"{file_name}.json"
    
    if not json_path.exists():
        return None
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading data from {file_name}: {e}")
        return None


def overwrite_dict_data(
    data: Dict[str, Any],
    file_name: str,
    ignore_old_data: bool = False,
) -> bool:
    """
    Overwrite or merge dictionary data to file.
    
    Args:
        data: New dictionary data
        file_name: Base filename without extension
        ignore_old_data: If True, completely replace; otherwise merge
    
    Returns:
        True if successful
    """
    if not ignore_old_data:
        old_data = read_dict_data(file_name)
        if old_data:
            old_data.update(data)
            data = old_data
    
    return write_dict_data(data, file_name)


def write_list_to_csv(data: List[Dict], file_name: str, fieldnames: Optional[List[str]] = None) -> bool:
    """
    Write list of dictionaries to CSV file.
    
    Args:
        data: List of dictionaries
        file_name: Base filename without extension
        fieldnames: Optional list of column names (auto-detect if None)
    
    Returns:
        True if successful
    """
    ensure_data_dirs()
    
    if not data:
        return False
    
    try:
        if fieldnames is None:
            fieldnames = list(data[0].keys())
        
        csv_path = CSV_DIR / f"{file_name}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        
        return True
    except Exception as e:
        print(f"Error writing CSV to {file_name}: {e}")
        return False


def read_list_from_csv(file_name: str) -> Optional[List[Dict]]:
    """
    Read list of dictionaries from CSV file.
    
    Args:
        file_name: Base filename without extension
    
    Returns:
        List of dictionaries or None
    """
    csv_path = CSV_DIR / f"{file_name}.csv"
    
    if not csv_path.exists():
        return None
    
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception as e:
        print(f"Error reading CSV from {file_name}: {e}")
        return None


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
    
    # Extract number from string like "25" or "(25)"
    match = re.search(r"\d+", str(age_str))
    if match:
        return int(match.group())
    return None


def parse_height(height_str: str) -> Optional[int]:
    """Parse height string to cm."""
    if not height_str:
        return None
    
    height_str = str(height_str).strip().lower()
    
    # Format: "1,85 m" or "1.85m" or "185 cm" or "185"
    if "cm" in height_str:
        match = re.search(r"(\d+)", height_str)
        if match:
            return int(match.group(1))
    
    # Meters format
    match = re.search(r"(\d)[,.](\d{2})", height_str)
    if match:
        return int(match.group(1)) * 100 + int(match.group(2))
    
    # Just a number (assume cm if > 100, else meters)
    match = re.search(r"(\d+)", height_str)
    if match:
        val = int(match.group(1))
        return val if val > 100 else val * 100
    
    return None


def get_season_year(season: str) -> int:
    """
    Get the starting year of a season.
    
    Examples:
        "2024-2025" -> 2024
        "2024/25" -> 2024
        "2024" -> 2024
    """
    if not season:
        from datetime import datetime
        return datetime.now().year
    
    match = re.search(r"(\d{4})", str(season))
    if match:
        return int(match.group(1))
    
    return 2024  # Default


def format_season(year: int) -> str:
    """Format season string from starting year."""
    return f"{year}-{year + 1}"
