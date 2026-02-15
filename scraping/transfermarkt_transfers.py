# scraping/transfermarkt_transfers.py
"""
Scraper for transfer data from Transfermarkt.

Iterates over every player in every team of a league (same approach as
the valuations scraper) and fetches their FULL transfer history via the
Transfermarkt API.  This guarantees we capture all transfers for all
players that belonged to a squad in a given season.

With --no-details, falls back to scraping only the season transfer page
per team (faster, but no market_value_at_transfer and limited to that
season's movements).
"""
from __future__ import annotations

import re
from typing import List, Optional, Dict, Set

from scraping.base_scraper import BaseScraper
from transfer import Transfer


class TransfermarktTransfersScraper(BaseScraper):
    """Scraper for transfer information from Transfermarkt."""

    # Transfermarkt API base URL for player transfer history
    TM_API_URL = "https://tmapi-alpha.transfermarkt.technology"

    # Cache for club names to avoid repeated API calls
    _club_name_cache: Dict[str, str] = {}

    # Auto-decrementing counter for fake "debut" transfer IDs
    _fake_id_counter: int = 0

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

                # 414 is handled by the caller (batch splitting) – propagate it
                if response.status_code == 414:
                    return {"_status": 414}

                # Transient errors → retry
                if response.status_code in (429, 500, 502, 503, 504):
                    last_transient_code = response.status_code
                    self.log(f"    Attempt {attempt}/{_max}: HTTP {response.status_code}")
                else:
                    # Non-retryable HTTP error
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

    # ── Club-name helpers (shared with valuations scraper) ───────────────

    def _fetch_club_names_batch(self, club_ids: Set[str]) -> Dict[str, str]:
        """
        Fetch multiple club names via API, adaptively splitting on 414 errors.
        """
        if not club_ids:
            return {}

        ids_to_fetch = [cid for cid in club_ids if cid and cid not in self._club_name_cache]

        if not ids_to_fetch:
            return {cid: self._club_name_cache.get(cid, "") for cid in club_ids}

        self.log(f"  Fetching {len(ids_to_fetch)} club names via API...")

        def fetch_batch(batch: list) -> None:
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

    def _fill_club_names(self, transfers: List[Transfer]) -> None:
        """Fill from_club_name and to_club_name for all transfers via API,
        with a local-file fallback for IDs that the API couldn't resolve."""
        club_ids = set()
        for t in transfers:
            if t.from_club_id and not t.from_club_name:
                club_ids.add(t.from_club_id)
            if t.to_club_id and not t.to_club_name:
                club_ids.add(t.to_club_id)

        if not club_ids:
            return

        self.log(f"\nFetching names for {len(club_ids)} clubs...")
        club_names = self._fetch_club_names_batch(club_ids)

        for t in transfers:
            if t.from_club_id and t.from_club_id in club_names and not t.from_club_name:
                t.from_club_name = club_names[t.from_club_id]
            if t.to_club_id and t.to_club_id in club_names and not t.to_club_name:
                t.to_club_name = club_names[t.to_club_id]

        # ── Local-file fallback for still-unresolved IDs ─────────────
        still_missing: Set[str] = set()
        for t in transfers:
            if t.from_club_id and not t.from_club_name:
                still_missing.add(t.from_club_id)
            if t.to_club_id and not t.to_club_name:
                still_missing.add(t.to_club_id)

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
                    for t in transfers:
                        if t.from_club_id and not t.from_club_name:
                            name = local_map.get(t.from_club_id)
                            if name:
                                t.from_club_name = name
                                found += 1
                        if t.to_club_id and not t.to_club_name:
                            name = local_map.get(t.to_club_id)
                            if name:
                                t.to_club_name = name
                                found += 1
                    self.log(f"  Local fallback resolved {found} additional names")
            except Exception as exc:
                self.log(f"  Local fallback failed: {exc}")

    # ── Per-player API history ───────────────────────────────────────────

    def scrape_player_all_transfers(self, player_id: str, player_name: str = "") -> List[Transfer]:
        """
        Get ALL historical transfers for a player using Transfermarkt API.
        API: /transfer/history/player/{player_id}
        """
        api_url = f"{self.TM_API_URL}/transfer/history/player/{player_id}"

        self.log(f"  Fetching player transfers via API: {player_name or player_id}")

        data = self._api_get(api_url, timeout=30)

        if data is None:
            self.log(f"    Failed after retries")
            return []

        if not data.get("success"):
            self.log(f"    API returned error: {data.get('message')}")
            return []

        history = data.get("data", {}).get("history", {})
        terminated = history.get("terminated", [])

        transfers = []
        for item in terminated:
            transfer = self._parse_api_transfer(item, player_id, player_name)
            if transfer:
                transfers.append(transfer)

        self.log(f"    Found {len(transfers)} transfers")
        return transfers

    def _parse_api_transfer(self, item: dict, player_id: str, player_name: str) -> Optional[Transfer]:
        """Parse a single transfer from the Transfermarkt API response."""
        try:
            transfer_id = item.get("id", "")

            source = item.get("transferSource", {})
            dest = item.get("transferDestination", {})

            from_club_id = str(source.get("clubId", ""))
            to_club_id = str(dest.get("clubId", ""))

            details = item.get("details", {})

            # Date
            date_str = details.get("date", "")
            transfer_date = ""
            if date_str:
                date_match = re.match(r'(\d{4})-(\d{2})-(\d{2})', date_str)
                if date_match:
                    transfer_date = f"{date_match.group(3)}/{date_match.group(2)}/{date_match.group(1)}"

            # Season
            season_id = details.get("seasonId")
            season = f"{season_id}-{season_id + 1}" if season_id else ""

            # Market value at transfer
            mv_data = details.get("marketValue", {})
            market_value_at_transfer = mv_data.get("value")

            # Price / Fee
            fee_data = details.get("fee", {})
            price = fee_data.get("value")

            compact = fee_data.get("compact", {})
            price_str = f"{compact.get('prefix', '')}{compact.get('content', '')}{compact.get('suffix', '')}"
            if not price_str or price_str == "-":
                price_str = "Unknown"

            # Type
            type_details = item.get("typeDetails", {})
            transfer_type_raw = type_details.get("type", "STANDARD")
            fee_description = type_details.get("feeDescription", "")

            if transfer_type_raw == "RETURNED_FROM_PREVIOUS_LOAN":
                is_loan = True
                transfer_type = "loan_return"
            elif transfer_type_raw == "ACTIVE_LOAN_TRANSFER":
                is_loan = True
                transfer_type = "loan_out"
            else:
                is_loan = False
                transfer_type = "out"

            if fee_description and fee_description not in ["", "-"]:
                price_str = fee_description

            if price_str.lower() in ["free transfer", "ablösefrei"]:
                price = 0

            return Transfer(
                transfer_id=transfer_id,
                player_id=player_id,
                player_name=player_name,
                from_club_name="",
                from_club_id=from_club_id,
                to_club_name="",
                to_club_id=to_club_id,
                price=price,
                price_str=price_str,
                transfer_date=transfer_date,
                transfer_type=transfer_type,
                is_loan=is_loan,
                market_value_at_transfer=market_value_at_transfer,
                season=season,
            )

        except Exception as e:
            self.log(f"    Error parsing API transfer: {e}")
            return None

    # ── Fake "debut" transfer for players with no history ──────────────

    def _make_debut_transfer(self, player_id: str, player_name: str,
                             club_id: str, club_name: str) -> Transfer:
        """
        Create a synthetic 'debut' transfer for a player whose API history
        is empty (0 transfers found).

        Uses a decreasing negative integer as transfer_id (-1, -2, …).
        Date is set to 01/06/{season_start_year}.
        """
        self._fake_id_counter -= 1

        season_year = self.season.split("-")[0] if self.season else "2000"

        self.log(f"    No transfers found – creating debut transfer (id={self._fake_id_counter})")

        return Transfer(
            transfer_id=str(self._fake_id_counter),
            player_id=player_id,
            player_name=player_name,
            from_club_name="Unknown",
            from_club_id="75",
            to_club_name=club_name,
            to_club_id=club_id,
            price=None,
            price_str="Unknown",
            transfer_date=f"01/06/{season_year}",
            transfer_type="debut",
            is_loan=False,
            market_value_at_transfer=0,
            season=self.season,
        )

    # ── Team / League level (like valuations scraper) ────────────────────

    def scrape_team_transfers(self, team_id: str, team_name: str = "",
                              player_ids: List = None) -> List[Transfer]:
        """
        Scrape full transfer history for every player in a team.

        Args:
            team_id: Transfermarkt team ID
            team_name: Team name for logging
            player_ids: Optional pre-built list of (player_id, player_name) tuples.
                        If None, fetches the squad via the players scraper.

        Returns:
            Flat list of Transfer objects (all players, all history)
        """
        if player_ids is None:
            from scraping.transfermarkt_players import TransfermarktPlayersScraper
            players_scraper = TransfermarktPlayersScraper(
                season=self.season, delay=self.delay, verbose=False,
            )
            players = players_scraper.scrape_team_players(team_id)
            player_ids = [(p.player_id, p.name) for p in players]
        else:
            player_ids = [
                (pid, "") if not isinstance(pid, tuple) else pid
                for pid in player_ids
            ]

        all_transfers: List[Transfer] = []
        seen_ids: Set[str] = set()

        for i, (pid, pname) in enumerate(player_ids):
            self.log(f"  [{i + 1}/{len(player_ids)}] {pname or pid}")
            transfers = self.scrape_player_all_transfers(pid, pname)

            if not transfers:
                debut = self._make_debut_transfer(pid, pname, team_id, team_name)
                all_transfers.append(debut)
            else:
                for t in transfers:
                    if t.transfer_id and t.transfer_id not in seen_ids:
                        seen_ids.add(t.transfer_id)
                        all_transfers.append(t)

        return all_transfers

    def scrape_league_transfers(
        self,
        league: str,
        details: bool = True,
        skip_player_ids: Set[str] = None,
        all_years_player_records: Dict[str, List[dict]] = None,
    ) -> Dict[str, List[Transfer]]:
        """
        Scrape transfers for all players in all teams of a league.

        With details=True (default) combines TWO sources to avoid missing anyone:

          Phase 1 – Squad players:
            Get every team's current squad via the players scraper, then
            call the API to fetch each player's full transfer history.

          Phase 2 – Transferred players:
            Scrape the season transfer page of each team to discover players
            who moved in/out that season.  For any player NOT already covered
            in Phase 1, fetch their full transfer history via API as well.

        Players are globally deduplicated so no player is scraped twice even
        if they appear in multiple squads or transfer pages.

        Args:
            league: League identifier (e.g., "laliga", "premier")
            details: If True, fetch full transfer history via API.
            skip_player_ids: Player IDs to skip (already scraped).

        With details=False:
          Falls back to scraping only the season transfer pages per team
          (no market_value_at_transfer, only that season's movements).
        """
        if not details:
            return self._scrape_league_transfers_simple(league)

        all_years_player_records = all_years_player_records or {}
        filled_player_ids: Set[str] = set()

        from scraping.transfermarkt_players import TransfermarktPlayersScraper
        players_scraper = TransfermarktPlayersScraper(
            season=self.season, delay=self.delay, verbose=False,
        )
        players_by_team = players_scraper.scrape_league_players(league)

        all_transfers: Dict[str, List[Transfer]] = {}
        global_seen: Set[str] = set(skip_player_ids) if skip_player_ids else set()

        # ── Phase 1: all squad players ───────────────────────────────────
        self.log(f"\n--- Phase 1: Squad players ({league.upper()}) ---")

        for team_id, players in players_by_team.items():
            team_name = players[0].team if players else team_id
            self.log(f"\nTeam: {team_name}")

            player_info = [(p.player_id, p.name) for p in players]
            team_transfers: List[Transfer] = []

            for i, (pid, pname) in enumerate(player_info):
                if pid in global_seen:
                    self.log(f"  [{i + 1}/{len(player_info)}] {pname} (already scraped, skipping)")
                    if pid not in filled_player_ids and pid in all_years_player_records:
                        for d in all_years_player_records[pid]:
                            team_transfers.append(Transfer.from_dict(d))
                        filled_player_ids.add(pid)
                    continue
                global_seen.add(pid)

                self.log(f"  [{i + 1}/{len(player_info)}] {pname}")
                transfers = self.scrape_player_all_transfers(pid, pname)

                if not transfers:
                    debut = self._make_debut_transfer(pid, pname, team_id, team_name)
                    team_transfers.append(debut)
                else:
                    team_transfers.extend(transfers)

            all_transfers[team_id] = team_transfers

        # ── Phase 2: transferred players from season transfer pages ──────
        self.log(f"\n--- Phase 2: Transferred players ({league.upper()}) ---")

        team_infos = self.get_league_teams(league)

        for i, info in enumerate(team_infos):
            tid = info["team_id"]
            tname = info["team_name"]
            self.log(f"\n[{i + 1}/{len(team_infos)}] {tname} (transfer page)")

            # Scrape the season transfer page to discover player IDs
            page_players = self.get_transferred_player_ids(tid, tname)

            # Collect player IDs + names we haven't seen yet (to scrape)
            new_players: List[tuple] = []
            for pid, pname in page_players:
                if pid not in global_seen:
                    new_players.append((pid, pname))
                    global_seen.add(pid)

            # Fill skipped players from all-years pool (add only once per player)
            if tid not in all_transfers:
                all_transfers[tid] = []
            for pid, pname in page_players:
                if pid in global_seen and pid not in filled_player_ids and pid in all_years_player_records:
                    self.log(f"  Fill {pname or pid} from all years")
                    for d in all_years_player_records[pid]:
                        all_transfers[tid].append(Transfer.from_dict(d))
                    filled_player_ids.add(pid)

            if not new_players:
                self.log(f"  No new players found on transfer page")
                continue

            self.log(f"  {len(new_players)} new player(s) from transfer page")

            for j, (pid, pname) in enumerate(new_players):
                self.log(f"  [{j + 1}/{len(new_players)}] {pname or pid}")
                transfers = self.scrape_player_all_transfers(pid, pname)

                if not transfers:
                    debut = self._make_debut_transfer(pid, pname, tid, tname)
                    all_transfers[tid].append(debut)
                else:
                    all_transfers[tid].extend(transfers)

        return all_transfers

    # ── Simple fallback (no-details) ─────────────────────────────────────

    def _scrape_league_transfers_simple(self, league: str) -> Dict[str, List[Transfer]]:
        """Fallback: scrape only the season transfer page per team."""
        team_infos = self.get_league_teams(league)
        if not team_infos:
            self.log(f"No teams found for league: {league}")
            return {}

        all_transfers: Dict[str, List[Transfer]] = {}

        for i, info in enumerate(team_infos):
            self.log(f"[{i + 1}/{len(team_infos)}] {info['team_name']}")
            transfers = self._scrape_team_transfers_page(
                team_id=info["team_id"],
                team_name=info["team_name"],
            )
            all_transfers[info["team_id"]] = transfers

        return all_transfers

    def _scrape_team_transfers_page(self, team_id: str, team_name: str = "",
                                     season: str = None) -> List[Transfer]:
        """
        Scrape transfers from the season transfer page (no-details fallback).
        URL: /team-name/transfers/verein/{team_id}/saison_id/{season_year}
        """
        season = season or self.season
        season_year = season.split("-")[0] if season else ""

        url = f"{self.BASE_URL}/-/transfers/verein/{team_id}/saison_id/{season_year}"

        self.log(f"Scraping transfers page: {team_name or team_id} ({season})")
        soup = self.fetch_page(url)

        if not soup:
            return []

        if not team_name:
            header = soup.select_one("header.data-header h1")
            team_name = header.text.strip() if header else f"Team {team_id}"

        transfers: List[Transfer] = []
        seen_keys: Set[str] = set()

        for box in soup.select("div.box"):
            header = box.select_one("h2")
            if not header:
                continue

            header_text = header.text.strip().lower()

            if "arrival" in header_text or "llegada" in header_text or "zugänge" in header_text:
                transfer_type = "in"
            elif "departure" in header_text or "salida" in header_text or "abgänge" in header_text:
                transfer_type = "out"
            else:
                continue

            table = box.select_one("table.items")
            if not table:
                continue

            tbody = table.select_one("tbody")
            if not tbody:
                continue

            for row in tbody.select("tr.odd, tr.even"):
                transfer = self._parse_transfer_row(row, team_id, team_name, transfer_type, season)
                if transfer:
                    key = f"{transfer.player_id}_{transfer.from_club_id}_{transfer.to_club_id}_{transfer.season}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        transfers.append(transfer)

        self.log(f"  Found {len(transfers)} transfers")
        return transfers

    def _parse_transfer_row(self, row, team_id: str, team_name: str,
                            transfer_type: str, season: str) -> Optional[Transfer]:
        """Parse a transfer row from the season transfers page."""
        try:
            cells = row.select("td")
            if len(cells) < 4:
                return None

            player_link = row.select_one("a[href*='/profil/spieler/'], a[href*='/spieler/']")
            if not player_link:
                return None

            player_href = player_link.get("href", "")
            player_id = self.extract_player_id(player_href)
            player_name_text = player_link.get("title", "") or player_link.text.strip()

            if not player_id:
                return None

            other_club_name = ""
            other_club_id = ""

            club_links = row.select("a[href*='/verein/']")
            for link in club_links:
                href = link.get("href", "")
                club_id_match = re.search(r'/verein/(\d+)', href)
                if club_id_match:
                    club_name = link.get("title", "") or link.text.strip()
                    if not club_name:
                        img = link.select_one("img")
                        if img:
                            club_name = img.get("alt", "")
                    if club_name:
                        other_club_name = club_name
                        other_club_id = club_id_match.group(1)
                        break

            if not other_club_name:
                for cell in cells:
                    cell_text = cell.get_text(strip=True)
                    if cell_text in ["Retired", "Without Club", "Unknown", "-", "?"]:
                        other_club_name = cell_text
                        break
                    for img in cell.select("img"):
                        alt = img.get("alt", "")
                        if alt in ["Retired", "Without Club"]:
                            other_club_name = alt
                            break

            if transfer_type == "in":
                from_club_name, from_club_id = other_club_name, other_club_id
                to_club_name, to_club_id = team_name, team_id
            else:
                from_club_name, from_club_id = team_name, team_id
                to_club_name, to_club_id = other_club_name, other_club_id

            price_info = self._parse_price(row)
            price = price_info["price"]
            price_str = price_info["price_str"]
            is_loan = price_info["is_loan"]
            transfer_date = price_info.get("date", "")

            if is_loan:
                transfer_type = f"loan_{transfer_type}"

            transfer_id = self.generate_id(
                player_id, from_club_id or "unknown", to_club_id or "unknown", season
            )

            return Transfer(
                transfer_id=transfer_id,
                player_id=player_id,
                player_name=player_name_text,
                from_club_name=from_club_name,
                from_club_id=from_club_id,
                to_club_name=to_club_name,
                to_club_id=to_club_id,
                price=price,
                price_str=price_str,
                transfer_date=transfer_date,
                transfer_type=transfer_type,
                is_loan=is_loan,
                market_value_at_transfer=None,
                season=season,
            )
        except Exception as e:
            self.log(f"  Error parsing transfer row: {e}")
            return None

    def _parse_price(self, row) -> Dict:
        """Parse transfer price from a row."""
        result = {"price": None, "price_str": "Unknown", "is_loan": False, "date": ""}

        fee_cell = row.select_one("td.rechts")
        if not fee_cell:
            cells = row.select("td")
            if cells:
                fee_cell = cells[-1]

        if not fee_cell:
            return result

        fee_link = fee_cell.select_one("a")
        fee_text = fee_link.text.strip() if fee_link else fee_cell.get_text(strip=True)

        fee_lower = fee_text.lower()
        result["price_str"] = fee_text

        if "loan" in fee_lower or "leih" in fee_lower or "préstamo" in fee_lower:
            result["is_loan"] = True
            loan_value = self.parse_market_value(fee_text)
            result["price"] = loan_value if loan_value and loan_value > 0 else None
            date_match = re.search(r'(\d{2}/\d{2}/\d{4})', fee_text)
            if date_match:
                result["date"] = date_match.group(1)
            return result

        if "free" in fee_lower or "ablösefrei" in fee_lower or "libre" in fee_lower:
            result["price"] = 0
            result["price_str"] = "Free transfer"
            return result

        if fee_text in ["-", "?", "", "N/A"]:
            result["price"] = None
            result["price_str"] = "Unknown"
            return result

        parsed_value = self.parse_market_value(fee_text)
        if parsed_value is not None:
            result["price"] = parsed_value
            result["price_str"] = fee_text

        return result

    # ── run() entry-point ────────────────────────────────────────────────

    def run(self, leagues: List[str] = None, details: bool = True) -> dict:
        """
        Run the scraper for specified leagues.

        Args:
            leagues: League identifiers (defaults to top 5).
            details: If True, iterate every player's full API history.
                     If False, only scrape the season transfer pages.
        """
        if leagues is None:
            leagues = ["laliga", "premier", "bundesliga", "seriea", "ligue1"]

        all_data: Dict[str, Dict[str, List[Transfer]]] = {}
        loaded_data: list = []
        all_years_player_records: Dict[str, List[dict]] = {}

        # Load existing data for incremental scraping (all years for skip+fill)
        skip_player_ids: Set[str] = set()
        if self.use_downloaded_data:
            from scraping.utils.helpers import load_entity_all_from_all_years

            skip_player_ids, all_years_player_records, loaded_data = load_entity_all_from_all_years(
                entity="transfers",
                id_field="player_id",
                current_season=self.season,
            )
            self.log(
                f"\nIncremental mode: {len(skip_player_ids)} players from all years, "
                f"{len(loaded_data)} in current season"
            )

        for league in leagues:
            self.log(f"\n=== Scraping transfers from {league.upper()} ===")
            transfers_by_team = self.scrape_league_transfers(
                league,
                details=details,
                skip_player_ids=skip_player_ids,
                all_years_player_records=all_years_player_records,
            )
            all_data[league] = transfers_by_team

            # Collect all transfers for this league
            all_transfers: List[Transfer] = []
            for transfers in transfers_by_team.values():
                all_transfers.extend(transfers)

            # Fill club names from API (single batch call)
            if details:
                self._fill_club_names(all_transfers)

            # Save per-league file
            transfers_dicts = [t.to_dict() for t in all_transfers]
            self.save_json(transfers_dicts, f"transfers_{league}_{self.season}")

            # Update skip set so subsequent leagues benefit
            for t in all_transfers:
                skip_player_ids.add(t.player_id)

        # Save combined _all_ file (new + existing)
        combined: List[dict] = []
        for league_data in all_data.values():
            for transfers in league_data.values():
                combined.extend([t.to_dict() for t in transfers])
        combined.extend(loaded_data)
        self.save_json(combined, f"transfers_all_{self.season}")

        return all_data


if __name__ == "__main__":
    scraper = TransfermarktTransfersScraper()
    scraper.run()
