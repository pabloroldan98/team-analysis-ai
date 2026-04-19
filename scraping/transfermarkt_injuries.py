# scraping/transfermarkt_injuries.py
"""
Scraper for player injury history from Transfermarkt.

Iterates over every player in every team of a league and fetches their
FULL injury history from the detailed injury page:
    https://www.transfermarkt.com/-/verletzungen/spieler/{player_id}/plus/1

Handles pagination (the table may span multiple pages).
"""
from __future__ import annotations

import re
from typing import List, Optional, Dict, Set

from scraping.base_scraper import BaseScraper
from scraping.utils.helpers import normalize_date
from injury import Injury


class TransfermarktInjuriesScraper(BaseScraper):
    """Scraper for player injury history from Transfermarkt."""

    def scrape_player_injuries(self, player_id: str, player_name: str = "") -> List[Injury]:
        """
        Get FULL injury history for a player by scraping the detailed injury page.
        Handles pagination automatically.

        URL pattern: /-/verletzungen/spieler/{player_id}/plus/1
        Pagination:  /-/verletzungen/spieler/{player_id}/page/{n}/plus/1

        Args:
            player_id: Transfermarkt player ID
            player_name: Player name for reference

        Returns:
            List of Injury objects
        """
        self.log(f"  Fetching injuries: {player_name or player_id}")

        all_injuries: List[Injury] = []
        seen_ids: Set[str] = set()
        page = 1

        while True:
            if page == 1:
                url = f"{self.BASE_URL}/-/verletzungen/spieler/{player_id}/plus/1"
            else:
                url = f"{self.BASE_URL}/-/verletzungen/spieler/{player_id}/page/{page}/plus/1"

            soup = self.fetch_page(url)
            if not soup:
                break

            rows = soup.select("table.items tbody tr.odd, table.items tbody tr.even")
            if not rows:
                break

            page_count = 0
            for row in rows:
                injury = self._parse_injury_row(row, player_id, player_name)
                if injury and injury.injury_id not in seen_ids:
                    seen_ids.add(injury.injury_id)
                    all_injuries.append(injury)
                    page_count += 1

            if page_count == 0:
                break

            # Check for next page link
            next_link = soup.select_one("li.tm-pagination__list-item--icon-next-page a")
            if not next_link:
                break

            page += 1

        self.log(f"    Found {len(all_injuries)} injuries")
        return all_injuries

    def _parse_injury_row(self, row, player_id: str, player_name: str) -> Optional[Injury]:
        """Parse a single row from the detailed injury table."""
        try:
            cells = row.select("td")
            if len(cells) < 6:
                return None

            # Season (cell 0)
            season_text = cells[0].get_text(strip=True)

            # Injury name (cell 1)
            injury_text = cells[1].get_text(strip=True)
            if not injury_text:
                return None

            # Date from (cell 2)
            date_from = cells[2].get_text(strip=True)

            # Date until (cell 3)
            date_until = cells[3].get_text(strip=True)

            # Days (cell 4) - e.g. "62 days"
            days = None
            days_text = cells[4].get_text(strip=True)
            days_match = re.search(r"(\d+)", days_text)
            if days_match:
                days = int(days_match.group(1))

            # Games missed (cell 5) - contains club link(s) + number
            games_missed = None
            club_name = ""
            club_id = ""

            games_cell = cells[5]
            # Club info from the link
            club_link = games_cell.select_one("a[href*='/verein/']")
            if club_link:
                club_name = club_link.get("title", "") or club_link.get_text(strip=True)
                club_href = club_link.get("href", "")
                cid_match = re.search(r"/verein/(\d+)", club_href)
                if cid_match:
                    club_id = cid_match.group(1)

            # Games missed is the plain text number (not inside a link)
            games_text = games_cell.get_text(strip=True)
            # Extract trailing number (the games count comes after club name)
            games_match = re.search(r"(\d+)\s*$", games_text)
            if games_match:
                games_missed = int(games_match.group(1))

            # Convert season text like "24/25" to "2024-2025"
            season = self._normalize_season(season_text)

            # Convert dates from "DD/MM/YYYY" or "MMM DD, YYYY" to DD/MM/YYYY
            date_from = normalize_date(date_from) or ""
            date_until = normalize_date(date_until) or ""

            injury_id = self.generate_id(player_id, injury_text, date_from)

            return Injury(
                injury_id=injury_id,
                player_id=player_id,
                player_name=player_name,
                season=season,
                injury=injury_text,
                date_from=date_from,
                date_until=date_until,
                days=days,
                games_missed=games_missed,
                club_name=club_name,
                club_id=club_id,
            )

        except Exception as e:
            self.log(f"    Error parsing injury row: {e}")
            return None

    @staticmethod
    def _normalize_season(season_text: str) -> str:
        """Convert '24/25' or '2024/2025' to '2024-2025'."""
        if not season_text:
            return ""
        m = re.match(r"(\d{2,4})/(\d{2,4})", season_text)
        if not m:
            return season_text
        start, end = m.group(1), m.group(2)
        if len(start) == 2:
            century = "20" if int(start) < 80 else "19"
            start = century + start
        if len(end) == 2:
            century = "20" if int(end) < 80 else "19"
            end = century + end
        return f"{start}-{end}"

    # ── Team / League level ────────────────────────────────────

    def scrape_league_injuries(
        self,
        league: str,
        skip_player_ids: Set[str] = None,
        all_years_player_records: Dict[str, List[dict]] = None,
        players_by_team: Dict[str, list] = None,
    ) -> Dict[str, List[Injury]]:
        """
        Scrape injuries for all players in all teams of a league.

        Phase 1 - Squad players:
          Get every team's current squad, then scrape each player's
          full injury history.

        Phase 2 - Transferred players:
          Discover players from the season transfer page who aren't
          in the current squad, and scrape their injury history too.

        Args:
            league: League identifier
            skip_player_ids: Player IDs to skip (already scraped)
            all_years_player_records: Pre-loaded records for filling skipped players
            players_by_team: Pre-loaded players dict to skip fetching squads

        Returns:
            Dict mapping team_id -> list of Injury objects
        """
        all_years_player_records = all_years_player_records or {}
        filled_player_ids: Set[str] = set()

        players_by_team_passed_in = players_by_team is not None

        if players_by_team is None:
            self.log("  [!] Pre-loaded players not found for this league. Scraping squad pages first (this may take a while)...")
            from scraping.transfermarkt_players import TransfermarktPlayersScraper
            players_scraper = TransfermarktPlayersScraper(
                season=self.season, delay=self.delay, verbose=self.verbose,
            )
            players_by_team = players_scraper.scrape_league_players(league)

        all_injuries: Dict[str, List[Injury]] = {}
        global_seen: Set[str] = set(skip_player_ids) if skip_player_ids else set()

        # ── Phase 1: squad players ────────────────────────────────
        self.log(f"\n--- Phase 1: Squad players ({league.upper()}) ---")

        for team_id, players in players_by_team.items():
            team_name = players[0].team if players else team_id
            self.log(f"\nTeam: {team_name}")

            team_injuries: List[Injury] = []

            for i, p in enumerate(players):
                if p.player_id in global_seen:
                    self.log(f"  [{i + 1}/{len(players)}] {p.name} (already scraped, skipping)")
                    if p.player_id not in filled_player_ids and p.player_id in all_years_player_records:
                        for d in all_years_player_records[p.player_id]:
                            team_injuries.append(Injury.from_dict(d))
                        filled_player_ids.add(p.player_id)
                    continue
                global_seen.add(p.player_id)

                self.log(f"  [{i + 1}/{len(players)}] {p.name}")
                injuries = self.scrape_player_injuries(p.player_id, p.name)
                team_injuries.extend(injuries)

            all_injuries[team_id] = team_injuries

        # ── Phase 2: transferred players ──────────────────────────
        # Only perform Phase 2 if we are NOT using a pre-loaded players list
        if not players_by_team_passed_in:
            self.log(f"\n--- Phase 2: Transferred players ({league.upper()}) ---")

            team_infos = self.get_league_teams(league)

            for i, info in enumerate(team_infos):
                tid = info["team_id"]
                tname = info["team_name"]
                self.log(f"\n[{i + 1}/{len(team_infos)}] {tname} (transfer page)")

                page_players = self.get_transferred_player_ids(tid, tname)

                if tid not in all_injuries:
                    all_injuries[tid] = []

                # Fill skipped players from all-years pool
                for pid, pname in page_players:
                    if pid in global_seen and pid not in filled_player_ids and pid in all_years_player_records:
                        self.log(f"  Fill {pname or pid} from all years")
                        for d in all_years_player_records[pid]:
                            all_injuries[tid].append(Injury.from_dict(d))
                        filled_player_ids.add(pid)

                new_players = [(pid, pname) for pid, pname in page_players if pid not in global_seen]

                if not new_players:
                    self.log(f"  No new players found on transfer page")
                    continue

                self.log(f"  {len(new_players)} new player(s) from transfer page")

                for j, (pid, pname) in enumerate(new_players):
                    global_seen.add(pid)
                    self.log(f"  [{j + 1}/{len(new_players)}] {pname or pid}")
                    injuries = self.scrape_player_injuries(pid, pname)
                    all_injuries[tid].extend(injuries)

        return all_injuries

    # ── run() entry-point ─────────────────────────────────────

    def run(self, leagues: List[str] = None, players_by_league: dict = None) -> dict:
        """
        Run the scraper for specified leagues.

        Args:
            leagues: League identifiers (defaults to top 5).
            players_by_league: Optional pre-loaded players dict.

        Returns:
            Dict with all injury data.
        """
        if leagues is None:
            leagues = ["laliga", "premier", "bundesliga", "seriea", "ligue1"]

        all_data: Dict[str, Dict[str, List[Injury]]] = {}
        loaded_data: list = []
        all_years_player_records: Dict[str, List[dict]] = {}

        # Load existing data for incremental scraping
        skip_player_ids: Set[str] = set()
        if self.use_downloaded_data:
            from scraping.utils.helpers import load_entity_all_from_all_years

            skip_player_ids, all_years_player_records, loaded_data = load_entity_all_from_all_years(
                entity="injuries",
                id_field="player_id",
                current_season=self.season,
            )
            self.log(
                f"\nIncremental mode: {len(skip_player_ids)} players from all years, "
                f"{len(loaded_data)} in current season"
            )

        for league in leagues:
            file_name = f"injuries_{league}_{self.season}"
            if self.skip_scraped and self._has_scraped_file(file_name):
                existing = self.load_json(file_name)
                if existing is not None:
                    self.log(f"\n=== {league.upper()}: file exists, skipping scraping ===")
                    from injury import Injury
                    injuries_by_team = {}
                    for d in existing:
                        inj = Injury.from_dict(d)
                        tid = inj.club_id if hasattr(inj, 'club_id') and inj.club_id else "unknown"
                        if tid not in injuries_by_team:
                            injuries_by_team[tid] = []
                        injuries_by_team[tid].append(inj)
                        if inj.player_id:
                            skip_player_ids.add(inj.player_id)
                            if inj.player_id not in all_years_player_records:
                                all_years_player_records[inj.player_id] = []
                            all_years_player_records[inj.player_id].append(d)
                    all_data[league] = injuries_by_team
                    continue

            self.log(f"\n=== Scraping injuries from {league.upper()} ===")

            league_players = None
            if players_by_league and league in players_by_league:
                league_players = players_by_league[league]

            injuries_by_team = self.scrape_league_injuries(
                league,
                skip_player_ids=skip_player_ids,
                all_years_player_records=all_years_player_records,
                players_by_team=league_players,
            )
            all_data[league] = injuries_by_team

            # Collect all injuries for this league
            all_injuries: List[Injury] = []
            for injuries in injuries_by_team.values():
                all_injuries.extend(injuries)

            # Save per-league file
            injuries_dicts = [inj.to_dict() for inj in all_injuries]
            self.save_json(injuries_dicts, f"injuries_{league}_{self.season}")

            # Update skip set so subsequent leagues benefit
            for inj in all_injuries:
                skip_player_ids.add(inj.player_id)

        # Save combined _all_ file (new + existing)
        combined: List[dict] = []
        for league_data in all_data.values():
            for injuries in league_data.values():
                combined.extend([inj.to_dict() for inj in injuries])
        combined.extend(loaded_data)
        self.save_json(combined, f"injuries_all_{self.season}")

        return all_data


if __name__ == "__main__":
    scraper = TransfermarktInjuriesScraper()
    scraper.run()
