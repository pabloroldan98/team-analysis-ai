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

#### Budget Calculation

Since exact player salaries are not publicly available, we approximate using a simple heuristic:

```
Effective Budget = min(Transfer Budget, Salary Budget × 10)
```

The reasoning: a player's annual salary is roughly **10% of their market value**. So either you're limited by how much you can spend on transfers, or by how much salary you can take on — whichever is lower.

#### Sell Phase

The simulator randomly selects **5 to 10 players** to put on the transfer market (max 3 per position). For each player:

- A **destination club** is found at random among clubs whose total squad value is at least **10× the player's market value** (a rough proxy for "can afford this player").
- If no club qualifies, the player **is not sold** (no buyer found).
- Revenue from successful sales is added to the budget.

#### Buy Phase

The positions vacated by sold players need to be filled. The simulator:

1. Takes all available players from the market (excluding the selling club's squad and sold players).
2. **Predicts their future value** using the ML model for that season.
3. Runs the **Grouped Knapsack algorithm** to find the set of players that **maximizes total predicted value** while filling the required positions and staying within budget.

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

- **Player attributes**: age, nationality, height, preferred foot, position.
- **Valuation history**: current market value, value trend, number of historical valuations.
- **Contextual features**: `is_playing_in_home_country`, league tier, club market value.
- **Categorical binning**: High-cardinality features like nationality and club are binned to reduce dimensionality.

#### Temporal Integrity

To prevent data leakage, models are **strictly limited to historical data**:

- The model for the **2022-2023 season** is trained on all valuations up to and including **01/07/2022**.
- It predicts player values for **01/07/2023**.
- It never sees data from the future — that would be cheating.

The train/validation split is also **temporal**: older seasons go to training, the most recent season(s) go to validation.

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

## Stack & Architecture

### Backend

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| HTTP Client | `tls-requests` (with `requests` fallback) |
| HTML Parsing | BeautifulSoup4 |
| Data Format | JSON |
| ML Framework | XGBoost + Scikit-learn |
| Optimization | Custom Knapsack solver |
| CI/CD | GitHub Actions |

### Frontend

| Component | Technology |
|-----------|------------|
| Framework | Streamlit *(coming soon)* |

### AI Models

| Provider | Model | Usage |
|----------|-------|-------|
| OpenAI | gpt-4o-mini | `OPENAI_API_KEY` |
| Anthropic | claude-3-haiku | `ANTHROPIC_API_KEY` |
| Google Gemini | gemini-2.0-flash | `GEMINI_API_KEY` |

### Project Structure

```
team-analysis-ai/
├── .github/workflows/       # CI/CD scraping pipelines
├── data/json/               # Scraped data (JSON)
├── ml/
│   ├── datasets/            # Cached training datasets
│   ├── models/              # Trained XGBoost models (.joblib)
│   ├── feature_engineering.py
│   ├── train_pipeline.py
│   └── value_predictor.py
├── scraping/
│   ├── base_scraper.py
│   ├── transfermarkt_leagues.py
│   ├── transfermarkt_teams.py
│   ├── transfermarkt_players.py
│   ├── transfermarkt_transfers.py
│   └── transfermarkt_valuations.py
├── scraping_tasks/          # CLI entry points for scrapers
├── simulator/
│   ├── knapsack_solver.py   # MCKP optimization
│   ├── transfer_simulator.py # Main simulation engine
│   └── llm_summarizer.py    # LLM integration
├── league.py / team.py / player.py / transfer.py / valuation.py
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
- **Random sales**: The decision to sell is random (within position limits) rather than strategic. This is by design — it forces the optimizer to react to different scenarios.
- **Data availability**: Relies on Transfermarkt data. Smaller leagues may have gaps in historical valuations.

### ML Model

- **Temporal limitation**: The model can only be as good as the features available. It doesn't capture intangibles like injuries, form, or media hype.
- **RMSE objective**: The model optimizes for absolute monetary error (RMSE). This means it prioritizes accuracy for expensive players over cheap ones.

---

## How to Run

### Option 1: GitHub Actions (Scraping)

The easiest way to run the scrapers is through GitHub Actions workflows:

1. **Single League & Season**: Go to [Input Single Scraper](../../actions/workflows/input_single_scraper.yml) → Run workflow → Select league, season, entity
2. **Multiple Leagues & Seasons**: Go to [Input Scraper](../../actions/workflows/input_scraper.yml) → Run workflow → Configure JSON arrays
3. **Full Data (All Leagues × 10 Seasons)**: Go to [Scheduled Scraper](../../actions/workflows/scheduled_scraper.yml) → Run workflow

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
```

#### Configure LLM (optional)

Copy `.env.example` to `.env` and add your API key:

```env
LLM_PROVIDER=gemini          # openai, anthropic, or gemini
GEMINI_API_KEY=your-key-here  # or OPENAI_API_KEY / ANTHROPIC_API_KEY
```

#### Run the Transfer Simulator

```bash
# Basic simulation (with AI summary if API key is configured)
python -m simulator.transfer_simulator --club "Real Madrid" --season 2022-2023

# Without AI summary
python -m simulator.transfer_simulator --club "Real Madrid" --season 2022-2023 --no-summary

# With specific LLM provider
python -m simulator.transfer_simulator --club "FC Barcelona" --season 2022-2023 --llm-provider gemini
```

#### Run the ML Pipeline

```bash
# Train model for a specific season
python -m ml.train_pipeline --season 2022-2023

# Rebuild the training dataset from scratch
python -m ml.train_pipeline --season 2022-2023 --rebuild-dataset
```

#### Run Scrapers Locally

```bash
python scraping_tasks/scrape_leagues.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_teams.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_players.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_transfers.py --leagues laliga --season 2025-2026
python scraping_tasks/scrape_valuations.py --leagues laliga --season 2025-2026
```

Output files are saved to `data/json/`.

---

## License

This project is for educational and demonstration purposes.

## Author

Pablo Roldán — [GitHub](https://github.com/pabloroldan98)
