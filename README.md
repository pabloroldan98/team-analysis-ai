# Team Analysis AI

A comprehensive football data scraping, ML prediction, and transfer simulation platform. Extracts data from Transfermarkt, predicts future player market values with XGBoost, and optimizes transfer windows using knapsack algorithms.

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
   - [Features](#features)
3. [Web Applications](#3-web-applications)
   - [Streamlit Frontend](#streamlit-frontend)
   - [React + FastAPI Frontend](#react--fastapi-frontend)
4. [Stack & Architecture](#4-stack--architecture)
5. [Limitations & Trade-offs](#5-limitations--trade-offs)
6. [How to Run](#6-how-to-run)
7. [Demo](#7-demo)
8. [Future Improvements](#8-future-improvements)

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
├── entities/
│   ├── league.py      # League data model
│   ├── team.py        # Team data model
│   ├── player.py      # Player data model
│   ├── transfer.py    # Transfer data model
│   └── valuation.py   # Valuation data model
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

An interactive web application for a **football transfer strategies simulator**. It accepts a Club Name, Starting Season, and Transfer Budget, and outputs a complete transfer window simulation with AI-generated analysis.

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

- **Precomputed season caches**: A script (`scripts/precompute_active_players_cache.py`) precomputes ALL season-level data (active players with ML predictions, team market values, Athletic-eligible IDs) and saves to `data/cache/seasons/season_data_{season}.json` (multi-part `*_partN.json` when large). The simulator loads these caches instantly instead of recomputing.
- **GitHub Actions automation**: Two workflows keep caches fresh — one runs daily at 00:30 CET for "today" data, another runs on push for historical seasons.
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

The simulator supports three selling modes:

1. **Manual selection** (UI): The user picks exactly which players to sell from multiselects grouped by position.
2. **Sell by value decline**: Automatically identifies players whose **predicted value < market value** (they've peaked financially) and recommends them for sale.
3. **Random selection** (default / CLI): Randomly selects **5 to 10 players** to put on the transfer market (max 3 per position).

In all modes, for each player:

- **On-loan players are excluded** from the sellable pool — they belong to another club and cannot be sold.
- A **destination club** is found at random among clubs whose total squad value is at least **10× the player's market value** (a rough proxy for "can afford this player").
- **Invalid destinations** are excluded: "Without Club", "Career break", and "Retired" are not real clubs you can sell to. You _can_ buy players from "Without Club" and "Career break", but "Retired" players are fully excluded from the simulation (no buying or selling).
- If no club qualifies, the player **is not sold** (no buyer found).
- Revenue from successful sales is added to the budget.

#### Buy Phase

The positions vacated by sold players need to be filled. The user can configure **how many players to sign per position** (0–3 each, default 1). If no custom counts are provided, the simulator replaces each sold position 1-for-1.

The simulator then:

1. Takes all available players from the market (excluding the selling club's squad, sold players, and **on-loan players** — a player on loan belongs to another club and is not available for purchase).
2. **Applies advanced filters** (league, banned clubs, banned players, etc.).
3. **Predicts their future value** using the ML model for that season.
4. Applies the selected **optimization objective** to rewrite predicted values.
5. Runs the **Grouped Knapsack algorithm** to find the optimal set of signings within budget.

##### Athletic Bilbao Special Case

Athletic Bilbao has a real-world policy of only signing players with a connection to the Basque Country. The simulator replicates this rule **in both directions**:

- **Buying**: When Athletic Bilbao is the buying club, it can only sign players who have played for any Athletic family club at some point in their career.
- **Selling**: When any club sells a player, Athletic Bilbao (or its sub-clubs) can only appear as the destination if the player has Athletic family history.

The Athletic family clubs are: Athletic Bilbao, Bilbao Athletic, Athletic Bilbao UEFA U19, Athletic Bilbao U19, Athletic Bilbao U18, Athletic Bilbao Youth, CD Basconia.

This is checked by loading the **full transfer history** and verifying whether the player's `from_club` or `to_club` matches any of these teams (by name or ID).

---

### ML Value Prediction

An **XGBoost** model predicts the market value of players one year into the future.

#### Feature Engineering (65+ features)

Each row in the training dataset represents **one player at one point in time** (specifically, 01/07 of each year — the opening of the summer transfer window). Features include:

| Category | Features |
|----------|----------|
| **Player attributes** | age, nationality (binned), height, preferred foot, position, positional versatility (num_positions) |
| **Current value** | market value, log-scale value, club total value, league tier |
| **Historical values** | value at 1y, 2y, 3y, 4y, 5y ago; last_valuation_date (decimal year) |
| **Trends** | % change over 1y, 2y, 4y, 5y |
| **Differences** | absolute change over 1y, 2y, 4y, 5y |
| **Percentiles** | current value percentile, historical percentiles, diff/trend/pct percentiles |
| **Derived** | value volatility (std/mean of recent values), value acceleration (trend change), peak ratio (current/max), age-value ratio |
| **Contextual** | is_in_top_league, is_in_home_league, club bin (top 25 or "Other") |
| **Loan status** | on_loan (whether the player is on loan at the cutoff date; always `False` for future predictions) |
| **Fair price** | fair_price_M (linear extrapolation from the two most recent valuations _excluding_ the latest, to ensure independence from current_value) |

#### Segmented Models

To prevent underestimation at extreme values, the system trains **4 specialized models** segmented by market value range:

| Segment | Range | Rationale |
|---------|-------|-----------|
| `under_1M` | €0 – €1M | Youth/low-tier players, can 10× in value |
| `1M_10M` | €1M – €10M | Emerging talents, can 5× |
| `10M_100M` | €10M – €100M | Established players, can 3× |
| `over_100M` | €100M+ | Elite stars, max 2× growth |

The `SegmentedValuePredictor` routes each player to the appropriate model. At segment boundaries, a **soft blend** (weighted average within a 15% zone) avoids prediction discontinuities. A global model serves as fallback when segment models aren't available.

**Anomaly clamping** prevents unrealistic predictions: per-segment growth ceilings and a 10% floor ensure no player's value is predicted to multiply beyond reason or drop to near-zero.

#### Temporal Integrity

To prevent data leakage, models are **strictly limited to historical data**:

- The model for the **2022-2023 season** is trained on all valuations up to and including **01/07/2022**.
- It predicts player values for **01/07/2023**.
- It never sees data from the future — that would be cheating.

The train/validation split is also **temporal**: older seasons go to training, the most recent season(s) go to validation. Sample weights give more importance to recent seasons (inflation / market evolution).

#### Categorical Features & Unknown Categories

The model uses **XGBoost with native categorical support** for league, position, nationality, etc. At prediction time, if a category appears that was **not seen during training** (e.g. a new league like Serie B when the model was trained on older data), it is automatically mapped to `"Other"` to avoid `XGBoostError: category not in training set`. Newly trained models save their category mappings; older models use a conservative fallback set.

#### Model Fallback for Future Seasons

The system supports simulating **seasons for which no dedicated model exists** (e.g., 2026-2027). When a model for the requested season is not found, it automatically falls back to the most recent available model (tries N-1, N-2, etc., up to 5 seasons back). This applies to both global and segmented models, and works in both the precompute script and the on-the-fly prediction path.

For example, simulating 2026-2027 with cutoff 01/07/2026 will use the 2025-2026 model if 2026-2027 hasn't been trained yet. Player data (market values, teams) is taken from the latest available valuations and transfers — since the data loader already filters by `date <= cutoff`, it naturally uses the most recent snapshot.

#### Native NaN / Missing Value Support

The model handles missing data natively via XGBoost's built-in NaN support. When a feature is genuinely unknown (e.g., no valuation 3 years ago, unknown height, unknown age), it is stored as `NaN` rather than a misleading default like `0.0`. XGBoost learns the optimal split direction for missing values during training, which is more accurate than imputing arbitrary defaults.

#### Backward Compatibility

Models trained before the v2 feature expansion (8 new features) still work. At prediction time, the predictor dynamically filters input features to match what the loaded model expects, filling any missing columns with `NaN`.

---

### Knapsack Optimization

The squad optimization uses a **Multiple-Choice Knapsack Problem (MCKP)** solver — a technique I originally developed for [calculadorafantasy.com](https://www.calculadorafantasy.com) and adapted here.

How it works:
- Players are grouped by position (GK, DEF, MID, ATT).
- Each group generates all valid combinations of `r` players (where `r` is the number needed for that position).
- The knapsack algorithm picks exactly one combination per group, maximizing the selected **objective** while keeping total **market value** (cost) within budget.
- An **unlimited budget** mode is also available, which removes all cost constraints to see the theoretical best squad.

#### Simulation Speed Tiers

Three speed presets control candidate pruning:

| Speed | Label | Description | Use Case |
|-------|-------|-------------|----------|
| `standard` | Standard | No pruning — full computation | Best results, production use |
| `fast` | Fast | Moderate pruning (90–200 candidates) | Balance of speed and quality |
| `local` | Faster | Aggressive pruning (50–100 candidates per group) | Quick local testing |

---

### LLM Analysis

Three LLM providers are supported:

| Provider | Display Name | Model (default) | Environment Variable |
|----------|-------------|----------------|---------------------|
| OpenAI | ChatGPT | `gpt-4o-mini` | `OPENAI_API_KEY` |
| Anthropic | Claude | `claude-3-haiku` | `ANTHROPIC_API_KEY` |
| Google | Gemini | `gemini-2.0-flash` | `GEMINI_API_KEY` |

Set `LLM_PROVIDER` in your `.env` to choose the provider. The summary is generated **by default** — if no API key is found, it is simply skipped (no error).

The LLM receives the full simulation context and produces a structured report with:
1. **Overall verdict** — rebuilding, consolidation, or marquee window
2. **Sale-by-sale reasoning** — why sell now, financial timing
3. **Signing-by-signing reasoning** — growth potential, xGrowth %, fair price assessment
4. **Financial summary** — total investment vs expected return, ROI, risk assessment

---

### Features

#### Sell Recommendations

Before the simulation, the system displays squad players across three tabs:

- **Full squad**: All players sorted by current market value
- **Peak reached**: Players whose predicted value is below their current market value (they've peaked financially)
- **Max expected decline**: Top 5 players by decline magnitude

Within each tab:

- **Visual indicators**: Players losing value show a red ▼ with the decline amount; players gaining value show a green ▲
- **Fair price**: Each player's fair price (linear extrapolation from their last two valuations) is displayed alongside current and predicted values
- **On-loan players**: Shown with reduced opacity and a "loaned" label. They are **not selectable** for sale (they belong to another club) but their **predicted value is still displayed** for reference
- **Select all / deselect all**: Buttons to quickly select or clear all eligible (non-loaned) players in the current tab
- **Manual override**: Users can also select players from a position-grouped chip view, where each chip shows the player's current value and predicted value

#### Optimization Objectives

The knapsack optimizer can maximize different metrics depending on the user's strategy:

| Objective | What it maximizes | Best for |
|-----------|-------------------|----------|
| **SMV** (Squad Market Value) | Total predicted value of signings | Building the most valuable squad |
| **Net Benefit** | Predicted value − purchase cost | Maximizing absolute profit |
| **ROI** | (Predicted − Cost) / Cost × 100 | Maximizing return percentage |
| **Growth %** | Predicted / Current value | Finding undervalued players |

#### Signing Strategies

Four pre-built approaches filter the candidate pool before optimization:

| Strategy | Label | Description |
|----------|-------|-------------|
| `max_value` | All players | No age filter — all eligible players are candidates |
| `young_talents` | Young talents | Only players aged ≤ 23. Build a long-term project |
| `balanced` | Balanced | Prioritizes prime-age players (25–29) with high predicted value |
| `veteran_players` | Veterans | Only players aged ≥ 30. Experienced signings with immediate impact |

#### Advanced Filters

- **League segmentation**: Restrict signings to specific leagues (e.g., only LaLiga and Premier League)
- **Nationality filter**: Filter players by nationality (chip-based multi-select with search). An optional "Include second nationality" checkbox extends the filter to also match players' secondary nationalities.
- **Banned clubs**: Exclude specific clubs as signing sources (searchable dropdown with chip-based selection)
- **Banned players**: Exclude specific players from recommendations (searchable dropdown with live search)
- **Temporal horizon**: Optimize for 1, 2, or 3 years ahead (multi-year predictions via iterative extrapolation)

#### xGrowth Ranking

**xGrowth** is a proprietary metric: `(predicted_value / market_value) - 1`. An xGrowth of +50% means the model predicts a 50% value increase in 1 year. The system produces a ranked list of the top players by xGrowth from the full player pool.

#### Similar Players (Financial Perspective)

For each recommended signing, the system finds **financially similar alternatives** — players in the same position with comparable market value, age, and xGrowth. Similarity is scored as a weighted combination:

- **Value similarity** (35%): How close are their market values
- **Age similarity** (25%): How close are their ages
- **xGrowth similarity** (40%): How similar is their predicted growth trajectory

#### Signing Alternatives

For each recommended signing, users can click to expand and see **5 alternative players**. These alternatives are drawn from the same pool of available players used during the simulation, filtered by:

- **Same position** as the recommended player
- **Market value ≤** the recommended player's value
- **Sorted by the same optimization objective** (SMV, Net Benefit, ROI, Growth %) used in the simulation
- **Excludes** players already in the recommended signings list

This allows the user to quickly explore comparable options if a specific signing isn't feasible.

#### Fair Purchase Price Estimation

The **fair price** is a simple, model-independent estimate computed via **linear extrapolation** from the player's last two valuations before the season's cutoff date. It takes the two most recent `(date, value)` points, fits a line, and evaluates it at the cutoff. This gives a "trend-based expected value" — if the current market value is above the fair price, the player may be overvalued relative to their trajectory; if below, they're undervalued. The result is clamped to [0, €250M]. If only one valuation exists, that value is used directly; if none exist, fair price is not set.

This is distinct from `predicted_value`, which uses the full ML model with 60+ features. The fair price provides a lightweight sanity check based purely on the player's valuation trend.

#### Player Search

A full-text search across all loaded players with filters for:
- Name (partial match, **accent-insensitive** — e.g., "atle" matches "Atlético de Madrid")
- Position (GK, DEF, MID, ATT)
- Market value range (min/max in millions)
- Age range (min/max)

Results include market value, predicted value, xGrowth, and fair price for each player. Both the search tab and xGrowth ranking support **pagination** with configurable page sizes.

The xGrowth tab also provides client-side filtering by league, nationality, team name, and slider ranges — all accent-insensitive and without requiring a server reload. The player count displays **filtered / total** (e.g., "213 / 51,389 players") so you always know the scope of the active filters.

---

## 3. Web Applications

The simulator is exposed through **two independent frontends** that share the same data and ML infrastructure.

### Streamlit Frontend

Deployed at:

> **[https://calculadorafichajes.streamlit.app/](https://calculadorafichajes.streamlit.app/)**
>
> **Note**: The hosted app may be down due to Streamlit Cloud resource limits. To test it, run it locally with `streamlit run streamlit_app.py`.

#### UI Flow

1. **Season & Club selection**: Choose a season and a club. Clubs are sorted by league priority (LaLiga → Premier League → Serie A → Bundesliga → Ligue 1) and then by descending total squad market value.
2. **Load team data**: A mandatory step that loads all players, identifies the club squad, and calculates team market values. The rest of the UI is hidden until this completes.
3. **Player search**: Search across all loaded players with filters (available immediately after loading).
4. **Sell recommendations**: The system identifies players at their financial peak and recommends them for sale.
5. **Select players to sell**: Multiselects grouped by position showing player name, position, and market value.
6. **Optimization configuration**: Select objective (SMV, Net Benefit, ROI, etc.), simulation speed (Standard, Fast, Faster), and signing strategy (All players, Young talents, Balanced, Veterans).
7. **Advanced filters**: League segmentation, banned clubs, banned players, temporal horizon.
8. **Budget configuration**: Set transfer budget. Checkbox for unlimited budget mode.
9. **Simulate**: Runs the full simulation.
10. **Analytics**: xGrowth ranking, similar players analysis, and fair price assessment (in tabs).
11. **AI Analysis**: LLM-generated structured report.

#### UI Features

- **Bilingual interface**: Toggle between Spanish and English with flag icons. All labels, captions, and AI analyses are language-aware.
- **Progress feedback**: A step-by-step progress bar with descriptive status messages and a spinner.

#### Output Display

- **Players Sold** (left column): Player image, name, position, market value, and destination club — each with a red down-arrow icon.
- **Recommended Signings** (right column): Player image, name, position, current value → predicted value, and origin club — each with a green up-arrow icon.
- **Financial summary**: Total cost, remaining budget, predicted value (1 year), and expected net financial benefit — with a color-coded delta indicator.
- **Final squad**: All remaining + new players displayed as cards grouped by position, sorted by market value descending. New signings are highlighted with a "NEW" badge.
- **Analytics tabs**: xGrowth ranking, similar players per signing, fair price comparison.
- **AI Analysis**: An expandable section where you can paste an API key (auto-detected from key prefix). The analysis is cached per language.

### React + FastAPI Frontend

A modern single-page application built with **React 18 + TypeScript + Vite + Tailwind CSS**, served by a **FastAPI** backend.

#### FastAPI Backend (`api/main.py`)

REST API endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/seasons` | GET | List available seasons |
| `/api/clubs` | GET | List clubs for a season |
| `/api/leagues` | GET | List leagues for a season |
| `/api/nationalities` | GET | List all distinct player nationalities |
| `/api/load-squad` | POST | Load a club's squad with predictions |
| `/api/sell-recommendations` | GET | Get sell recommendations for a club |
| `/api/simulate` | POST | Run simulation (synchronous) |
| `/api/simulate-stream` | POST | Run simulation with SSE progress events |
| `/api/analytics` | GET | xGrowth ranking + signing analysis |
| `/api/search-players` | GET | Full-text player search with filters |
| `/api/ai-summary` | POST | Generate LLM summary of last simulation |

#### React Frontend (`frontend/`)

- **ConfigPanel**: Season/club selection, squad loading, sell selection, optimization params, advanced filters
- **ResultsPanel**: Sold players, recommended signings, financial summary, squad display, analytics section, AI analysis
- **PlayerSearch**: Full-text search with position/value/age filters
- **AnalyticsSection**: xGrowth table, signing analysis with similar players, fair price tab

#### Auto-Deployment

Every time a scraping pipeline completes, an **auto-update trigger** comment in `streamlit_app.py` is updated with the current timestamp. Since Streamlit Cloud watches the main branch for changes, this forces a redeployment with the latest data.

---

## 4. Stack & Architecture

### Backend

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| HTTP Client | `tls-requests` (with `requests` fallback) |
| HTML Parsing | BeautifulSoup4 |
| Data Format | JSON (`orjson` for fast parsing when available) |
| ML Framework | XGBoost + Scikit-learn |
| Optimization | Custom Knapsack solver |
| API | FastAPI + Uvicorn |
| CI/CD | GitHub Actions |

### Frontend

| Component | Technology |
|-----------|------------|
| Streamlit | Streamlit Cloud |
| React SPA | React 18 + TypeScript + Vite |
| Styling | Tailwind CSS |
| Internationalization | Custom i18n module (ES/EN) |

### AI / LLM

| Provider | Display Name | Model | Environment Variable |
|----------|-------------|-------|---------------------|
| OpenAI | ChatGPT | gpt-4o-mini | `OPENAI_API_KEY` |
| Anthropic | Claude | claude-3-haiku | `ANTHROPIC_API_KEY` |
| Google | Gemini | gemini-2.0-flash | `GEMINI_API_KEY` |

### Project Structure

```
team-analysis-ai/
├── .github/workflows/            # CI/CD pipelines
│   ├── scheduled_scraper.yml     # Monthly all-leagues scraper
│   ├── input_scraper.yml         # Multi-league manual scraper
│   ├── input_single_scraper.yml  # Single-league manual scraper
│   ├── fill_club_names.yml       # Backfill missing club names
│   ├── precompute_cache_today.yml    # Daily cache update (00:30 CET)
│   └── precompute_cache_seasons.yml  # Season caches on push
├── api/
│   └── main.py                   # FastAPI backend (REST + SSE)
├── assets/
│   ├── arrows/                   # UI arrow icons
│   ├── language/                 # Flag SVGs for language toggle
│   └── logo.png                  # App logo
├── data/                         # Layout: see common/data_paths.py
│   ├── datasets/<entity>/      # Scraped JSON per entity (players, teams, …)
│   ├── cache/seasons/            # Precomputed season_data_*.json
│   ├── cache/clubs/              # e.g. tm_club API cache
│   └── …                         # derived/, runtime/, misc/, auth/
├── frontend/
│   ├── src/
│   │   ├── components/           # React components
│   │   │   ├── ConfigPanel.tsx   # Season/club/sim config
│   │   │   ├── ResultsPanel.tsx  # Results + analytics display
│   │   │   ├── PlayerSearch.tsx  # Player search with filters
│   │   │   ├── PlayerCard.tsx    # Player card component
│   │   │   ├── Header.tsx        # Header with language toggle
│   │   │   └── Footer.tsx        # Footer
│   │   ├── api.ts                # API client
│   │   ├── i18n.ts               # Translations (ES/EN)
│   │   ├── types.ts              # TypeScript interfaces
│   │   └── App.tsx               # Main application
│   ├── package.json
│   └── tsconfig.json
├── ml/
│   ├── datasets/                 # Cached training datasets (auto-split if >90MB)
│   ├── models/                   # Trained XGBoost models (.joblib)
│   │   ├── value_model_{season}.joblib          # Global models
│   │   ├── value_model_{season}_{segment}.joblib # Segmented models
│   │   └── *.json                # Model metrics
│   ├── feature_engineering.py    # 65+ features, PlayerFeatures dataclass
│   ├── train_pipeline.py         # Training CLI (global + segmented)
│   └── value_predictor.py        # ValuePredictor + SegmentedValuePredictor
├── scraping/
│   ├── base_scraper.py           # Base class + API retry logic
│   ├── utils/helpers.py          # JSON load/save, parse_date, DATA_DIR
│   ├── transfermarkt_leagues.py
│   ├── transfermarkt_teams.py
│   ├── transfermarkt_players.py
│   ├── transfermarkt_transfers.py
│   └── transfermarkt_valuations.py
├── scraping_tasks/               # CLI entry points for scrapers
│   ├── scrape_*.py               # Individual entity scrapers
│   └── combine_data.py           # Combine league-specific files into _all_ files
├── scripts/
│   ├── precompute_active_players_cache.py  # Precompute season caches
│   ├── run_demo.py               # Demo launcher (API + frontend)
│   └── export_predictions_to_xlsx.py
├── simulator/
│   ├── data_loader.py            # Centralized player data pipeline + caching
│   ├── knapsack_solver.py        # MCKP optimization + speed tiers
│   ├── transfer_simulator.py     # Main simulation engine
│   ├── transfer_engine.py        # Alternative API (SimulationResult)
│   ├── llm_summarizer.py         # LLM integration (detailed + simple prompts)
│   └── salary_calculator.py      # Effective budget heuristic (~10% of market value)
├── webapp/
│   └── i18n.py                   # Internationalization (ES/EN)
├── entities/
│   └── league.py / team.py / player.py / transfer.py / valuation.py / injury.py / competition.py
├── scripts/
│   ├── fill_club_names.py            # Backfill missing club names
│   ├── fill_players_data.py          # Backfill missing player data
│   ├── discover_leagues.py           # Discover leagues for scraper config
│   ├── patch_dataset_on_loan.py      # Add on_loan feature to existing datasets
│   └── patch_dataset_fair_price.py   # Add fair_price feature to existing datasets
├── streamlit_app.py              # Streamlit web app
├── demo.ipynb                    # Interactive demo notebook
├── requirements.txt
├── Dockerfile                    # Multi-stage Docker build (Node + Python)
├── docker-compose.yml            # One-command deployment
├── .dockerignore
└── README.md
```

---

## 5. Limitations & Trade-offs

### Scraping

- **Blocking is still common**: Headless scraping from virtual machines (GitHub runners) gets flagged more often than local scraping.
- **Conservative rate limiting**: 0.25s between requests + 60s retry pauses. Slower execution but higher success rate.
- **Internal API dependency**: The `tmapi-alpha.transfermarkt.technology` endpoint is undocumented and could change. HTML scraping is available as fallback.

### Simulation

- **Salary approximation**: Real salaries are complex (bonuses, taxes, etc.). The "10% of market value" rule is a simplification.
- **Transfer realism**: The simulation assumes any player can be bought if the budget allows, ignoring contracts, player will, or release clauses.
- **Data availability**: Relies on Transfermarkt data. Smaller leagues may have gaps in historical valuations.

### ML Model

- **Temporal limitation**: The model can only be as good as the features available. It doesn't capture intangibles like injuries, form, or media hype.
- **RMSE objective**: The model optimizes for absolute monetary error (RMSE). Segmented models mitigate this by training separate models per value range.
- **Extrapolation risk**: Multi-year horizon predictions use iterative extrapolation of the 1-year model, which compounds any systematic bias.

---

## 6. How to Run

### Option 1: Live App (Streamlit)

> **[https://calculadorafichajes.streamlit.app/](https://calculadorafichajes.streamlit.app/)**
>
> **Note**: The hosted app may be down due to Streamlit Cloud resource limits. If it's unavailable, run locally.

### Option 2: GitHub Actions (Scraping)

1. **Single League & Season**: Go to [Input Single Scraper](../../actions/workflows/input_single_scraper.yml) → Run workflow → Select league, season, entity
2. **Multiple Leagues & Seasons**: Go to [Input Scraper](../../actions/workflows/input_scraper.yml) → Run workflow → Configure JSON arrays
3. **Full Data (All Leagues × 10 Seasons)**: Go to [Scheduled Scraper](../../actions/workflows/scheduled_scraper.yml) → Run workflow

### Option 3: Docker

The easiest way to deploy online. Requires [Docker](https://docs.docker.com/get-docker/). All data (`data/`, `ml/models/`, precomputed caches) is baked into the image so the container is fully self-contained.

```bash
# Clone the repository
git clone https://github.com/pabloroldan98/team-analysis-ai.git
cd team-analysis-ai

# (Optional) Add LLM keys for AI analysis
cp .env.example .env   # then edit .env with your keys

# Build and run (frontend is compiled inside the container automatically)
docker compose up --build -d
```

The app will be available at [http://localhost:8000](http://localhost:8000).

To deploy on a cloud provider (AWS EC2, DigitalOcean, Render, Fly.io, Railway, etc.), push the image to a container registry or run `docker compose up` on the server with the same `.env` file.

```bash
# Stop
docker compose down

# Rebuild after code or data changes
docker compose up --build -d
```

### Option 4: Run Locally

**Prerequisites**

- Python 3.10+
- Node.js 18+ (only for React frontend)
- The simulator and ML pipeline require `*_all_*.json` files under `data/datasets/<entity>/` (e.g. `data/datasets/players/players_all_2024-2025.json`, `data/datasets/transfers/…`, `data/datasets/valuations/…`). Use the scrapers + `combine_data.py`, or download data that already follows this layout.

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

#### Precompute Season Caches (recommended, it should be already done)

Precomputing caches makes the app load instantly instead of spending minutes loading data:

```bash
# All historical seasons (run once)
python scripts/precompute_active_players_cache.py --all-seasons

# All historical seasons + next future season (e.g., 2026-2027)
python scripts/precompute_active_players_cache.py --all-seasons --include-next

# Today's data
python scripts/precompute_active_players_cache.py --season today

# Specific season (including future seasons like 2026-2027)
python scripts/precompute_active_players_cache.py --season 2024-2025
python scripts/precompute_active_players_cache.py --season 2026-2027
```

#### Run the Streamlit App

```bash
streamlit run streamlit_app.py
```

The app will open at [http://localhost:8501](http://localhost:8501).

#### Run the React + FastAPI App

```bash
# Option A: Use the demo launcher (builds frontend + starts API)
python scripts/run_demo.py

# Option B: Manual setup
cd frontend
npm install
npm run build
cd ..
uvicorn api.main:app --host 0.0.0.0 --port 8000

# Option C: Development mode (with hot-reload)
# Terminal 1: API
uvicorn api.main:app --reload --port 8000
# Terminal 2: Frontend dev server
cd frontend && npm run dev
```

The app will open at [http://localhost:8000](http://localhost:8000) (production) or [http://localhost:5173](http://localhost:5173) (dev mode).

#### Configure LLM (optional)

Copy `.env.example` to `.env` and add your API key:

```env
LLM_PROVIDER=gemini          # openai, anthropic, or gemini
GEMINI_API_KEY=your-key-here  # or OPENAI_API_KEY / ANTHROPIC_API_KEY
```

Alternatively, you can enter the API key directly in the app (in the AI Analysis section). The provider is auto-detected from the key prefix.

#### Run the Transfer Simulator (CLI)

```bash
# Basic simulation
python -m simulator.transfer_simulator --club "Real Madrid" --season 2022-2023

# Current data snapshot
python -m simulator.transfer_simulator --club "Real Madrid" --season today

# Without AI summary
python -m simulator.transfer_simulator --club "Real Madrid" --season 2022-2023 --no-summary

# Sell by value decline
python -m simulator.transfer_simulator --club "FC Barcelona" --season 2023-2024 --sell-by-value-decline

# With specific LLM provider
python -m simulator.transfer_simulator --club "FC Barcelona" --season 2022-2023 --llm-provider gemini
```

#### Train ML Models

```bash
# Train global model for a specific season
python -m ml.train_pipeline --season 2023-2024

# Train global + segmented models (4 value-range-specific models)
python -m ml.train_pipeline --season 2023-2024 --segmented

# Rebuild the training dataset from scratch
python -m ml.train_pipeline --season 2023-2024 --rebuild-dataset

# Semi-annual cutoffs (more training data)
python -m ml.train_pipeline --season 2023-2024 --cutoff-months 6 --rebuild-dataset
```

#### Run Scrapers Locally

```bash
python scraping_tasks/scrape_leagues.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_teams.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_players.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_transfers.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_valuations.py --leagues laliga --season 2025-2026
```

Output files are saved under `data/datasets/<entity>/`. Use `scraping_tasks/combine_data.py` to merge league-specific files into `*_all_*.json` inside those folders (required for the simulator).

#### Utility Scripts

```bash
# Export all players with predicted values to xlsx
python -m scripts.export_predictions_to_xlsx [--output FILE.xlsx] [--verbose]

# Fill missing club names in JSON files (API → local data → transfer history)
python scripts/fill_club_names.py [--dry-run]

# Discover leagues from Transfermarkt (output config for scrapers)
python scripts/discover_leagues.py

# Combine league-specific JSON into _all_ files
python scraping_tasks/combine_data.py --entity teams --season 2025-2026
python scraping_tasks/combine_data.py --entity players
```

---

## 7. Demo

Two demo formats are available:

### Interactive Notebook (`demo.ipynb`)

Best for **technical audiences** — shows code and results step by step.

```bash
jupyter notebook demo.ipynb
```

The notebook covers:

1. **Data loading** — 12,000+ players with ML predictions from precomputed caches
2. **Model metrics** — RMSE, MAE, MAPE for global and segmented models
3. **Feature importance** — Top-15 most important features in the XGBoost model
4. **Player search** — Filtered searches (e.g., "young midfielders over €20M")
5. **xGrowth ranking** — Top 25 players by predicted growth potential
6. **Full simulation** — Sell + buy optimization for a specific club
7. **Similar players analysis** — Financially comparable alternatives for each signing
8. **Multi-objective comparison** — Side-by-side results of SMV vs Net Benefit vs ROI vs Growth%

### Web App Demo (`scripts/run_demo.py`)

Best for **business/product audiences** — interactive UI, no code visible.

```bash
# React + FastAPI (modern UI)
python scripts/run_demo.py

# Streamlit
python scripts/run_demo.py --streamlit

# Custom port
python scripts/run_demo.py --port 8080
```

The script verifies cached data exists, builds the frontend, starts the server, and opens the browser automatically.

---

## 8. Future Improvements

- **Transfer negotiation realism**: Add release clauses, contract length, and player willingness as factors that affect whether a transfer goes through.
- **Multi-window simulation**: Simulate multiple consecutive transfer windows to see squad evolution over several seasons.
- **Wage structure visualization**: Display estimated wage impact of signings and departures alongside transfer fees.
- **More leagues**: Extend beyond the top 5 European leagues to include Portuguese Liga, Eredivisie, Liga MX, etc.
- **Injury and performance data**: Integrate external data sources (injuries, goals, assists) to improve ML predictions.
- **Log-target model**: Train an alternative model with `log(market_value)` as target, optimizing for percentage errors instead of absolute errors.
- **Real-time data pipeline**: Webhook-based updates when new transfers or valuations are published.

---

## License

This project is for educational and demonstration purposes.

## Author

Pablo Roldán — [GitHub](https://github.com/pabloroldan98)
