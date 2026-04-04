import os
import json
from collections import defaultdict

from scraping.utils.helpers import load_json_with_parts, save_json_with_parts, list_json_bases

# Keys that should NEVER be patched across different seasons because they are season-specific
SKIP_KEYS = {
    "season",
    "age",
    "team",
    "team_id",
    "market_value",
    "shirt_number",
    "on_loan",
    "loaning_team",
    "loaning_team_id",
    "predicted_value",
    
    # Competition specific
    "team_name",
    "position",
    "matches_played",
    "wins",
    "draws",
    "losses",
    "goals_for",
    "goals_against",
    "goal_difference",
    "points",
    
    # League specific
    "total_market_value",
    "num_teams",
    "num_players",
    "average_age",
    "average_market_value",
    "most_valuable_player",
    
    # Transfer specific
    "from_club_name",
    "from_club_id",
    "to_club_name",
    "to_club_id",
    "price",
    "price_str",
    "transfer_date",
    "transfer_type",
    "is_loan",
    "market_value_at_transfer",
    
    # Valuation specific
    "valuation_amount",
    "valuation_date",
    "club_name_at_valuation",
    "club_id_at_valuation",
    "age_at_valuation",
}

def is_empty(val):
    if val is None:
        return True
    if isinstance(val, str) and val.strip() == "":
        return True
    if isinstance(val, list) and len(val) == 0:
        return True
    return False

def make_hashable(val):
    if isinstance(val, list):
        return tuple(val)
    if isinstance(val, dict):
        return tuple(sorted(val.items()))
    return val

def process_entity_files(prefix, id_field):
    print(f"\nProcessing {prefix}...")
    
    pattern = f"{prefix}_all_*.json"
    base_names = list_json_bases(pattern)
    
    if not base_names:
        print(f"No files found for {prefix}")
        return

    # files_data maps base_name -> list of items (or dict of items)
    files_data = {}
    entity_map = defaultdict(list)

    for base in base_names:
        print(f"Loading {base}...")
        try:
            data = load_json_with_parts(base)
            if data is None:
                continue
                
            files_data[base] = data
            
            # load_json_with_parts always returns the actual data (list for players/transfers, dict for some others)
            # but usually it's a list for _all_ files
            items = data if isinstance(data, list) else data.get("items", []) if isinstance(data, dict) else []
            
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                eid = item.get(id_field)
                if eid:
                    entity_map[eid].append((base, i, item))
        except Exception as e:
            print(f"Error loading {base}: {e}")

    total_patches = 0
    # For each unique ID across all years
    for eid, occurrences in entity_map.items():
        if len(occurrences) <= 1:
            continue
            
        all_keys = set()
        for _, _, item in occurrences:
            all_keys.update(item.keys())
            
        for key in all_keys:
            if key in SKIP_KEYS:
                continue
                
            non_empty_values = set()
            val_to_original = {}
            
            for _, _, item in occurrences:
                val = item.get(key)
                if not is_empty(val):
                    try:
                        h_val = make_hashable(val)
                        non_empty_values.add(h_val)
                        val_to_original[h_val] = val
                    except TypeError:
                        pass # Ignore unhashable types
                    
            if len(non_empty_values) == 1:
                patch_val = list(val_to_original.values())[0]
                
                for base, i, item in occurrences:
                    if is_empty(item.get(key)):
                        item[key] = patch_val
                        total_patches += 1

    print(f"Total patches applied for {prefix}: {total_patches}")
    
    if total_patches > 0:
        for base, data in files_data.items():
            print(f"Saving {base}...")
            save_json_with_parts(data, base)
    else:
        print(f"No patches needed for {prefix}.")

def main():
    entities = [
        ("players", "player_id"),
        ("teams", "team_id"),
        ("leagues", "league_id"),
        ("competitions", "competition_id"),
        ("transfers", "transfer_id"),
        ("valuations", "valuation_id"),
        ("injuries", "injury_id"),
    ]
    
    for prefix, id_field in entities:
        process_entity_files(prefix, id_field)

if __name__ == "__main__":
    main()
