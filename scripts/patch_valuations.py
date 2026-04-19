import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraping.utils.helpers import load_json_with_parts, save_json_with_parts, list_json_bases

def parse_date(date_str: str):
    if not date_str:
        return datetime.min
    try:
        return datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError:
        return datetime.min

def patch_valuations():
    print("Starting patch for valuations...")
    
    # Identify all bases
    pattern = "valuations_all_*.json"
    base_names = list_json_bases(pattern)
    if not base_names:
        print(f"No files found for pattern {pattern}")
        return
        
    print(f"Found {len(base_names)} base files for valuations.")
    
    # global_data maps player_id -> valuation_id -> item_dict
    global_data: Dict[str, Dict[str, dict]] = {}
    # base_players maps base_name -> set of player_ids
    base_players: Dict[str, Set[str]] = {}
    
    for base in base_names:
        print(f"Loading {base}...")
        data = load_json_with_parts(base)
        
        if not data:
            base_players[base] = set()
            continue
            
        player_ids = set()
        for item in data:
            pid = str(item.get("player_id", ""))
            item_id = str(item.get("valuation_id", ""))
            if not pid or not item_id:
                continue
                
            player_ids.add(pid)
            
            if pid not in global_data:
                global_data[pid] = {}
            
            # Keep the most recent data loaded for this valuation_id
            global_data[pid][item_id] = item
            
        base_players[base] = player_ids
        print(f"  Found {len(player_ids)} unique players in {base}.")
        
    print("\nWriting patched data back to files...")
    for base in base_names:
        print(f"Processing {base}...")
        patched_data = []
        
        for pid in base_players[base]:
            # Get all valuations for this player across all seasons
            player_items = list(global_data[pid].values())
            
            # Sort items by date ascending (oldest first)
            player_items.sort(key=lambda x: parse_date(x.get("valuation_date", "")))
            
            patched_data.extend(player_items)
            
        # Sort the overall list by player_id
        try:
            patched_data.sort(key=lambda x: int(x.get("player_id", 0)))
        except ValueError:
            patched_data.sort(key=lambda x: str(x.get("player_id", "")))
            
        print(f"  Saving {len(patched_data)} total items to {base}...")
        save_json_with_parts(patched_data, base)
        
    print("Finished patching valuations!")

if __name__ == "__main__":
    patch_valuations()
