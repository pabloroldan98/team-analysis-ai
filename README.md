# Team Analysis AI ⚽

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.45+-red.svg)](https://streamlit.io/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Scraping and AI features to analyze football Teams** - A comprehensive football team analysis tool with web scraping capabilities and AI integration.

---

## 🎯 Overview

This project consists of two main components:

### 1. Data Integration & Web Scraping
A web scraping tool that extracts football data from Transfermarkt, including:
- **Players**: name, age, position, nationality, market value, contract details, etc.
- **Transfers**: player movements between clubs, transfer fees, loan details
- **Valuations**: historical market value data for players
- **Teams**: squad composition, total value, league information

### 2. AI Integration & Web Application
An interactive Streamlit web application for football transfer strategies simulation:
- Team analysis and visualization
- Transfer budget planning
- Squad valuation tracking
- AI-generated season summaries (mock implementation)

---

## 📁 Project Structure

```
team-analysis-ai/
├── .github/
│   └── workflows/
│       ├── scraper_scheduler.yml    # Automated weekly scraping
│       └── manual_scraper.yml       # Manual trigger for single teams
├── .streamlit/
│   └── config.toml                  # Streamlit configuration
├── scraping/
│   ├── models/
│   │   ├── player.py               # Player data model
│   │   ├── team.py                 # Team data model
│   │   ├── transfer.py             # Transfer data model
│   │   └── valuation.py            # Valuation data model
│   ├── utils/
│   │   └── helpers.py              # Utility functions
│   └── transfermarkt_scraper.py    # Main scraper module
├── webapp/
│   └── i18n.py                     # Internationalization (ES/EN)
├── data/
│   ├── json/                       # JSON output files
│   └── csv/                        # CSV output files
├── assets/
│   ├── logos/                      # Team logos
│   └── language/                   # Language flag icons
├── streamlit_app.py                # Main Streamlit application
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

---

## 🛠️ Technical Decisions

### Libraries & Frameworks

| Component | Technology | Reason |
|-----------|------------|--------|
| **Web Scraping** | `BeautifulSoup4` + `tls-requests` | Robust HTML parsing with TLS support to handle anti-scraping measures |
| **Data Storage** | JSON + CSV | Dual format for flexibility - JSON for structured data, CSV for easy analysis |
| **Web Framework** | `Streamlit` | Rapid development of data apps, great for prototyping and demos |
| **Data Processing** | `Pandas` | Industry standard for data manipulation |
| **Visualization** | `Matplotlib` | Flexible charting capabilities |
| **i18n** | Custom module | Simple key-value translation for ES/EN support |

### Architecture Decisions

1. **Modular Design**: Separate modules for scraping, models, and webapp allow independent development and testing
2. **Pipeline Approach**: GitHub Actions enable automated data updates, similar to ETL pipelines
3. **Caching**: Scraper implements caching to avoid redundant requests
4. **Rate Limiting**: Built-in delays between requests to respect server limits

---

## ⚠️ Challenges & Solutions

### Anti-Scraping Mechanisms

**Challenge**: Transfermarkt implements various anti-bot protections.

**Solutions**:
- Using `tls-requests` library for TLS fingerprint matching
- Implementing realistic User-Agent headers
- Adding configurable delays between requests (default: 2 seconds)
- Retry mechanism with exponential backoff

### Data Inconsistencies

**Challenge**: Player names, team names, and date formats vary across pages.

**Solutions**:
- `normalize_team_name()` function with comprehensive mapping dictionary
- `find_similar_string()` for fuzzy matching using sequence similarity
- Multiple date format parsers as fallbacks
- Unidecode for handling special characters

### Large Dataset Handling

**Challenge**: Scraping entire leagues generates large datasets.

**Solutions**:
- Progress callbacks for real-time feedback
- Incremental saving during scraping
- Deduplication of transfers by ID

---

## 🚀 Enhancements Implemented

1. **Multi-League Support**: Scrape entire leagues, not just single teams
2. **Concurrent Pipelines**: GitHub Actions matrix for parallel league scraping
3. **Bilingual Interface**: Full Spanish/English support
4. **Historical Valuations**: Track market value changes over time
5. **Transfer History**: Complete transfer timeline for players
6. **Export Options**: Download data as CSV or Excel

---

## 📦 Installation

### Prerequisites
- Python 3.10 or higher
- pip package manager

### Setup

```bash
# Clone the repository
git clone https://github.com/pabloroldan98/team-analysis-ai.git
cd team-analysis-ai

# Create virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## 🖥️ Running Locally

### Streamlit Application

```bash
streamlit run streamlit_app.py
```

The app will open at `http://localhost:8501`

### Command-Line Scraper

```bash
# Scrape a single team
python -m scraping.transfermarkt_scraper --team "Real Madrid" --season "2024-2025"

# Scrape an entire league
python -m scraping.transfermarkt_scraper --league "laliga" --season "2024-2025"

# Options
#   --team, -t       Team name to scrape
#   --league, -l     League code (laliga, premier, seriea, bundesliga, ligue1)
#   --season, -s     Season (e.g., 2024-2025)
#   --no-details     Skip detailed player info
#   --no-transfers   Skip transfer history
#   --no-valuations  Skip valuation history
#   --delay, -d      Delay between requests (default: 2.0)
#   --quiet, -q      Suppress output
```

---

## 🌐 Deployment

### Streamlit Cloud (Recommended)

1. Push your code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io/)
3. Connect your repository
4. Deploy!

### Alternative Platforms

- **Render**: Free tier available
- **Railway**: Simple deployment
- **Heroku**: Classic PaaS option

---

## 📊 Data Schema

### Players
```json
{
  "player_id": "string",
  "name": "string",
  "current_club": "string",
  "age": "integer",
  "birth_date": "date",
  "nationality": "string",
  "position": "string (GK/DEF/MID/ATT)",
  "preferred_foot": "string",
  "height": "integer (cm)",
  "current_market_value": "float (euros)",
  "contract_expires": "date",
  "img_url": "string"
}
```

### Transfers
```json
{
  "transfer_id": "string",
  "player_id": "string",
  "player_name": "string",
  "from_club": "string",
  "to_club": "string",
  "transfer_fee": "float (euros)",
  "transfer_date": "date",
  "transfer_type": "string (purchase/loan/free/loan_return)"
}
```

### Valuations
```json
{
  "valuation_id": "string",
  "player_id": "string",
  "player_name": "string",
  "valuation_amount": "float (euros)",
  "valuation_date": "date",
  "club_at_valuation": "string"
}
```

---

## 🔄 Automated Pipelines

The project includes GitHub Actions workflows for automated data updates:

- **`scraper_scheduler.yml`**: Runs weekly to update top 5 leagues data
- **`manual_scraper.yml`**: Manual trigger for single team/league scraping

Data is automatically committed to the repository after each run.

---

## 📝 Limitations & Trade-offs

1. **No Real AI Engine**: The simulator uses mock logic; a production version would integrate real ML models
2. **Rate Limiting**: Scraping is intentionally slow to avoid being blocked
3. **Static Data**: Data is updated via pipelines, not real-time
4. **No Authentication**: The app doesn't persist user data or require login
5. **Transfermarkt Dependency**: Data availability depends on source website structure

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## ⚠️ Disclaimer

This tool is for educational and analysis purposes only. Data is extracted from Transfermarkt and should be used in compliance with their terms of service. The creators of this tool are not responsible for any misuse.

---

## 👤 Author

**Pablo Roldán** - [GitHub](https://github.com/pabloroldan98)
