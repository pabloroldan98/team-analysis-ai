# Team Analysis AI

Sistema de scraping y análisis de datos de fútbol con simulador de estrategias de fichajes.

## Estructura del Proyecto

```
team-analysis-ai/
├── player.py                    # Clase Player
├── team.py                      # Clase Team
├── scraping/                    # Módulo de scrapers
│   ├── base_scraper.py          # Clase base con utilidades comunes
│   ├── transfermarkt_teams.py   # Scraper de equipos
│   ├── transfermarkt_players.py # Scraper de jugadores
│   ├── transfermarkt_transfers.py # Scraper de transferencias
│   ├── transfermarkt_valuations.py # Scraper de valoraciones
│   └── transfermarkt_logos.py   # Scraper de logos
├── scraping_tasks/              # Scripts ejecutables
│   ├── scrape_teams.py          # Descarga datos de equipos
│   ├── scrape_players.py        # Descarga datos de jugadores
│   ├── scrape_transfers.py      # Descarga datos de transferencias
│   ├── scrape_valuations.py     # Descarga historial de valoraciones
│   ├── scrape_logos.py          # Descarga logos de equipos
│   └── scrape_all.py            # Ejecuta todos los scrapers
├── data/                        # Datos JSON generados
├── assets/
│   ├── logos/                   # Logos descargados
│   └── team_logos/              # Logos estáticos
├── webapp/                      # Módulo de la app web
│   └── i18n.py                  # Traducciones ES/EN
├── streamlit_app.py             # Aplicación Streamlit (simulador)
├── .github/workflows/           # Pipelines de GitHub Actions
│   ├── scrape_teams.yml
│   ├── scrape_players.yml
│   ├── scrape_transfers.yml
│   ├── scrape_logos.yml
│   └── scrape_all.yml
└── requirements.txt
```

## Instalación

```bash
# Clonar repositorio
git clone https://github.com/pabloroldan98/team-analysis-ai.git
cd team-analysis-ai

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o: venv\Scripts\activate  # Windows

# Instalar dependencias
pip install -r requirements.txt
```

## Uso

### Scraping Manual

Cada scraper se ejecuta de forma independiente:

```bash
# Descargar datos de equipos (top 5 ligas europeas)
python scraping_tasks/scrape_teams.py

# Descargar datos de jugadores
python scraping_tasks/scrape_players.py

# Descargar transferencias
python scraping_tasks/scrape_transfers.py

# Descargar logos de equipos
python scraping_tasks/scrape_logos.py

# Ejecutar todos los scrapers
python scraping_tasks/scrape_all.py
```

### Opciones Disponibles

Todos los scrapers soportan estas opciones:

```bash
python scraping_tasks/scrape_teams.py --help

# Ejemplo: solo LaLiga y Premier League
python scraping_tasks/scrape_teams.py --leagues laliga premier

# Ejemplo: temporada específica
python scraping_tasks/scrape_players.py --season 2023-2024

# Ejemplo: con menos delay (más rápido, más riesgo de bloqueo)
python scraping_tasks/scrape_transfers.py --delay 1.0
```

### Ligas Disponibles

- `laliga` - La Liga (España)
- `premier` - Premier League (Inglaterra)
- `bundesliga` - Bundesliga (Alemania)
- `seriea` - Serie A (Italia)
- `ligue1` - Ligue 1 (Francia)

### Pipelines Automáticos

Los workflows de GitHub Actions ejecutan los scrapers automáticamente:

| Workflow | Frecuencia | Descripción |
|----------|------------|-------------|
| `scrape_teams.yml` | Semanal (Domingo 2:00 UTC) | Datos de equipos |
| `scrape_players.yml` | Semanal (Domingo 3:00 UTC) | Datos de jugadores |
| `scrape_transfers.yml` | Semanal (Domingo 4:00 UTC) | Transferencias |
| `scrape_logos.yml` | Mensual (Día 1, 5:00 UTC) | Logos de equipos |
| `scrape_all.yml` | Mensual (Día 15, 1:00 UTC) | Actualización completa |

También pueden ejecutarse manualmente desde la pestaña "Actions" en GitHub.

## Datos Generados

Los datos se guardan en formato JSON en la carpeta `data/`:

```
data/
├── teams_laliga_2024-2025.json
├── teams_premier_2024-2025.json
├── teams_all_2024-2025.json
├── players_laliga_2024-2025.json
├── players_all_2024-2025.json
├── transfers_laliga_2024-2025.json
├── logos_laliga_2024-2025.json
└── ...
```

## Clases de Datos

### Player

```python
from player import Player

player = Player(
    player_id="123456",
    name="Vinicius Junior",
    team="Real Madrid",
    team_id="418",
    position="ATT",
    age=24,
    nationality="Brazil",
    market_value=150000000,  # 150M€
)

# Serialización
data = player.to_dict()
player = Player.from_dict(data)
```

### Team

```python
from team import Team

team = Team(
    team_id="418",
    name="Real Madrid",
    league="laliga",
    country="Spain",
    total_market_value=1050000000,  # 1.05B€
    squad_size=25,
    average_age=26.5,
)

# Serialización
data = team.to_dict()
team = Team.from_dict(data)
```

## Aplicación Streamlit

El simulador de estrategias de fichajes (en desarrollo):

```bash
streamlit run streamlit_app.py
```

## Notas Técnicas

### Anti-Scraping

- Se usa `tls-requests` para bypass de fingerprinting TLS
- Delay configurable entre peticiones (default: 2 segundos)
- Headers de navegador realistas
- Reintentos automáticos con backoff exponencial

### Consideraciones

- El scraper de valoraciones (`scrape_valuations.py`) es muy lento por el volumen de datos
- Se recomienda ejecutar con pocas ligas para pruebas
- Los datos pueden tardar en actualizarse en Transfermarkt

## Licencia

MIT License - Ver [LICENSE](LICENSE)
