# scraping/utils/helpers.py
"""
Utility functions for scraping and file management.
Based on useful_functions.py from knapsack-football-formations.
"""
from __future__ import annotations
import json
import os
import re

try:
    import orjson
    _HAS_ORJSON = True
except ImportError:
    _HAS_ORJSON = False
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from difflib import SequenceMatcher
from unidecode import unidecode


ROOT_DIR = Path(__file__).parent.parent.parent
DATA_DIR = ROOT_DIR / "data" / "json"

# Maximum file size per part (90 MB leaves headroom under GitHub's 100 MB limit)
MAX_JSON_PART_BYTES = 90 * 1024 * 1024


# =============================================================================
# FILE OPERATIONS WITH VALIDATION AND BACKUP
# =============================================================================

def ensure_data_dir():
    """Ensure data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_json_base_path(file_name: str) -> Path:
    """Return full path for base JSON file (with .json extension)."""
    return DATA_DIR / f"{file_name}.json"


def _get_json_part_paths(file_name: str) -> List[Path]:
    """
    Return sorted list of existing part files for a dataset.
    Parts follow the pattern ``<file_name>_part1.json``, ``<file_name>_part2.json``, …
    Falls back to the single-file ``<file_name>.json`` if no parts exist.
    Returns empty list if nothing exists.
    """
    base_path = _get_json_base_path(file_name)
    stem = base_path.stem  # file_name (no .json)
    parts = sorted(DATA_DIR.glob(f"{stem}_part*.json"))
    # Filter out _OLD backups
    parts = [p for p in parts if "_OLD" not in p.stem]
    if parts:
        return parts
    if base_path.exists():
        return [base_path]
    return []


def save_json_with_parts(
    data: Any,
    file_name: str,
    max_part_bytes: int = MAX_JSON_PART_BYTES,
) -> bool:
    """
    Save data to JSON, splitting into parts when size exceeds max_part_bytes.

    For lists: when serialized size > max_part_bytes, saves as ``<file>_part1.json``,
    ``<file>_part2.json``, … with format ``{"metadata": {...}, "items": [...]}``.
    For dicts or small lists: saves as single file (backward compatible).

    Args:
        data: Data to save (list or dict)
        file_name: Base filename without extension
        max_part_bytes: Maximum bytes per part file (default 90 MB)

    Returns:
        True if successful
    """
    ensure_data_dir()
    base_path = _get_json_base_path(file_name)

    def _write_single(blob: bytes, path: Path) -> bool:
        try:
            with open(path, "wb") as f:
                f.write(blob)
            return True
        except Exception as e:
            print(f"Error writing to {path.name}: {e}")
            return False

    # Serialize to measure size
    full_blob = json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8")

    if len(full_blob) <= max_part_bytes:
        # Single file: remove old parts
        for old_part in DATA_DIR.glob(f"{base_path.stem}_part*.json"):
            if "_OLD" not in old_part.stem:
                try:
                    old_part.unlink()
                except OSError:
                    pass
        return _write_single(full_blob, base_path)

    # Split into parts (only for lists)
    if not isinstance(data, list):
        # Dict or other: save as single file anyway (may exceed limit)
        return _write_single(full_blob, base_path)

    # Remove legacy single file and old parts
    if base_path.exists():
        base_path.unlink()
    for old_part in DATA_DIR.glob(f"{base_path.stem}_part*.json"):
        if "_OLD" not in old_part.stem:
            try:
                old_part.unlink()
            except OSError:
                pass

    metadata = {
        "num_items": len(data),
        "created_at": datetime.now().isoformat(),
    }

    # Build chunks so each part stays under max_part_bytes (iterative size-based split)
    def _serialize_chunk(chunk: List[Any], part_num: int, total: int) -> bytes:
        part_meta = {**metadata, "part": part_num, "total_parts": total}
        part_output = {"metadata": part_meta, "items": chunk}
        return json.dumps(part_output, ensure_ascii=False, indent=2, default=str).encode("utf-8")

    chunks: List[List[Any]] = []
    start = 0
    avg_bytes_per_item = len(full_blob) / len(data) if data else 0
    # Reserve ~2KB for metadata
    target_bytes = max(1, max_part_bytes - 2048)

    while start < len(data):
        remaining = len(data) - start
        # Estimate chunk size from average, with 5% safety margin
        est_count = int(target_bytes / avg_bytes_per_item * 0.95) if avg_bytes_per_item else remaining
        est_count = max(1, min(est_count, remaining))

        chunk = data[start : start + est_count]
        blob = _serialize_chunk(chunk, len(chunks) + 1, 0)
        # Shrink until it fits
        while len(blob) > max_part_bytes and len(chunk) > 1:
            est_count = max(1, int(est_count * 0.9))
            chunk = data[start : start + est_count]
            blob = _serialize_chunk(chunk, len(chunks) + 1, 0)
        if len(blob) > max_part_bytes:
            chunk = data[start : start + 1]  # Single item exceeds limit – take one anyway
        chunks.append(chunk)
        start += len(chunk)

    # Write each chunk
    for i, chunk in enumerate(chunks):
        part_meta = {**metadata, "part": i + 1, "total_parts": len(chunks)}
        part_output = {"metadata": part_meta, "items": chunk}
        part_path = DATA_DIR / f"{base_path.stem}_part{i + 1}.json"
        try:
            with open(part_path, "w", encoding="utf-8") as f:
                json.dump(part_output, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            print(f"Error writing to {part_path.name}: {e}")
            return False

    return True


def load_json_with_parts(file_name: str) -> Optional[Any]:
    """
    Load data from JSON file(s), supporting both single file and multi-part.

    For part files (``<file>_part1.json``, …): concatenates ``items`` and returns the list.
    For single file: returns the raw content (list or dict).

    Args:
        file_name: Base filename without extension

    Returns:
        Data or None if no file(s) exist
    """
    paths = _get_json_part_paths(file_name)
    if not paths:
        return None

    def _read_json(path: Path) -> Any:
        """Load JSON from path. Uses orjson when available (~5-10x faster)."""
        if _HAS_ORJSON:
            with open(path, "rb") as f:
                return orjson.loads(f.read())
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    if len(paths) == 1 and "_part" not in paths[0].stem:
        # Single file (legacy or small)
        try:
            raw = _read_json(paths[0])
            # Support wrapped format from old part files that were later saved as single
            if isinstance(raw, dict) and "items" in raw and "metadata" in raw:
                return raw["items"]
            return raw
        except Exception as e:
            print(f"Error reading from {paths[0].name}: {e}")
            return None

    # Multi-part
    all_items: List[Any] = []
    for pp in paths:
        try:
            data = _read_json(pp)
            if isinstance(data, dict) and "items" in data:
                all_items.extend(data["items"])
            else:
                all_items.append(data)
        except Exception as e:
            print(f"Error reading from {pp.name}: {e}")
            return None

    return all_items


def write_dict_to_json(data: Any, file_name: str) -> bool:
    """
    Write data to JSON file.
    Uses part splitting when data exceeds 90 MB (for lists).

    Args:
        data: Data to save (dict, list, etc.)
        file_name: Base filename without extension

    Returns:
        True if successful
    """
    return save_json_with_parts(data, file_name)


def load_json(file_name: str) -> Optional[Any]:
    """
    Load data from JSON file(s) in data/json.
    Supports single file and multi-part (``*_part1.json``, …).

    Args:
        file_name: Base filename without extension (e.g. "players_all_2024-2025")

    Returns:
        Data (list, dict, etc.) or None if file(s) don't exist
    """
    return load_json_with_parts(file_name)


# Aliases for backward compatibility
read_dict_from_json = load_json
read_dict_data = load_json
write_dict_data = write_dict_to_json


def load_entity_all_from_all_years(
    entity: str,
    id_field: str,
    current_season: str = None,
) -> tuple[set, Dict[str, List[dict]], List[dict]]:
    """
    Load all ``{entity}_all_*.json`` files from every season.
    Used for --use-downloaded-data to skip and fill from any year.

    Args:
        entity: Base name (e.g. "transfers", "valuations", "players")
        id_field: Field to use as unique ID (e.g. "player_id")
        current_season: Optional season for current-season records (e.g. "2024-2025")

    Returns:
        (skip_ids, id_to_records, current_season_records)
        - skip_ids: set of IDs we already have data for (from any year)
        - id_to_records: mapping id -> list of records (for filling when skipping)
        - current_season_records: records from current season only (for merge)
    """
    pattern = f"{entity}_all_*.json"
    bases = list_json_bases(pattern)
    if not bases:
        return set(), {}, []

    skip_ids: set = set()
    id_to_records: Dict[str, List[dict]] = {}
    current_season_records: List[dict] = []
    seen_record_ids: set = set()  # for deduplication (e.g. transfer_id)

    for base in bases:
        data = load_json(base)
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            rid = item.get(id_field)
            if not rid:
                continue
            rid = str(rid)
            skip_ids.add(rid)

            # Current season records for merge (before dedup so we capture all)
            if current_season and base.endswith(f"_{current_season}"):
                current_season_records.append(item)

            # Build id_to_records with deduplication
            record_key = item.get("transfer_id") or item.get("valuation_id") or id(item)
            if record_key in seen_record_ids:
                continue
            seen_record_ids.add(record_key)

            if rid not in id_to_records:
                id_to_records[rid] = []
            id_to_records[rid].append(item)

    return skip_ids, id_to_records, current_season_records


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
        data_type: Type of data ("teams", "players", "transfers", "valuations", "leagues")
    
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
    
    # Dict format
    if isinstance(data, dict):
        if len(data) < 1:
            return False
        
        # Check if it's a single entity object (e.g., a League with league_id)
        # These have known ID fields as keys, not nested collections
        entity_id_fields = ["league_id", "team_id", "player_id", "transfer_id", "valuation_id"]
        for id_field in entity_id_fields:
            if id_field in data:
                # It's a single entity object - validate it has required fields
                if data_type == "leagues":
                    # League must have at least league_id and name
                    return bool(data.get("league_id") and data.get("name"))
                elif data_type == "teams":
                    return bool(data.get("team_id") and data.get("name"))
                elif data_type == "players":
                    return bool(data.get("player_id") and data.get("name"))
                # Generic: just having the ID field is enough
                return True
        
        # Dict format (league -> items) for nested structures
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

    # Read old data for potential merge (supports single and part files)
    old_data = None
    existing_paths = _get_json_part_paths(file_name)
    if not ignore_old_data and existing_paths:
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
    
    # Create backup of current file(s) and remove them
    if existing_paths:
        try:
            for path in existing_paths:
                backup_path = path.parent / f"{path.stem}_OLD.json"
                if backup_path.exists():
                    backup_path.unlink()
                shutil.copy(path, backup_path)
                print(f"  Backup created: {backup_path.name}")
                path.unlink()
        except Exception as e:
            print(f"  Warning: Could not create backup: {e}")

    # Write new data (single or parts)
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


def list_json_bases(glob_pattern: str = "*.json") -> List[str]:
    """
    Return unique base names for JSON files, treating _part1, _part2 as one logical file.
    E.g. players_all_2024_part1.json + players_all_2024_part2.json -> "players_all_2024".

    Args:
        glob_pattern: Glob pattern (e.g. "players_all_*.json")

    Returns:
        Sorted list of unique base names (without .json, without _partN)
    """
    if not DATA_DIR.exists():
        return []
    seen = set()
    for f in DATA_DIR.glob(glob_pattern):
        if f.suffix != ".json" or "_OLD" in f.stem:
            continue
        base = re.sub(r"_part\d+$", "", f.stem)
        seen.add(base)
    return sorted(seen)


# =============================================================================
# PARSING UTILITIES
# =============================================================================

def parse_date(date_str: str):
    """Parse a date string in DD/MM/YYYY or YYYY-MM-DD format.

    Returns a ``datetime`` object or ``None`` if the string cannot be
    parsed.
    """
    from datetime import datetime as _dt

    if not date_str:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return _dt.strptime(date_str, fmt)
        except ValueError:
            continue
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
