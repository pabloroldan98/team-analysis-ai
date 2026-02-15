# scraping/transfermarkt_valuations.py
"""
Scraper for player valuation history from Transfermarkt.

By default (--details), fetches the FULL valuation history for each player
via Transfermarkt API.

With --no-details, only gets the current market value from player profiles
(much faster but no historical data).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional, Dict, Set, Tuple

from scraping.base_scraper import BaseScraper
from scraping.utils.helpers import parse_date
from valuation import Valuation


class TransfermarktValuationsScraper(BaseScraper):
    """Scraper for player valuation history from Transfermarkt."""
    
    # Transfermarkt API base URL
    TM_API_URL = "https://tmapi-alpha.transfermarkt.technology"
    
    # Cache for club names to avoid repeated API calls
    _club_name_cache: Dict[str, str] = {}
    
    # ── Resilient API request helper ────────────────────────────────────

    def _api_get(
        self,
        url: str,
        timeout: int = 60,
        max_retries: Optional[int] = None,
        retry_pause: Optional[int] = None,
    ) -> Optional[dict]:
        """
        GET a JSON API endpoint with retry logic identical to fetch_page.

        Retries on connection errors (ConnectionResetError, etc.) and on
        transient HTTP status codes (429, 5xx) up to *max_retries* times,
        sleeping *retry_pause* seconds between attempts.

        Parameters default to ``self.max_retries`` / ``self.retry_pause``
        when not supplied, but callers (e.g. ``_fetch_club_names_batch``)
        can override them for more aggressive retrying.

        Returns the parsed JSON dict on success, or None on failure.
        On 414 or exhausted retries for 429/5xx, returns
        ``{"_status": <code>}`` so the caller can split the batch.
        """
        import time as _time
        import requests

        _max = max_retries if max_retries is not None else self.max_retries
        _pause = retry_pause if retry_pause is not None else self.retry_pause
        last_transient_code = None

        for attempt in range(1, _max + 1):
            try:
                _time.sleep(self.delay)
                response = requests.get(url, timeout=timeout)

                if response.status_code == 200:
                    return response.json()

                if response.status_code == 414:
                    return {"_status": 414}

                if response.status_code in (429, 500, 502, 503, 504):
                    last_transient_code = response.status_code
                    self.log(f"    Attempt {attempt}/{_max}: HTTP {response.status_code}")
                else:
                    self.log(f"    HTTP {response.status_code}")
                    return None

            except Exception as e:
                last_transient_code = last_transient_code or 429
                self.log(f"    Attempt {attempt}/{_max}: {e!r}")

            if attempt < _max:
                self.log(f"    Retrying in {_pause}s...")
                _time.sleep(_pause)

        self.log(f"    All {_max} attempts failed for {url}")
        # Signal the caller to split the batch instead of giving up
        if last_transient_code is not None:
            return {"_status": last_transient_code}
        return None

    def _fetch_club_names_batch(self, club_ids: Set[str]) -> Dict[str, str]:
        """
        Fetch multiple club names via API, adaptively splitting on 414 errors.
        API: https://tmapi-alpha.transfermarkt.technology/clubs?ids[]=X&ids[]=Y...
        
        Starts with all IDs in one request. If 414 (URL too long) is received,
        splits the batch in half and retries recursively.
        
        Args:
            club_ids: Set of club IDs to fetch
        
        Returns:
            Dict mapping club_id -> club_name
        """
        if not club_ids:
            return {}
        
        # Filter out already cached IDs
        ids_to_fetch = [cid for cid in club_ids if cid and cid not in self._club_name_cache]
        
        if not ids_to_fetch:
            return {cid: self._club_name_cache.get(cid, "") for cid in club_ids}
        
        self.log(f"  Fetching {len(ids_to_fetch)} club names via API...")
        
        def fetch_batch(batch: list) -> None:
            """Recursively fetch a batch, splitting on 414/429/5xx errors."""
            if not batch:
                return
            
            params = "&".join([f"ids[]={cid}" for cid in batch])
            api_url = f"{self.TM_API_URL}/clubs?{params}"
            
            data = self._api_get(api_url, timeout=60, max_retries=50, retry_pause=10)
            
            if data is None:
                self.log(f"    Failed to fetch {len(batch)} club names")
                return
            
            # Splittable error (414, 429, 5xx) → halve the batch and retry
            error_status = data.get("_status")
            if error_status is not None:
                if len(batch) <= 1:
                    self.log(f"    Cannot split further, skipping ID: {batch[0]}")
                    return
                mid = len(batch) // 2
                self.log(f"    HTTP {error_status} with {len(batch)} IDs, splitting in half...")
                fetch_batch(batch[:mid])
                fetch_batch(batch[mid:])
                return
            
            if data.get("success"):
                clubs_data = data.get("data", [])
                for club in clubs_data:
                    club_id = str(club.get("id", ""))
                    club_name = club.get("name", "")
                    if club_id:
                        self._club_name_cache[club_id] = club_name
                self.log(f"    Fetched {len(clubs_data)} clubs (batch of {len(batch)})")
        
        fetch_batch(ids_to_fetch)
        
        self.log(f"    Total cached club names: {len(self._club_name_cache)}")
        
        return {cid: self._club_name_cache.get(cid, "") for cid in club_ids}
    
    def _fill_club_names(self, valuations: List[Valuation]) -> None:
        """
        Fill club_name_at_valuation for all valuations by fetching club names
        from the API, with a local-file fallback for IDs that the API couldn't
        resolve.

        Args:
            valuations: List of Valuation objects to update (modified in place)
        """
        # Collect unique club IDs that need names
        club_ids = set()
        for v in valuations:
            if v.club_id_at_valuation and not v.club_name_at_valuation:
                club_ids.add(v.club_id_at_valuation)

        if not club_ids:
            return

        self.log(f"\nFetching names for {len(club_ids)} clubs...")

        # Fetch all club names in one call
        club_names = self._fetch_club_names_batch(club_ids)

        # Fill club names in valuations
        for v in valuations:
            if v.club_id_at_valuation and v.club_id_at_valuation in club_names:
                v.club_name_at_valuation = club_names[v.club_id_at_valuation]

        # ── Local-file fallback for still-unresolved IDs ─────────────
        still_missing: set = set()
        for v in valuations:
            if v.club_id_at_valuation and not v.club_name_at_valuation:
                still_missing.add(v.club_id_at_valuation)

        if still_missing:
            self.log(f"  {len(still_missing)} IDs still unresolved – "
                     f"trying local file fallback …")
            try:
                from fill_club_names import load_all_json_files, build_local_name_map
                from pathlib import Path as _Path

                data_dir = _Path("data/json")
                if data_dir.exists():
                    file_records = load_all_json_files(data_dir)
                    local_map = build_local_name_map(file_records)
                    found = 0
                    for v in valuations:
                        if (v.club_id_at_valuation
                                and not v.club_name_at_valuation
                                and v.club_id_at_valuation in local_map):
                            v.club_name_at_valuation = local_map[v.club_id_at_valuation]
                            found += 1
                    self.log(f"  Local fallback resolved {found} additional names")
            except Exception as exc:
                self.log(f"  Local fallback failed: {exc}")
    
    def scrape_player_valuations(self, player_id: str, player_name: str = "") -> List[Valuation]:
        """
        Get FULL valuation history for a player using Transfermarkt API.
        API: https://tmapi-alpha.transfermarkt.technology/player/{player_id}/market-value-history
        
        Args:
            player_id: Transfermarkt player ID
            player_name: Player name for reference
        
        Returns:
            List of Valuation objects (all historical valuations)
        """
        api_url = f"{self.TM_API_URL}/player/{player_id}/market-value-history"
        
        self.log(f"  Fetching valuations via API: {player_name or player_id}")
        
        data = self._api_get(api_url, timeout=30)
        
        if data is None:
            self.log(f"    Failed after retries")
            return []
        
        if not data.get("success"):
            self.log(f"    API returned error: {data.get('message')}")
            return []
        
        # Parse the history data
        history = data.get("data", {}).get("history", [])
        
        valuations = []
        for item in history:
            valuation = self._parse_api_valuation(item, player_id, player_name)
            if valuation:
                valuations.append(valuation)
        
        self.log(f"    Found {len(valuations)} valuations")
        return valuations
    
    def _parse_api_valuation(self, item: dict, player_id: str, player_name: str) -> Optional[Valuation]:
        """
        Parse a valuation from the Transfermarkt API response.
        
        API structure:
        {
            "playerId": "948275",
            "clubId": "6767",
            "age": 17,
            "marketValue": {
                "value": 200000,
                "currency": "EUR",
                "compact": {"prefix": "€", "content": "200.00", "suffix": "K"},
                "determined": "2022-03-21"
            }
        }
        """
        try:
            market_value_data = item.get("marketValue", {})
            
            # Value
            valuation_amount = market_value_data.get("value")
            if valuation_amount is None:
                return None
            
            # Date - from marketValue.determined (format: "2022-03-21")
            date_str = market_value_data.get("determined", "")
            valuation_date = ""
            if date_str:
                date_match = re.match(r'(\d{4})-(\d{2})-(\d{2})', date_str)
                if date_match:
                    valuation_date = f"{date_match.group(3)}/{date_match.group(2)}/{date_match.group(1)}"
                else:
                    valuation_date = date_str
            
            # Club ID (club name will be filled later)
            club_id_at_valuation = str(item.get("clubId", ""))
            
            # Age
            age_at_valuation = item.get("age")
            
            # Generate unique ID
            valuation_id = self.generate_id(player_id, valuation_date, str(valuation_amount))
            
            return Valuation(
                valuation_id=valuation_id,
                player_id=player_id,
                player_name=player_name,
                valuation_amount=valuation_amount,
                valuation_date=valuation_date,
                club_name_at_valuation="",  # Will be filled later by _fill_club_names
                club_id_at_valuation=club_id_at_valuation,
                age_at_valuation=age_at_valuation,
            )
            
        except Exception as e:
            self.log(f"    Error parsing API valuation: {e}")
            return None
    
    def scrape_team_valuations(self, team_id: str, details: bool = True, 
                               player_ids: List = None) -> Dict[str, List[Valuation]]:
        """
        Scrape valuations for all players in a team.
        
        Args:
            team_id: Transfermarkt team ID
            details: If True, get full valuation history per player. 
                     If False, only current market value.
            player_ids: Optional list of player IDs or tuples (will fetch from team if not provided)
        
        Returns:
            Dict mapping player_id -> list of valuations
        """
        # If no player IDs provided, fetch them from team
        if player_ids is None:
            from scraping.transfermarkt_players import TransfermarktPlayersScraper
            players_scraper = TransfermarktPlayersScraper(season=self.season, delay=self.delay, verbose=False)
            players = players_scraper.scrape_team_players(team_id)
            player_ids = [(p.player_id, p.name, p.market_value, p.team) for p in players]
        else:
            # Convert simple IDs to tuples with placeholder info if needed
            player_ids = [
                (pid, "", None, "") if not isinstance(pid, tuple) else pid 
                for pid in player_ids
            ]
        
        all_valuations = {}
        
        for i, player_info in enumerate(player_ids):
            if isinstance(player_info, tuple):
                pid, pname, current_value, club = player_info
            else:
                pid = player_info
                pname = ""
                current_value = None
                club = ""
            
            self.log(f"  [{i+1}/{len(player_ids)}] Player {pname or pid}")
            
            if details:
                # Get full history via API
                valuations = self.scrape_player_valuations(pid, pname)
            else:
                # Only current value (create single Valuation from player data)
                if current_value:
                    valuation_id = self.generate_id(pid, self.season, str(current_value))
                    valuations = [Valuation(
                        valuation_id=valuation_id,
                        player_id=pid,
                        player_name=pname,
                        valuation_amount=current_value,
                        valuation_date=self.season,
                        club_name_at_valuation=club,
                    )]
                else:
                    valuations = []
            
            all_valuations[pid] = valuations
        
        return all_valuations
    
    def scrape_league_valuations(
        self,
        league: str,
        details: bool = True,
        skip_player_ids: set = None,
        all_years_player_records: dict = None,
    ) -> Dict[str, Dict[str, List[Valuation]]]:
        """
        Scrape valuations for all players in a league.

        Phase 1 – Squad players:
          Get every team's current squad via the players scraper, then
          fetch each player's valuation history via API.

        Phase 2 – Transferred players:
          Scrape the season transfer page of each team to discover players
          who moved in/out that season.  For any player NOT already covered
          in Phase 1, fetch their valuation history as well.

        Players are globally deduplicated so no player is scraped twice.

        Args:
            league: League identifier
            details: If True, get full valuation history per player (slower).
                     If False, only current market values (faster).
            skip_player_ids: Player IDs to skip (already scraped).

        Returns:
            Dict mapping team_id -> player_id -> list of valuations
        """
        all_years_player_records = all_years_player_records or {}
        filled_player_ids: set = set()

        from scraping.transfermarkt_players import TransfermarktPlayersScraper
        players_scraper = TransfermarktPlayersScraper(season=self.season, delay=self.delay, verbose=False)
        players_by_team = players_scraper.scrape_league_players(league)

        all_valuations: Dict[str, Dict[str, List[Valuation]]] = {}
        global_seen: set = set(skip_player_ids) if skip_player_ids else set()

        # ── Phase 1: squad players ───────────────────────────────────────
        self.log(f"\n--- Phase 1: Squad players ({league.upper()}) ---")

        for team_id, players in players_by_team.items():
            team_name = players[0].team if players else team_id
            self.log(f"\nTeam: {team_name}")

            # Filter out players already scraped
            player_info = [
                (p.player_id, p.name, p.market_value, p.team)
                for p in players if p.player_id not in global_seen
            ]
            skipped = len(players) - len(player_info)
            if skipped:
                self.log(f"  Skipping {skipped} already-scraped player(s)")

            team_valuations = self.scrape_team_valuations(
                team_id=team_id,
                details=details,
                player_ids=player_info
            )

            if team_id not in all_valuations:
                all_valuations[team_id] = {}
            all_valuations[team_id].update(team_valuations)
            for p in players:
                was_skipped = p.player_id in global_seen
                global_seen.add(p.player_id)
                if was_skipped and p.player_id not in filled_player_ids and p.player_id in all_years_player_records:
                    all_valuations[team_id][p.player_id] = [
                        Valuation.from_dict(d) for d in all_years_player_records[p.player_id]
                    ]
                    filled_player_ids.add(p.player_id)

        # ── Phase 2: transferred players from season transfer pages ──────
        self.log(f"\n--- Phase 2: Transferred players ({league.upper()}) ---")

        team_infos = self.get_league_teams(league)

        for i, info in enumerate(team_infos):
            tid = info["team_id"]
            tname = info["team_name"]
            self.log(f"\n[{i+1}/{len(team_infos)}] {tname} (transfer page)")

            page_players = self.get_transferred_player_ids(tid, tname)

            new_players = [(pid, pname) for pid, pname in page_players if pid not in global_seen]

            if tid not in all_valuations:
                all_valuations[tid] = {}

            # Fill skipped players from all-years pool
            for pid, pname in page_players:
                if pid in global_seen and pid not in filled_player_ids and pid in all_years_player_records:
                    self.log(f"  Fill {pname or pid} from all years")
                    all_valuations[tid][pid] = [
                        Valuation.from_dict(d) for d in all_years_player_records[pid]
                    ]
                    filled_player_ids.add(pid)

            if not new_players:
                self.log(f"  No new players found on transfer page")
                continue

            self.log(f"  {len(new_players)} new player(s) from transfer page")

            for j, (pid, pname) in enumerate(new_players):
                global_seen.add(pid)
                self.log(f"  [{j+1}/{len(new_players)}] {pname or pid}")

                if details:
                    valuations = self.scrape_player_valuations(pid, pname)
                else:
                    valuations = []

                all_valuations[tid][pid] = valuations

        return all_valuations
    
    # ── Fix empty valuation dates ────────────────────────────────────────

    def _fix_empty_valuation_dates(self, valuations: List[Valuation]) -> None:
        """Fill empty ``valuation_date`` using neighbouring valuations.

        For each valuation with an empty date:

        1. Use the **next** valuation's date **− 1 day** (same player, by
           list order).
        2. If there is no next, use the **previous** valuation's date
           **+ 1 day**.
        3. If neither exists, fall back to ``01/06/{season_start_year}``
           when a season is available; otherwise skip.
        """
        from datetime import timedelta

        # Group by player, preserving original list order
        by_player: Dict[str, List[Valuation]] = {}
        for v in valuations:
            by_player.setdefault(v.player_id, []).append(v)

        season_year: Optional[int] = None
        if self.season:
            try:
                season_year = int(self.season.split("-")[0])
            except (ValueError, IndexError):
                pass

        fixed = 0
        for _pid, pvs in by_player.items():
            for i, v in enumerate(pvs):
                if v.valuation_date:
                    continue

                # 1. Next → date − 1 day
                for j in range(i + 1, len(pvs)):
                    nd = parse_date(pvs[j].valuation_date)
                    if nd:
                        v.valuation_date = (nd - timedelta(days=1)).strftime("%d/%m/%Y")
                        fixed += 1
                        break
                else:
                    # 2. Previous → date + 1 day
                    for j in range(i - 1, -1, -1):
                        pd = parse_date(pvs[j].valuation_date)
                        if pd:
                            v.valuation_date = (pd + timedelta(days=1)).strftime("%d/%m/%Y")
                            fixed += 1
                            break
                    else:
                        # 3. Season fallback
                        if season_year:
                            v.valuation_date = f"01/06/{season_year}"
                            fixed += 1

        if fixed:
            self.log(f"  Fixed {fixed} empty valuation dates")

    # ── Fix club names from transfer history ────────────────────────────

    @staticmethod
    def _build_transfer_index(
        transfers,
    ) -> Dict[str, List[Tuple[datetime, object]]]:
        """Group transfers by ``player_id`` with parsed dates.

        Returns ``{player_id: [(date, Transfer), …]}`` sorted by date
        ascending.  Transfers whose date can't be parsed are skipped.
        """
        index: Dict[str, List[Tuple[datetime, object]]] = {}
        for t in transfers:
            td = parse_date(t.transfer_date)
            if td is None:
                continue
            index.setdefault(t.player_id, []).append((td, t))

        # Sort each player's list by date
        for pid in index:
            index[pid].sort(key=lambda x: x[0])

        return index

    def _fix_club_names_from_transfers(
        self,
        valuations: List[Valuation],
        transfer_index: Dict[str, List[Tuple[datetime, object]]],
    ) -> None:
        """Fix empty ``club_name_at_valuation`` using transfer history.

        For each valuation with no club name (or ``club_id == "0"``):

        1. Look up the player's transfers.
        2. Find the latest transfer with ``date <= valuation_date`` and use
           its ``to_club_name`` / ``to_club_id``.
        3. If no transfer exists before the valuation date, take the
           closest transfer overall and use ``from_club_name`` /
           ``from_club_id`` (i.e. the club the player came *from* in
           their earliest known transfer).
        """
        fixed = 0

        for v in valuations:
            if v.club_name_at_valuation and v.club_id_at_valuation != "0":
                continue

            player_transfers = transfer_index.get(v.player_id)
            if not player_transfers:
                continue

            val_date = parse_date(v.valuation_date)
            if not val_date:
                continue

            # Latest transfer with date <= valuation_date
            best_before = None
            for t_date, t in player_transfers:
                if t_date <= val_date:
                    best_before = (t_date, t)
                    # List is sorted, so last match = latest before

            if best_before:
                t = best_before[1]
                if t.to_club_name:
                    v.club_name_at_valuation = t.to_club_name
                    v.club_id_at_valuation = t.to_club_id or v.club_id_at_valuation
                    fixed += 1
                    continue

            # No transfer before → earliest transfer, use from_club_name
            _first_date, closest = player_transfers[0]

            if closest.from_club_name:
                v.club_name_at_valuation = closest.from_club_name
                v.club_id_at_valuation = closest.from_club_id or v.club_id_at_valuation
                fixed += 1

        if fixed:
            self.log(f"  Fixed {fixed} club names from transfer history")

    def run(self, leagues: List[str] = None, details: bool = True) -> dict:
        """
        Run the scraper for specified leagues.
        
        Args:
            leagues: List of league identifiers. Defaults to top 5.
            details: If True, get full valuation history (slower).
        
        Returns:
            Dict with all valuation data
        """
        if leagues is None:
            leagues = ["laliga", "premier", "bundesliga", "seriea", "ligue1"]

        # Pre-load all transfers once to fix empty club names later
        transfer_index: Dict[str, List] = {}
        if details:
            try:
                import sys
                from pathlib import Path as _Path
                _root = _Path(__file__).parent.parent
                sys.path.insert(0, str(_root))
                from simulator.data_loader import _load_all_transfers

                self.log("\nPre-loading transfers for club-name fixing …")
                all_transfers = _load_all_transfers()
                transfer_index = self._build_transfer_index(all_transfers)
                self.log(f"  Indexed transfers for {len(transfer_index)} players")
            except Exception as exc:
                self.log(f"  Could not pre-load transfers: {exc}")

        all_data = {}
        loaded_data: list = []
        all_years_player_records: dict = {}

        # Load existing data for incremental scraping (all years for skip+fill)
        skip_player_ids: set = set()
        if self.use_downloaded_data:
            from scraping.utils.helpers import load_entity_all_from_all_years

            skip_player_ids, all_years_player_records, loaded_data = load_entity_all_from_all_years(
                entity="valuations",
                id_field="player_id",
                current_season=self.season,
            )
            self.log(
                f"\nIncremental mode: {len(skip_player_ids)} players from all years, "
                f"{len(loaded_data)} in current season"
            )

        for league in leagues:
            self.log(f"\n=== Scraping valuations from {league.upper()} ===")
            valuations_data = self.scrape_league_valuations(
                league,
                details=details,
                skip_player_ids=skip_player_ids,
                all_years_player_records=all_years_player_records,
            )
            all_data[league] = valuations_data
            
            # Collect all valuations for this league
            all_valuations = []
            for team_data in valuations_data.values():
                for player_valuations in team_data.values():
                    all_valuations.extend(player_valuations)
            
            if details:
                # Fix empty valuation dates before any club-name logic
                self._fix_empty_valuation_dates(all_valuations)

                # Fill club names from API (single batch call)
                self._fill_club_names(all_valuations)

                # Fix remaining empty club names from transfer history
                if transfer_index:
                    self._fix_club_names_from_transfers(
                        all_valuations, transfer_index,
                    )
            
            # Save per-league file
            valuations_dicts = [v.to_dict() for v in all_valuations]
            self.save_json(valuations_dicts, f"valuations_{league}_{self.season}")

            # Update skip set so subsequent leagues benefit
            for v in all_valuations:
                skip_player_ids.add(v.player_id)
        
        # Save combined _all_ file (new + existing)
        combined = []
        for league_data in all_data.values():
            for team_data in league_data.values():
                for player_valuations in team_data.values():
                    combined.extend([v.to_dict() for v in player_valuations])
        combined.extend(loaded_data)
        self.save_json(combined, f"valuations_all_{self.season}")
        
        return all_data


if __name__ == "__main__":
    scraper = TransfermarktValuationsScraper()
    scraper.run()
