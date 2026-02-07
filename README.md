# Team Analysis AI

A comprehensive football data scraping and analysis platform that extracts data from Transfermarkt, including players, teams, leagues, transfers, and valuations.

---

## Table of Contents

1. [Data Integration & Web Scraping](#1-data-integration--web-scraping)
   - [Technical Decisions](#technical-decisions)
   - [Challenges](#challenges)
   - [Enhancements](#enhancements)
2. [AI Integration & Web Development](#2-ai-integration--web-development) *(Coming Soon)*
3. [Stack & Architecture](#stack--architecture)
4. [Limitations & Trade-offs](#limitations--trade-offs)
5. [How to Run](#how-to-run)

---

## 1. Data Integration & Web Scraping

### Technical Decisions

#### CI/CD Pipelines with GitHub Actions

I decided to implement the entire scraping infrastructure using **GitHub Actions** for several reasons:

- **Free tier**: GitHub Actions provides generous free minutes for public repositories
- **Scheduling**: Native support for cron-based scheduling (e.g., monthly automated scrapes)
- **Manual triggers**: `workflow_dispatch` allows running scrapers on-demand with custom inputs
- **Parallel execution**: Matrix strategies enable scraping multiple leagues/seasons simultaneously
- **Artifact management**: Built-in artifact upload/download for data passing between jobs
- **Previous experience**: I've successfully used this approach in [knapsack-football-formations](https://github.com/pabloroldan98/knapsack-football-formations)

#### TLS Requests over Selenium

I specifically avoided **Selenium** because:

- It's slow due to browser rendering overhead
- Requires maintaining browser drivers
- More resource-intensive on CI/CD runners

Instead, I chose **`tls-requests`** over standard `requests` because:

- In my experience, it gets blocked significantly less frequently
- It mimics browser TLS fingerprints more accurately
- Faster execution with similar anti-detection benefits

#### Object-Oriented Architecture

The codebase follows an **object-oriented design** with dedicated classes for each entity:

```
├── league.py      # League data model
├── team.py        # Team data model  
├── player.py      # Player data model
├── transfer.py    # Transfer data model
├── valuation.py   # Valuation data model
└── scraping/
    ├── base_scraper.py              # Base class with common utilities
    ├── transfermarkt_leagues.py     # League-specific scraper
    ├── transfermarkt_teams.py       # Team-specific scraper
    ├── transfermarkt_players.py     # Player-specific scraper
    ├── transfermarkt_transfers.py   # Transfer-specific scraper
    └── transfermarkt_valuations.py  # Valuation-specific scraper
```

This approach makes it easier to:
- Track relationships between entities
- Serialize/deserialize data consistently (via `to_dict()`/`from_dict()`)
- Extend functionality without breaking existing code

---

### Challenges

#### Web Scraping with BeautifulSoup

Extracting data from Transfermarkt proved tricky at times:

- HTML structure varies between pages (player profiles vs. team pages)
- Some data is rendered dynamically or in non-obvious locations
- Position information, market values, and dates required custom parsing logic
- Stadium information was nested in unexpected DOM structures

#### Anti-Scraping Mechanisms

Despite implementing multiple countermeasures, blocking still occurs:

- **Rotating User-Agents**: Pool of 12+ different browser fingerprints (Chrome, Firefox, Safari, Edge, Opera across Windows/macOS/Linux)
- **Request delays**: 0.25s default delay between requests
- **Retry logic**: 5 retries with 60-second pauses between attempts
- **TLS fingerprinting**: Using `tls-requests` to mimic real browser connections

Even with these measures, occasional 403/429 errors occur, especially from GitHub Actions runners (known IPs).

#### Discovery of Transfermarkt API

A significant breakthrough was discovering Transfermarkt's internal API:

```
https://tmapi-alpha.transfermarkt.technology/
```

This API provides:
- **Player transfer history**: `/transfer/history/player/{player_id}`
- **Market value history**: `/player/{player_id}/market-value-history`
- **Club information**: `/clubs?ids[]=X&ids[]=Y...`

Benefits of using the API:
- **Reduced request count**: One API call vs. multiple page scrapes
- **Faster execution**: JSON parsing vs. HTML parsing
- **More reliable data**: Structured responses vs. fragile XPath selectors
- **Future-proof**: Less likely to break when website UI changes

For the clubs batch endpoint, I implemented **adaptive batching** that starts with all IDs in one request and recursively splits in half on 414 (URL too long) errors.

> **Note on Players API**: A batch endpoint exists (`/players?ids[]=X&ids[]=Y...`) but I chose not to use it because it doesn't return all the detailed player data I needed (positions, contract info, etc.). To get complete player profiles, individual page scraping is still required, so using the batch API wouldn't reduce the number of requests.

---

### Enhancements

#### League-Based Scraping (Instead of Team-Based)

The original requirement asked for team-based scraping, but I implemented **league-based scraping** instead:

- **No hardcoded IDs needed**: Team IDs are not intuitive (e.g., Real Madrid = 418)
- **Name consistency**: Team names vary (PSG vs. Paris Saint-Germain vs. Paris Saint-Germain FC)
- **Complete data**: Scraping a league automatically captures all teams and players
- **Simpler UX**: Just select "laliga" instead of looking up team IDs

#### Extended Data Collection

I capture more data than required:

| Entity | Required Fields | Additional Fields |
|--------|----------------|-------------------|
| Player | name, age, club, birth_date, foot, nationality | height, position, other_positions, market_value, contract_expires, joined_date, shirt_number, other_nationalities |
| Transfer | player_id, from_club, to_club, fee, date | market_value_at_transfer, is_loan, season |
| Valuation | player_id, amount, date | club_at_valuation |
| Team | - | stadium, capacity, logo, coach, squad_size, average_age, foreign_players_count |
| League | - | total_market_value, num_teams, num_players, most_valuable_player |

#### Multi-League, Multi-Season, Parallel Execution

Three workflow options are available:

1. **Single Scraper**: One league, one season, one entity (dropdowns)
2. **Input Scraper**: Multiple leagues, multiple seasons, multiple entities (JSON arrays + checkboxes)
3. **Scheduled Scraper**: All 5 leagues × 10 seasons, runs monthly automatically

All scrapers use **parallel matrix execution** - for example, the scheduled scraper spawns up to 50 parallel jobs (5 leagues × 10 seasons) per entity type.

---

## 2. AI Integration & Web Development

*Coming soon...*

---

## Stack & Architecture

### Backend / Scraping

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| HTTP Client | `tls-requests` (with `requests` fallback) |
| HTML Parsing | BeautifulSoup4 |
| Data Format | JSON (list of dictionaries) |
| CI/CD | GitHub Actions |
| Scheduling | Cron (1st of each month, 1:00 AM UTC) |

### Frontend

*Coming in Part 2...*

### AI Models

*Coming in Part 2...*

---

## Limitations & Trade-offs

### Scraping Reliability

- **Blocking is still common**: Headless scraping from virtual machines (GitHub runners) gets flagged more often than local scraping
- **Workaround**: Failed jobs can be re-run individually; the system is designed to be resilient with retries and graceful error handling

### Rate Limiting

- **Conservative delays**: 0.25s between requests + 60s retry pauses
- **Trade-off**: Slower execution but higher success rate

### Data Freshness

- **Scheduled monthly**: Data is refreshed on the 1st of each month
- **Manual runs available**: Can trigger scrapes anytime via workflow_dispatch

### API Dependency

- **Internal API**: The `tmapi-alpha.transfermarkt.technology` endpoint is undocumented and could change
- **Fallback**: HTML scraping is still available as backup

---

## How to Run

### Option 1: Run via GitHub Actions (Recommended)

The easiest way to run the scrapers is through GitHub Actions workflows:

#### Single League & Season (Dropdowns)

1. Go to [Input Single Scraper](https://github.com/pabloroldan98/team-analysis-ai/actions/workflows/input_single_scraper.yml)
2. Click **"Run workflow"**
3. Select your options from the dropdowns:
   - League: `laliga`, `premier`, `bundesliga`, `seriea`, `ligue1`
   - Season: `2025-2026` to `2016-2017`
   - Entity: `all`, `leagues`, `teams`, `players`, `transfers`, `valuations`
4. Click **"Run workflow"**

#### Multiple Leagues & Seasons (Advanced)

1. Go to [Input Scraper](https://github.com/pabloroldan98/team-analysis-ai/actions/workflows/input_scraper.yml)
2. Click **"Run workflow"**
3. Configure inputs:
   - Leagues: JSON array, e.g., `["laliga", "premier"]`
   - Seasons: JSON array, e.g., `["2025-2026", "2024-2025"]`
   - Check/uncheck entity checkboxes
4. Click **"Run workflow"**

#### Full Data (All Leagues, Last 10 Seasons)

1. Go to [Scheduled Scraper](https://github.com/pabloroldan98/team-analysis-ai/actions/workflows/scheduled_scraper.yml)
2. Click **"Run workflow"** → **"Run workflow"**
3. Wait for completion (this takes several hours due to the volume of data)

> **Note**: If you need permissions to run workflows, please contact the repository owner.

### Option 2: Run Locally

```bash
# Clone the repository
git clone https://github.com/pabloroldan98/team-analysis-ai.git
cd team-analysis-ai

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run individual scrapers
python scraping_tasks/scrape_leagues.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_teams.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_players.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_transfers.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_valuations.py --leagues laliga --season 2025-2026

# Available arguments:
#   --leagues: laliga, premier, bundesliga, seriea, ligue1 (comma-separated for multiple)
#   --season: e.g., 2025-2026 (defaults to current season)
#   --details / --no-details: Enable/disable detailed scraping (default: enabled)
```

Output files are saved to the `data/json/` directory:
```
data/json/
├── leagues_laliga_2025-2026.json
├── teams_laliga_2025-2026.json
├── players_laliga_2025-2026.json
├── transfers_laliga_2025-2026.json
└── valuations_laliga_2025-2026.json
```

---

## License

This project is for educational and demonstration purposes.

---

## Author

Pablo Roldán - [GitHub](https://github.com/pabloroldan98)
