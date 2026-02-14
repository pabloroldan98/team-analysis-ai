#!/usr/bin/env python3
# scraping_tasks/combine_data.py
"""
Utility script to combine league-specific JSON files into a single _all_ file.

Usage:
    python scraping_tasks/combine_data.py --entity teams --season 2025-2026
    python scraping_tasks/combine_data.py --entity players
    python scraping_tasks/combine_data.py --entity transfers
    python scraping_tasks/combine_data.py --entity valuations
"""
import sys
import json
import glob
import argparse
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraping.utils.helpers import load_json, write_dict_to_json

DATA_DIR = Path(__file__).parent.parent / "data" / "json"


def get_current_season() -> str:
    """Get current season string (e.g., '2025-2026')."""
    today = datetime.now()
    year = today.year
    month = today.month
    if month >= 7:
        return f"{year}-{year + 1}"
    else:
        return f"{year - 1}-{year}"


def combine_entity_files(entity: str, season: str = None) -> int:
    """
    Combine all league-specific files for an entity into a single _all_ file.
    
    Args:
        entity: Entity type (teams, players, transfers, valuations)
        season: Season string (e.g., '2025-2026'). Auto-detected if not provided.
    
    Returns:
        Number of items in combined file
    """
    if season is None:
        season = get_current_season()
    
    # Find all files for this entity (excluding _all_)
    pattern = str(DATA_DIR / f"{entity}_*_{season}.json")
    files = [f for f in glob.glob(pattern) if "_all_" not in f]
    
    if not files:
        print(f"No files found matching: {pattern}")
        return 0
    
    print(f"Found {len(files)} {entity} files to combine:")
    for f in sorted(files):
        print(f"  - {Path(f).name}")
    
    # Combine all data
    combined = []
    # Known ID fields that indicate a single entity object
    entity_id_fields = ["league_id", "team_id", "player_id", "transfer_id", "valuation_id"]
    
    for filepath in files:
        try:
            base = Path(filepath).stem
            data = load_json(base)
            if data is None:
                continue
            if isinstance(data, list):
                # Standard format: list of dicts
                combined.extend(data)
            elif isinstance(data, dict):
                # Check if it's a single entity object (has an ID field)
                is_single_entity = any(id_field in data for id_field in entity_id_fields)
                if is_single_entity:
                    # Single entity dict, add as one item
                    combined.append(data)
                else:
                    # Could be {league: [...]} format, extract lists
                    for value in data.values():
                        if isinstance(value, list):
                            combined.extend(value)
                        elif isinstance(value, dict):
                            combined.append(value)
            else:
                combined.append(data)
        except Exception as e:
            print(f"  Error reading {filepath}: {e}")
    
    # Save combined file (uses part splitting when >90MB)
    file_name = f"{entity}_all_{season}"
    write_dict_to_json(combined, file_name)

    print(f"\nCombined into: {file_name}.json (or _part1, _part2, ... if large)")
    print(f"Total items: {len(combined)}")
    
    return len(combined)


def main():
    parser = argparse.ArgumentParser(description="Combine league JSON files into _all_ file")
    parser.add_argument(
        "--entity",
        required=True,
        choices=["leagues", "teams", "players", "transfers", "valuations"],
        help="Entity type to combine"
    )
    parser.add_argument(
        "--season",
        type=str,
        default=None,
        help="Season (e.g., 2025-2026). Auto-detected if not provided."
    )
    
    args = parser.parse_args()
    
    print(f"=== Combining {args.entity.upper()} files ===")
    count = combine_entity_files(args.entity, args.season)
    
    if count > 0:
        print(f"\n=== Complete ===")
        return 0
    else:
        print(f"\n=== No files to combine ===")
        return 1


if __name__ == "__main__":
    sys.exit(main())
