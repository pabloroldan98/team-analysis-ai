"""
Canonical filesystem layout under ``data/``.

Use these helpers instead of hardcoding ``Path("data/...")`` so scrapers, ML,
simulator, and CI stay aligned.

Layout (functional subfolders):

- ``auth/`` — authentication-related local artifacts.
- ``datasets/`` — scraped season datasets by entity (``players``, ``teams``,
  ``transfers``, ``valuations``, ``leagues``, ``competitions``, ``injuries``,
  ``metadata``).
- ``derived/`` — precomputed indexes and model-ready aggregates (``players/``,
  ``clubs/``).
- ``cache/`` — regenerable caches: ``seasons/``, ``clubs/``, ``scraping/``.
- ``runtime/`` — app-managed JSON (e.g. ``club_finance_inputs/``).
- ``misc/`` — one-off maintenance / temporary JSON helpers.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Sequence

ROOT_DIR: Path = Path(__file__).resolve().parent.parent

# --- Root data directory ----------------------------------------------------
DATA_DIR: Path = ROOT_DIR / "data"

AUTH_DIR: Path = DATA_DIR / "auth"
DATASETS_ROOT: Path = DATA_DIR / "datasets"
DERIVED_DIR: Path = DATA_DIR / "derived"
CACHE_ROOT: Path = DATA_DIR / "cache"
RUNTIME_DIR: Path = DATA_DIR / "runtime"
MISC_DIR: Path = DATA_DIR / "misc"

# --- Scraped season datasets (by entity) ------------------------------------
DS_PLAYERS: Path = DATASETS_ROOT / "players"
DS_TEAMS: Path = DATASETS_ROOT / "teams"
DS_TRANSFERS: Path = DATASETS_ROOT / "transfers"
DS_VALUATIONS: Path = DATASETS_ROOT / "valuations"
DS_LEAGUES: Path = DATASETS_ROOT / "leagues"
DS_COMPETITIONS: Path = DATASETS_ROOT / "competitions"
DS_INJURIES: Path = DATASETS_ROOT / "injuries"
DS_METADATA: Path = DATASETS_ROOT / "metadata"

DATASET_ENTITY_DIRS: Dict[str, Path] = {
    "players": DS_PLAYERS,
    "teams": DS_TEAMS,
    "transfers": DS_TRANSFERS,
    "valuations": DS_VALUATIONS,
    "leagues": DS_LEAGUES,
    "competitions": DS_COMPETITIONS,
    "injuries": DS_INJURIES,
}

# Prefixes for JSON stems / globs (order only matters for documentation)
KNOWN_ENTITY_PREFIXES: Sequence[str] = tuple(DATASET_ENTITY_DIRS.keys())

# --- Derived (indexes, model-ready aggregates) -------------------------------
DERIVED_PLAYERS: Path = DERIVED_DIR / "players"
DERIVED_CLUBS: Path = DERIVED_DIR / "clubs"

# --- Cache (regenerable) ----------------------------------------------------
CACHE_SEASONS: Path = CACHE_ROOT / "seasons"
CACHE_CLUBS: Path = CACHE_ROOT / "clubs"
CACHE_SCRAPING: Path = CACHE_ROOT / "scraping"

# --- Runtime (app-written JSON) ---------------------------------------------
RUNTIME_CLUB_FINANCE_INPUTS: Path = RUNTIME_DIR / "club_finance_inputs"

# Club name API cache file (see ``TmClubApiCache``)
TM_CLUB_API_CACHE_FILE: Path = CACHE_CLUBS / "tm_club_api_cache.json"


def dataset_dir_for_entity(entity: str) -> Path:
    """Directory for scraped JSON of *entity* (e.g. ``"players"``)."""
    key = entity.lower()
    if key not in DATASET_ENTITY_DIRS:
        raise ValueError(f"Unknown dataset entity {entity!r}; expected one of {sorted(DATASET_ENTITY_DIRS)}")
    return DATASET_ENTITY_DIRS[key]


def dataset_subdir_for_stem(stem: str) -> Path:
    """Directory where a JSON *stem* (no ``.json``) should live."""
    s = stem.lower()
    if s.startswith("discovered_leagues"):
        return DS_METADATA
    for ent in KNOWN_ENTITY_PREFIXES:
        if s == ent or s.startswith(f"{ent}_"):
            return DATASET_ENTITY_DIRS[ent]
    return MISC_DIR


def json_search_dirs_for_glob(glob_pattern: str) -> List[Path]:
    """
    Which directories to scan for *glob_pattern* when listing / loading JSON.

    Patterns that start with ``players_``, ``teams_``, … only hit that entity's
    folder. Broad patterns (e.g. ``*_all_*.json``) search every entity folder
    plus ``misc/`` (metadata uses ``discovered_leagues*`` only in ``metadata/``).
    """
    gpl = glob_pattern.lower()
    for ent in KNOWN_ENTITY_PREFIXES:
        if gpl.startswith(f"{ent}_") or gpl.startswith(f"{ent}."):
            return [DATASET_ENTITY_DIRS[ent]]
    if gpl.startswith("discovered_leagues"):
        return [DS_METADATA]
    if "*_all_*" in gpl or gpl in ("*_all_*.json",):
        return list(DATASET_ENTITY_DIRS.values()) + [MISC_DIR]
    if gpl == "*.json":
        return list(DATASET_ENTITY_DIRS.values()) + [MISC_DIR, DS_METADATA]
    return [MISC_DIR, DS_METADATA]


def ensure_data_tree() -> None:
    """Create the functional ``data/`` layout if missing."""
    dirs = [
        AUTH_DIR,
        DS_PLAYERS,
        DS_TEAMS,
        DS_TRANSFERS,
        DS_VALUATIONS,
        DS_LEAGUES,
        DS_COMPETITIONS,
        DS_INJURIES,
        DS_METADATA,
        DERIVED_PLAYERS,
        DERIVED_CLUBS,
        CACHE_SEASONS,
        CACHE_CLUBS,
        CACHE_SCRAPING,
        RUNTIME_CLUB_FINANCE_INPUTS,
        MISC_DIR,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


# Backwards alias: code that still expects a single “cache root” for seasons
CACHE_DIR_SEASONS = CACHE_SEASONS
