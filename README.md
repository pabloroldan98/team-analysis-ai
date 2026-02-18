# Team Analysis AI

A comprehensive football data scraping and analysis platform that extracts data from Transfermarkt, including players, teams, leagues, transfers, and valuations.

---

## Table of Contents

1. [Data Integration & Web Scraping](#1-data-integration--web-scraping)
   - [Technical Decisions](#technical-decisions)
   - [Challenges](#challenges)
   - [Enhancements](#enhancements)
2. [AI Integration & Web Development](#2-ai-integration--web-development)
   - [How the Simulator Works](#how-the-simulator-works)
   - [ML Value Prediction](#ml-value-prediction)
   - [Knapsack Optimization](#knapsack-optimization)
   - [LLM Analysis](#llm-analysis)
   - [Web Application (Streamlit)](#web-application-streamlit)
3. [Stack & Architecture](#stack--architecture)
4. [Limitations & Trade-offs](#limitations--trade-offs)
5. [How to Run](#how-to-run)
6. [Future Improvements](#future-improvements)

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
- **Retry logic**: 5 retries with 60-second pauses between attempts for HTML scraping; dedicated `_api_get` method for API calls with retry on `ConnectionResetError`, HTTP 429, and 5xx errors
- **TLS fingerprinting**: Using `tls-requests` to mimic real browser connections

Even with these measures, occasional 403/429 errors occur, especially from GitHub Actions runners (known IPs).

#### Two-Phase Player Discovery

The scrapers for players, transfers, and valuations use a **two-phase approach** to ensure comprehensive coverage:

- **Phase 1 (Squad players)**: Scrape all players from current team squads and fetch their complete histories (transfer history, valuation history, etc.).
- **Phase 2 (Transferred players)**: Additionally scan each team's season transfer page to discover players who moved in/out that season but may no longer be in the current squad. Any new players not already covered in Phase 1 get their full history scraped as well.

This combined approach ensures we capture data for players who were transferred mid-season and wouldn't appear in the current squad roster.

#### Discovery of Transfermarkt API

A significant breakthrough was discovering Transfermarkt's internal API:

```
https://tmapi-alpha.transfermarkt.technology/
```

This API provides:
- **Player transfer history**: `/transfer/history/player/{player_id}`
- **Market value history**: `/player/{player_id}/market-value-history`
- **Club information**: `/clubs?ids[]=X&ids[]=Y...`
- **Competition data**: `/competition/{competition_id}` (used as fallback for league total market value)

Benefits of using the API:
- **Reduced request count**: One API call vs. multiple page scrapes
- **Faster execution**: JSON parsing vs. HTML parsing
- **More reliable data**: Structured responses vs. fragile XPath selectors
- **Future-proof**: Less likely to break when website UI changes

For the clubs batch endpoint, I implemented **adaptive batching** that starts with all IDs in one request and recursively splits in half on 414 (URL too long), 429 (rate limit), or 5xx (server error) responses. The club-name resolution uses aggressive retry settings (50 retries, 10s pause) since it's critical for data completeness — while 414 triggers an immediate split (retrying won't help), 429/5xx errors first retry with waits and only split the batch after all retries are exhausted.

Club name resolution follows a **three-level fallback chain**:
1. **API**: Batch-fetch names from the clubs endpoint (with adaptive splitting).
2. **Local file data**: If the API fails, scan all existing JSON files to build an `{id → name}` dictionary from already-known name/id pairs.
3. **Transfer history**: For valuations where `club_id` is `"0"` or the name is still empty, determine the club from the player's transfer history — the most recent transfer before the valuation date provides the `to_club_name`, or the earliest transfer provides the `from_club_name`.

Additionally, **empty valuation dates** are patched before any club-name logic runs: the date is inferred from the next valuation (−1 day), the previous valuation (+1 day), or `01/06/{season_start_year}` as a last resort.

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
| Player | name, age, club, birth_date, foot, nationality | height, position, other_positions, market_value, shirt_number, other_nationalities |
| Transfer | player_id, from_club, to_club, fee, date | market_value_at_transfer, is_loan, season |
| Valuation | player_id, amount, date | club_at_valuation |
| Team | - | stadium, capacity, logo, coach, squad_size, average_age, foreign_players_count |
| League | - | total_market_value, num_teams, num_players, most_valuable_player |

#### Multi-League, Multi-Season, Parallel Execution

Three workflow options are available:

1. **Single Scraper**: One league, one season, one entity (dropdowns)
2. **Input Scraper**: Multiple leagues, multiple seasons, multiple entities (JSON arrays + checkboxes)
3. **Scheduled Scraper**: All 5 leagues × 10 seasons, runs monthly automatically

All scrapers use **parallel matrix execution** — for example, the scheduled scraper spawns up to 50 parallel jobs (5 leagues × 10 seasons) per entity type.

---

## 2. AI Integration & Web Development

### Objective

An interactive web application for a **football transfer strategies simulator**. It accepts a Club Name, Starting Season, Transfer Budget and Salary Budget, and outputs a complete transfer window simulation with AI-generated analysis.

---

### How the Simulator Works

#### Data Loading Pipeline

Before the simulation runs, the **data loader** builds an accurate snapshot of every player at the start of the selected season:

1. **Load ALL players** from every `players_all_*.json` file (deduplicated, keeping the latest entry per player).
2. **Load ALL transfers** from every `transfers_all_*.json` file. For each player, find their **most recent transfer with a date ≤ 01/07/{season_start_year}** to determine their current team and loan status. This is an **inner join** — players that don't appear in the transfer data are excluded entirely, since we can't reliably determine their club.
3. **Filter out** players whose team is "Retired", "Without Club", "Career break", or empty.
4. **Compute age** from `birth_date` and the season cutoff date (01/07 of the starting year, or `now()` for "Today").
5. **Load ALL valuations** from every `valuations_all_*.json` file. For each player, find their **most recent valuation ≤ cutoff** and update their market value. Players without a valuation receive `market_value = 0` (they're in the club but haven't been valued yet).

**Performance optimizations** (for large datasets):

- **Streaming**: Transfer and valuation maps are built in a single pass without loading full lists into memory.
- **Parallel loading**: Multiple transfer/valuation files are loaded in parallel (up to 4 workers).
- **Fast JSON parsing**: Uses `orjson` when available (~5–10× faster than stdlib).
- **Multi-part files**: JSON files exceeding 90 MB are automatically split into `_part1.json`, `_part2.json`, etc. (to stay under GitHub's 100 MB limit).

#### Budget Calculation

Since exact player salaries are not publicly available, we approximate using a simple heuristic:

```
Effective Budget = min(Transfer Budget, Salary Budget × 10)
```

The reasoning: a player's annual salary is roughly **10% of their market value**. So either you're limited by how much you can spend on transfers, or by how much salary you can take on — whichever is lower.

#### Sell Phase

The simulator supports two selling modes:

1. **Manual selection** (Streamlit UI): The user loads the team data, then picks exactly which players to sell from multiselects grouped by position.
2. **Random selection** (default / CLI): Randomly selects **5 to 10 players** to put on the transfer market (max 3 per position).

In both modes, for each player:

- **On-loan players are excluded** from the sellable pool — they belong to another club and cannot be sold.
- A **destination club** is found at random among clubs whose total squad value is at least **10× the player's market value** (a rough proxy for "can afford this player").
- **Invalid destinations** are excluded: "Without Club", "Career break", and "Retired" are not real clubs you can sell to. You _can_ buy players from "Without Club" and "Career break", but "Retired" players are fully excluded from the simulation (no buying or selling).
- If no club qualifies, the player **is not sold** (no buyer found).
- Revenue from successful sales is added to the budget.

#### Buy Phase

The positions vacated by sold players need to be filled. The user can configure **how many players to sign per position** (0–3 each, default 1). If no custom counts are provided, the simulator replaces each sold position 1-for-1.

The simulator then:

1. Takes all available players from the market (excluding the selling club's squad and sold players).
2. **Predicts their future value** using the ML model for that season.
3. Runs the **Grouped Knapsack algorithm** to find the set of players that **maximizes total predicted value** while filling the required positions and staying within budget.

##### Athletic Bilbao Special Case

Athletic Bilbao has a real-world policy of only signing players with a connection to the Basque Country. The simulator replicates this rule **in both directions**:

- **Buying**: When Athletic Bilbao is the buying club, it can only sign players who have played for any Athletic family club at some point in their career.
- **Selling**: When any club sells a player, Athletic Bilbao (or its sub-clubs) can only appear as the destination if the player has Athletic family history.

The Athletic family clubs are: Athletic Bilbao, Bilbao Athletic, Athletic Bilbao UEFA U19, Athletic Bilbao U19, Athletic Bilbao U18, Athletic Bilbao Youth, CD Basconia.

This is checked by loading the **full transfer history** and verifying whether the player's `from_club` or `to_club` matches any of these teams (by name or ID).

#### AI Summary

Finally, the full context of the simulation is sent to an LLM:
- Budget breakdown and financial summary.
- Players sold (with destinations and prices).
- Players bought (with origin club, cost, and predicted value).
- The remaining squad (with current and predicted values).

The LLM produces a strategic analysis covering: the impact of departures, what the new signings bring, and whether this was a rebuilding or consolidation window.

---

### ML Value Prediction

An **XGBoost** model predicts the market value of players one year into the future.

#### Feature Engineering

Each row in the training dataset represents **one player at one point in time** (specifically, 01/07 of each year — the opening of the summer transfer window). Features include:

- **Player attributes**: age (explicitly calculated from `birth_date` and the cutoff date for each row), nationality, height, preferred foot, position.
- **Valuation history**: current market value, value trend, number of historical valuations.
- **Contextual features**: `is_playing_in_home_country`, league tier, club market value.
- **Current club determination**: The player's current club at each cutoff date is determined from their **transfer history** (most recent transfer before the cutoff), not from valuation data — which may reference the club at the time of valuation rather than the actual team on 01/07.
- **Categorical binning**: High-cardinality features like nationality and club are binned to reduce dimensionality.

#### Temporal Integrity

To prevent data leakage, models are **strictly limited to historical data**:

- The model for the **2022-2023 season** is trained on all valuations up to and including **01/07/2022**.
- It predicts player values for **01/07/2023**.
- It never sees data from the future — that would be cheating.

The train/validation split is also **temporal**: older seasons go to training, the most recent season(s) go to validation.

#### Categorical Features & Unknown Categories

The model uses **XGBoost with native categorical support** for league, position, nationality, etc. At prediction time, if a category appears that was **not seen during training** (e.g. a new league like Serie B when the model was trained on older data), it is automatically mapped to `"Other"` to avoid `XGBoostError: category not in training set`. Newly trained models save their category mappings; older models use a conservative fallback set.

---

### Knapsack Optimization

The squad optimization uses a **Multiple-Choice Knapsack Problem (MCKP)** solver — a technique I originally developed for [calculadorafantasy.com](https://www.calculadorafantasy.com) and adapted here.

How it works:
- Players are grouped by position (GK, DEF, MID, ATT).
- Each group generates all valid combinations of `r` players (where `r` is the number needed for that position).
- The knapsack algorithm picks exactly one combination per group, maximizing total **predicted value** while keeping total **market value** (cost) within budget.
- An **unlimited budget** mode is also available, which removes all cost constraints to see the theoretical best squad.

---

### LLM Analysis

Three LLM providers are supported:

| Provider | Model (default) | Environment Variable |
|----------|----------------|---------------------|
| OpenAI | `gpt-4o-mini` | `OPENAI_API_KEY` |
| Anthropic | `claude-3-haiku` | `ANTHROPIC_API_KEY` |
| Google Gemini | `gemini-2.0-flash` | `GEMINI_API_KEY` |

Set `LLM_PROVIDER` in your `.env` to choose the provider. The summary is generated **by default** — if no API key is found, it is simply skipped (no error).

---

### Web Application (Streamlit)

The simulator is exposed through an interactive **Streamlit** web application, deployed at:

> **[https://calculadorafichajes.streamlit.app/](https://calculadorafichajes.streamlit.app/)**
>
> **Note**: The hosted app may be down due to Streamlit Cloud resource limits. To test it, run it locally with `streamlit run streamlit_app.py` (see [How to Run](#how-to-run)).

#### UI Flow

The interface follows a sequential workflow:

1. **Season & Club selection**: Choose a season and a club. Clubs are sorted by league priority (LaLiga → Premier League → Serie A → Bundesliga → Ligue 1) and then by descending total squad market value.
2. **Load team data**: A mandatory step that loads all players, identifies the club squad, and calculates team market values. The rest of the UI is hidden until this completes.
3. **Select players to sell**: Multiselects grouped by position (GK, DEF, MID, ATT), showing each player's name, position, and market value. If none are selected, random selling is used.
4. **Signings per position**: Choose how many players to sign for each position (0–3, default 1).
5. **Budget configuration**: Set transfer budget and salary budget. The budget is **additional** to the money obtained from player sales. A checkbox enables **unlimited budget** mode.
6. **Simulate**: Runs the full simulation.

#### UI Features

- **Bilingual interface**: Toggle between Spanish and English with flag icons. All labels, captions, and AI analyses are language-aware.
- **Progress feedback**: A step-by-step progress bar with descriptive status messages (e.g., "Predicting future values with ML... [5/8]") and a spinner with a "May take a few minutes" caption.

#### Output Display

- **Players Sold** (left column): Player image, name, position, market value, and destination club — each with a red down-arrow icon.
- **Recommended Signings** (right column): Player image, name, position, current value → predicted value, and origin club — each with a green up-arrow icon.
- **Financial summary**: Total cost, remaining budget, predicted value (1 year), and expected net financial benefit — with a color-coded delta indicator (green/up when positive, red/down when negative).
- **Final squad**: All remaining + new players displayed as cards grouped by position (GK, DEF, MID, ATT), sorted by market value descending within each position. New signings are highlighted with a "NEW" badge and a colored border.
- **AI Analysis**: An expandable section where you can paste an API key (OpenAI, Anthropic, or Gemini — auto-detected from key prefix). The analysis is cached per language, so switching languages triggers a new analysis only if one hasn't been generated yet for that language.

#### Auto-Deployment

Every time a scraping pipeline completes, an **auto-update trigger** comment in `streamlit_app.py` is updated with the current timestamp. Since Streamlit Cloud watches the main branch for changes, this forces a redeployment with the latest data.

---

## Stack & Architecture

### Backend

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| HTTP Client | `tls-requests` (with `requests` fallback) |
| HTML Parsing | BeautifulSoup4 |
| Data Format | JSON (`orjson` for fast parsing when available) |
| ML Framework | XGBoost + Scikit-learn |
| Optimization | Custom Knapsack solver |
| CI/CD | GitHub Actions |

### Frontend

| Component | Technology |
|-----------|------------|
| Framework | Streamlit |
| Internationalization | Custom i18n module (ES/EN) |
| Deployment | Streamlit Cloud |

### AI Models

| Provider | Model | Usage |
|----------|-------|-------|
| OpenAI | gpt-4o-mini | `OPENAI_API_KEY` |
| Anthropic | claude-3-haiku | `ANTHROPIC_API_KEY` |
| Google Gemini | gemini-2.0-flash | `GEMINI_API_KEY` |

### Project Structure

```
team-analysis-ai/
├── .github/workflows/       # CI/CD scraping pipelines (7 workflows)
├── assets/
│   ├── arrows/              # UI arrow icons (red down, green up)
│   ├── language/            # Flag SVGs for language toggle
│   └── logo.png             # App logo
├── data/json/               # Scraped data (JSON, supports _all_* and multi-part)
├── ml/
│   ├── datasets/            # Cached training datasets (auto-split into parts if >90MB)
│   ├── models/              # Trained XGBoost models (.joblib)
│   ├── feature_engineering.py
│   ├── train_pipeline.py
│   └── value_predictor.py
├── scraping/
│   ├── base_scraper.py      # Base class + API retry logic
│   ├── utils/helpers.py     # JSON load/save, parse_date, list_json_bases, DATA_DIR
│   ├── transfermarkt_leagues.py
│   ├── transfermarkt_teams.py
│   ├── transfermarkt_players.py
│   ├── transfermarkt_transfers.py
│   └── transfermarkt_valuations.py
├── scraping_tasks/          # CLI entry points for scrapers
│   ├── scrape_*.py          # Individual entity scrapers
│   └── combine_data.py      # Combine league-specific files into _all_ files
├── scripts/
│   └── export_predictions_to_xlsx.py  # Export all players + predicted values to xlsx
├── simulator/
│   ├── data_loader.py       # Centralized player data pipeline
│   ├── knapsack_solver.py   # MCKP optimization
│   ├── transfer_simulator.py # Main simulation engine
│   ├── transfer_engine.py   # Alternative API (SimulationResult)
│   └── llm_summarizer.py    # LLM integration
├── webapp/
│   └── i18n.py              # Internationalization (ES/EN)
├── league.py / team.py / player.py / transfer.py / valuation.py
├── fill_club_names.py       # Backfill missing club names (API → local → transfers)
├── discover_leagues.py      # Discover leagues from Transfermarkt for scraper config
├── streamlit_app.py         # Web app entry point
├── requirements.txt
└── README.md
```

---

## Limitations & Trade-offs

### Scraping

- **Blocking is still common**: Headless scraping from virtual machines (GitHub runners) gets flagged more often than local scraping.
- **Conservative rate limiting**: 0.25s between requests + 60s retry pauses. Slower execution but higher success rate.
- **Internal API dependency**: The `tmapi-alpha.transfermarkt.technology` endpoint is undocumented and could change. HTML scraping is available as fallback.

### Simulation

- **Salary approximation**: Real salaries are complex (bonuses, taxes, etc.). The "10% of market value" rule is a simplification.
- **Transfer realism**: The simulation assumes any player can be bought if the budget allows, ignoring contracts, player will, or release clauses.
- **Sell realism**: In manual mode, the user picks who to sell. In random mode, the decision is random (within position limits) rather than strategic — this forces the optimizer to react to different scenarios.
- **Data availability**: Relies on Transfermarkt data. Smaller leagues may have gaps in historical valuations.

### ML Model

- **Temporal limitation**: The model can only be as good as the features available. It doesn't capture intangibles like injuries, form, or media hype.
- **RMSE objective**: The model optimizes for absolute monetary error (RMSE). This means it prioritizes accuracy for expensive players over cheap ones.

---

## How to Run

### Option 1: Live App

The simulator is deployed at:

> **[https://calculadorafichajes.streamlit.app/](https://calculadorafichajes.streamlit.app/)**

> **Note**: The hosted app may be down due to Streamlit Cloud resource limits. If it's unavailable, use Option 3 to run it locally.

### Option 2: GitHub Actions (Scraping)

The easiest way to run the scrapers is through GitHub Actions workflows:

1. **Single League & Season**: Go to [Input Single Scraper](../../actions/workflows/input_single_scraper.yml) → Run workflow → Select league, season, entity
2. **Multiple Leagues & Seasons**: Go to [Input Scraper](../../actions/workflows/input_scraper.yml) → Run workflow → Configure JSON arrays
3. **Full Data (All Leagues × 10 Seasons)**: Go to [Scheduled Scraper](../../actions/workflows/scheduled_scraper.yml) → Run workflow

### Option 3: Run Locally

**Prerequisites**

- Python 3.10+
- The simulator and ML pipeline require `*_all_*.json` files in `data/json/` (e.g. `players_all_2024-2025.json`, `transfers_all_2024-2025.json`, `valuations_all_2024-2025.json`). Use the scrapers + `combine_data.py`, or download data from a repository that has pre-scraped `_all_` files.

```bash
# Clone the repository
git clone https://github.com/pabloroldan98/team-analysis-ai.git
cd team-analysis-ai

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### Run the Streamlit App

```bash
streamlit run streamlit_app.py
```

The app will open at [http://localhost:8501](http://localhost:8501).

#### Configure LLM (optional)

Copy `.env.example` to `.env` and add your API key:

```env
LLM_PROVIDER=gemini          # openai, anthropic, or gemini
GEMINI_API_KEY=your-key-here  # or OPENAI_API_KEY / ANTHROPIC_API_KEY
```

Alternatively, you can enter the API key directly in the Streamlit app (in the AI Analysis section). The provider is auto-detected from the key prefix.

#### Run the Transfer Simulator (CLI)

```bash
# Basic simulation (with AI summary if API key is configured)
python -m simulator.transfer_simulator --club "Real Madrid" --season 2022-2023

# Use current data snapshot ("today" instead of a fixed season)
python -m simulator.transfer_simulator --club "Real Madrid" --season today

# Without AI summary
python -m simulator.transfer_simulator --club "Real Madrid" --season 2022-2023 --no-summary

# Sell by value decline (sell players whose predicted value < market value)
python -m simulator.transfer_simulator --club "FC Barcelona" --season 2023-2024 --sell-by-value-decline

# With specific LLM provider
python -m simulator.transfer_simulator --club "FC Barcelona" --season 2022-2023 --llm-provider gemini

# Quiet mode (no progress output)
python -m simulator.transfer_simulator --club "Real Madrid" --season 2022-2023 --no-verbose
```

#### Run the ML Pipeline

```bash
# Train model for a specific season
python -m ml.train_pipeline --season 2022-2023

# Rebuild the training dataset from scratch (e.g. after new data is scraped)
python -m ml.train_pipeline --season 2022-2023 --rebuild-dataset

# Use semi-annual cutoffs (more training rows, slower to build)
python -m ml.train_pipeline --season 2023-2024 --cutoff-months 6 --rebuild-dataset

# Verbose output
python -m ml.train_pipeline --season 2023-2024 --verbose
```

#### Run Scrapers Locally

```bash
python scraping_tasks/scrape_leagues.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_teams.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_players.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_transfers.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_valuations.py --leagues laliga --season 2025-2026
```

Output files are saved to `data/json/`. Use `scraping_tasks/combine_data.py` to merge league-specific files into `*_all_*.json` (required for the simulator).

#### Utility Scripts

```bash
# Export all players with predicted values to xlsx
python -m scripts.export_predictions_to_xlsx [--output FILE.xlsx] [--verbose]

# Fill missing club names in JSON files (API → local data → transfer history)
python fill_club_names.py [--dry-run]

# Discover leagues from Transfermarkt (output config for scrapers)
python discover_leagues.py

# Combine league-specific JSON into _all_ files
python scraping_tasks/combine_data.py --entity teams --season 2025-2026
python scraping_tasks/combine_data.py --entity players
python scraping_tasks/combine_data.py --entity transfers
python scraping_tasks/combine_data.py --entity valuations
```

---

## Future Improvements

- **Strategic selling**: Sell players based on criteria (age, declining value, surplus in position) rather than purely at random.
- **Transfer negotiation realism**: Add release clauses, contract length, and player willingness as factors that affect whether a transfer goes through.
- **Multi-window simulation**: Simulate multiple consecutive transfer windows to see squad evolution over several seasons.
- **Wage structure visualization**: Display estimated wage impact of signings and departures alongside transfer fees.
- **More leagues**: Extend beyond the top 5 European leagues to include Portuguese Liga, Eredivisie, Liga MX, etc.
- **Injury and performance data**: Integrate external data sources (injuries, goals, assists) to improve ML predictions.

---

## License

This project is for educational and demonstration purposes.

## Author

Pablo Roldán — [GitHub](https://github.com/pabloroldan98)
