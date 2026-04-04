import os
import json
import time
from pathlib import Path
from typing import Dict, Tuple
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

from scraping.transfermarkt_players import TransfermarktPlayersScraper
from scraping.utils.helpers import load_json_with_parts, save_json_with_parts, DATA_DIR, list_json_bases

def patch_players():
    base_names = list_json_bases("players_*.json")
    if not base_names:
        print("No players JSON files found.")
        return

    cache_file = DATA_DIR / "patch_dates_cache.json"
    
    # Load from backup if cache is empty to avoid restarting from scratch
    backup_file = DATA_DIR / "patch_dates_cache.json.bak"
    if not cache_file.exists() and backup_file.exists():
        print("Restoring from backup...")
        import shutil
        shutil.copy(backup_file, cache_file)
        
    cache = {}
    if cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            try:
                cache = json.load(f)
                print(f"Loaded {len(cache)} players from cache.")
            except json.JSONDecodeError:
                print("Cache file is corrupted, starting fresh.")
                cache = {}
                
    scraper = TransfermarktPlayersScraper()
    # Suppress verbose logging
    scraper.verbose = False
    
    print("Collecting unique players and teams...")
    files_data = {}
    unique_player_ids = set()
    unique_team_ids = set()
    
    for base in base_names:
        data = load_json_with_parts(base)
        if data:
            files_data[base] = data
            for player in data:
                pid = player.get("player_id")
                if pid:
                    pid_str = str(pid)
                    unique_player_ids.add(pid_str)
                    # Check if already has meaningful date data (must look like dates, e.g., contains "/")
                    has_date = player.get("signed_date") and "/" in str(player.get("signed_date"))
                    has_contract = player.get("contract_end_date") and "/" in str(player.get("contract_end_date"))
                    
                    # Use existing data if already there and valid
                    if pid_str not in cache and (has_date or has_contract):
                        cache[pid_str] = {
                            "signed_date": player.get("signed_date") if has_date else None,
                            "contract_end_date": player.get("contract_end_date") if has_contract else None
                        }
                tid = player.get("team_id")
                if tid:
                    unique_team_ids.add(str(tid))
                    
    print(f"Found {len(unique_player_ids)} unique players and {len(unique_team_ids)} teams across {len(base_names)} files.")

    # Clean up any bad cache entries before doing more work
    for pid in list(cache.keys()):
        if str(cache[pid].get("signed_date")).lower() in ["-", "", "?", "none", "right", "left", "both"] or "?" in str(cache[pid].get("signed_date")):
            cache[pid]["signed_date"] = None
        if str(cache[pid].get("contract_end_date")).lower() in ["-", "", "?", "none", "right", "left", "both"] or "?" in str(cache[pid].get("contract_end_date")):
            cache[pid]["contract_end_date"] = None
    
    # Build team_id -> player_ids map
    team_players = {}
    for base, data in files_data.items():
        for player in data:
            tid = player.get("team_id")
            pid = player.get("player_id")
            if tid and pid:
                tid_str = str(tid)
                pid_str = str(pid)
                if tid_str not in team_players:
                    team_players[tid_str] = set()
                team_players[tid_str].add(pid_str)
                
    # 1. First scrape teams to get multiple players at once
    # Only scrape teams if we have players missing from cache
    missing_players = unique_player_ids - set(cache.keys())
    
    # We will skip team scraping as requested, since we already did a full pass
    SKIP_TEAM_SCRAPING = True
    
    teams_to_scrape = []
    if not SKIP_TEAM_SCRAPING and missing_players and unique_team_ids:
        print(f"Scraping teams to find missing players...")
        save_interval = 5
        
        teams_to_scrape = []
        for tid in unique_team_ids:
            # Check if team has players missing from cache
            has_missing = False
            for pid in team_players.get(str(tid), []):
                if pid not in cache or (cache[pid].get("signed_date") is None and cache[pid].get("contract_end_date") is None):
                    has_missing = True
                    break
            if has_missing:
                teams_to_scrape.append(tid)
            
    print(f"Actually scraping {len(teams_to_scrape)} teams with missing players")
    
    # We will save cache every N teams (approx 4 teams = 100 players)
    save_interval = 10
    
    # Optional: If teams are taking too long, we might just be getting timed out.
    # The scraping process might be hitting limits. Let's add some basic error counting.
    error_count = 0
    
    for i, tid in enumerate(tqdm(teams_to_scrape, desc="Scraping teams")):
        try:
            # Very small delay just to avoid overwhelming CPU
            time.sleep(0.1)
            
            url = f"{scraper.BASE_URL}/-/kader/verein/{tid}/saison_id/{scraper.season_year}/plus/1"
            soup = scraper.fetch_page(url)
            if not soup:
                continue
                
            for row in soup.select("table.items tbody tr.odd, table.items tbody tr.even"):
                # Get player ID
                player_link = row.select_one("td.hauptlink a[href*='/spieler/']")
                if not player_link:
                    continue
                
                href = player_link.get("href", "")
                pid = scraper.extract_player_id(href)
                # Only get player IDs that are in unique_player_ids
                # and that we haven't already cached fully (both dates)
                if not pid or pid not in unique_player_ids:
                    continue
                if pid in cache and cache[pid].get("signed_date") and cache[pid].get("contract_end_date"):
                    continue
                    
                # Signed date (Fichado) - 7th column in the extended table
                # Columns: #, Player, Age, Nat, Height, Foot, Joined, Prev. Club, Contract, Market Value
                signed_date = None
                contract_end_date = None
                
                cells = row.find_all("td", recursive=False)
                if len(cells) >= 9:
                    # The columns typically look like this in extended view:
                    # 0: Number
                    # 1: Player/Position
                    # 2: Age
                    # 3: Nat.
                    # 4: Height
                    # 5: Foot
                    # 6: Joined (Signed Date)
                    # 7: Prev Club
                    # 8: Contract End
                    # 9: Market Value
                    
                    # Safely extract from expected indices
                    try:
                        # Joined date is index 6
                        joined_cell = cells[6]
                        joined_text = joined_cell.get_text(strip=True)
                        
                        # Clean up text first to avoid storing "-" or similar
                        if joined_text in ["-", "", "?"] or "?" in joined_text:
                            signed_date = None
                        elif "cedido" not in joined_text.lower():
                            # Basic date format check DD/MM/YYYY
                            if len(joined_text.split("/")) == 3:
                                signed_date = joined_text
                            else:
                                # Make sure it contains numbers, not just text like "right" or "left" (from foot column)
                                import re
                                if re.search(r'\d', joined_text):
                                    signed_date = joined_text
                                else:
                                    signed_date = None
                        else:
                            signed_date = None
                                
                        # Contract date is index 8
                        contract_cell = cells[8]
                        contract_text = contract_cell.get_text(strip=True)
                        
                        if contract_text in ["-", "", "?"] or "?" in contract_text:
                            contract_end_date = None
                        elif "cedido" not in contract_text.lower():
                            if len(contract_text.split("/")) == 3:
                                contract_end_date = contract_text
                            else:
                                # Make sure it contains numbers
                                import re
                                if re.search(r'\d', contract_text):
                                    contract_end_date = contract_text
                                else:
                                    contract_end_date = None
                        else:
                            contract_end_date = None
                            
                        # Final strict check before storing, avoid assigning "left", "right", "both"
                        import re
                        if signed_date and not re.search(r'\d', signed_date):
                            signed_date = None
                        if contract_end_date and not re.search(r'\d', contract_end_date):
                            contract_end_date = None
                                
                            # Update cache if we found dates
                        if signed_date or contract_end_date:
                            if pid in cache:
                                if not cache[pid].get("signed_date") and signed_date:
                                    cache[pid]["signed_date"] = signed_date
                                elif cache[pid].get("signed_date") in ["-", "", None, "?"] or "?" in str(cache[pid].get("signed_date")):
                                    cache[pid]["signed_date"] = signed_date
                                    
                                if not cache[pid].get("contract_end_date") and contract_end_date:
                                    cache[pid]["contract_end_date"] = contract_end_date
                                elif cache[pid].get("contract_end_date") in ["-", "", None, "?"] or "?" in str(cache[pid].get("contract_end_date")):
                                    cache[pid]["contract_end_date"] = contract_end_date
                            else:
                                cache[pid] = {
                                    "signed_date": signed_date,
                                    "contract_end_date": contract_end_date
                                }
                            
                            # Ensure we don't save "-"
                            if str(cache[pid].get("signed_date")).lower() in ["-", "", "?", "none", "right", "left", "both"] or "?" in str(cache[pid].get("signed_date")): cache[pid]["signed_date"] = None
                            if str(cache[pid].get("contract_end_date")).lower() in ["-", "", "?", "none", "right", "left", "both"] or "?" in str(cache[pid].get("contract_end_date")): cache[pid]["contract_end_date"] = None
                        else:
                            # We didn't find dates for this player on this team
                            # We add to cache so we don't try to scrape them individually again
                            if pid not in cache:
                                cache[pid] = {
                                    "signed_date": None,
                                    "contract_end_date": None
                                }
                            else:
                                # Ensure we don't keep "-" from bad past cache
                                if str(cache[pid].get("signed_date")).lower() in ["-", "", "?", "none", "right", "left", "both"] or "?" in str(cache[pid].get("signed_date")): cache[pid]["signed_date"] = None
                                if str(cache[pid].get("contract_end_date")).lower() in ["-", "", "?", "none", "right", "left", "both"] or "?" in str(cache[pid].get("contract_end_date")): cache[pid]["contract_end_date"] = None
                                
                    except IndexError:
                        pass
        except Exception as e:
            error_count += 1
            print(f"Error processing team {tid}: {e}")
            if error_count > 20:
                print("Too many errors. Saving current cache and stopping team scrape.")
                break
                
        if (i + 1) % save_interval == 0:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2)
                    
        # Save cache after teams
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)

    missing_players = unique_player_ids - set(cache.keys())
    print(f"Need to scrape {len(missing_players)} remaining players individually...")
    
    # Add a small delay to respect rate limits (Transfermarkt limits around 40-50 per min)
    save_interval = 25
    
    ids_to_scrape = list(missing_players)
    if ids_to_scrape:
        print(f"Starting to scrape {len(ids_to_scrape)} individual players")
        
        # We process in batches to save cache
        batch_size = 100
        
        # If we have too many missing players after team scraping, we might have hit a block
        if False: # Removed the 5000 limit as requested
            print("Warning: More than 5000 players still missing after team scraping.")
            print("Aborting individual scraping to prevent getting blocked by Transfermarkt.")
            print("You can run this script again later to continue.")
        else:
            print("Warning: Scraping ~60k players individually will take a long time.")
            print("The script will save every 100 players, so you can stop (Ctrl+C) and resume later if needed.")
            for batch_start in range(0, len(ids_to_scrape), batch_size):
                batch_pids = ids_to_scrape[batch_start:batch_start + batch_size]
                
                with ThreadPoolExecutor(max_workers=5) as executor:
                    def process_player(pid):
                        import random
                        time.sleep(random.uniform(0.1, 0.5))
                        try:
                            player_obj = scraper.scrape_player_details(pid)
                            if player_obj:
                                return pid, {
                                    "signed_date": player_obj.signed_date,
                                    "contract_end_date": player_obj.contract_end_date
                                }
                        except Exception as e:
                            pass
                        return pid, {"signed_date": None, "contract_end_date": None}
                
                    # Process the batch
                    future_to_pid = {executor.submit(process_player, pid): pid for pid in batch_pids}
                    
                    for future in tqdm(as_completed(future_to_pid), total=len(batch_pids), desc=f"Scraping players ({batch_start}/{len(ids_to_scrape)})"):
                        pid, dates = future.result()
                        
                        if pid in cache:
                            if not cache[pid].get("signed_date") and dates["signed_date"]:
                                cache[pid]["signed_date"] = dates["signed_date"]
                            if not cache[pid].get("contract_end_date") and dates["contract_end_date"]:
                                cache[pid]["contract_end_date"] = dates["contract_end_date"]
                        else:
                            cache[pid] = dates
                            
                        # Ensure we also process the ids_to_scrape cache entries properly
                        # and clean up bad "-" values
                        for pid in list(cache.keys()):
                            if str(cache[pid].get("signed_date")).lower() in ["-", "", "?", "none", "right", "left", "both"] or "?" in str(cache[pid].get("signed_date")):
                                cache[pid]["signed_date"] = None
                            if str(cache[pid].get("contract_end_date")).lower() in ["-", "", "?", "none", "right", "left", "both"] or "?" in str(cache[pid].get("contract_end_date")):
                                cache[pid]["contract_end_date"] = None
                            
                # Save cache after each batch
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(cache, f, indent=2)
                
                # Backup cache
                try:
                    import shutil
                    shutil.copy(cache_file, f"{cache_file}.bak")
                except:
                    pass
            
    # Print summary of remaining players before saving files
    still_missing = unique_player_ids - set(cache.keys())
    print(f"Scraping completed. {len(still_missing)} players still missing dates from cache.")
    
    # Final cleanup before applying to files
    for pid in list(cache.keys()):
        if str(cache[pid].get("signed_date")).lower() in ["-", "", "?", "none", "right", "left", "both"] or "?" in str(cache[pid].get("signed_date")):
            cache[pid]["signed_date"] = None
        if str(cache[pid].get("contract_end_date")).lower() in ["-", "", "?", "none", "right", "left", "both"] or "?" in str(cache[pid].get("contract_end_date")):
            cache[pid]["contract_end_date"] = None
    
    print("Applying updates to files...")
    for base, data in files_data.items():
        updated = False
        for player in data:
            pid = str(player.get("player_id"))
            
            # First clean up "-" directly in the player data
            if str(player.get("signed_date")).lower() in ["-", "", "?", "none", "right", "left", "both"] or "?" in str(player.get("signed_date")):
                player["signed_date"] = None
                updated = True
            if str(player.get("contract_end_date")).lower() in ["-", "", "?", "none", "right", "left", "both"] or "?" in str(player.get("contract_end_date")):
                player["contract_end_date"] = None
                updated = True
                
            if pid in cache:
                cached_data = cache[pid]
                
                # Check if needs update
                if player.get("signed_date") != cached_data["signed_date"] or \
                   player.get("contract_end_date") != cached_data["contract_end_date"]:
                    player["signed_date"] = cached_data["signed_date"]
                    player["contract_end_date"] = cached_data["contract_end_date"]
                    updated = True
                    
            # Ensure None is used instead of null strings if it somehow bypassed checks
            if player.get("signed_date") == "None":
                player["signed_date"] = None
                updated = True
            if player.get("contract_end_date") == "None":
                player["contract_end_date"] = None
                updated = True
                    
        if updated:
            print(f"Saving updated {base}...")
            save_json_with_parts(data, base)
            
    print("Done! All players updated.")

if __name__ == "__main__":
    patch_players()
