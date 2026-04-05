# scraping/base_scraper.py
"""
Base scraper class with common functionality for Transfermarkt scraping.
"""
from __future__ import annotations

import json
import os
import re
import time
import random
import hashlib
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests
from bs4 import BeautifulSoup

try:
    import tls_requests
    USE_TLS = True
except ImportError:
    USE_TLS = False

from unidecode import unidecode


ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data" / "json"

# Rotating header pool
HEADER_POOL = [
    # Chrome / Windows 10 (older)
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
    },
    # Chrome / Windows 10 (newer)
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    },
    # Chrome / Windows 11
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    },
    # Chrome / macOS
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    },
    # Chrome / macOS Sonoma
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        )
    },
    # Chrome / Linux
    {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    },
    # Firefox / Windows
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
            "Gecko/20100101 Firefox/121.0"
        )
    },
    # Firefox / macOS
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:122.0) "
            "Gecko/20100101 Firefox/122.0"
        )
    },
    # Safari / macOS Ventura
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.1 Safari/605.1.15"
        )
    },
    # Safari / macOS Sonoma
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.3 Safari/605.1.15"
        )
    },
    # Edge / Windows
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        )
    },
    # Opera / Windows
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0"
        )
    },
]


def pick_headers() -> dict:
    """Pick a random header from the pool."""
    return random.choice(HEADER_POOL).copy()


class BaseScraper:
    """Base class for Transfermarkt scrapers."""
    
    BASE_URL = "https://www.transfermarkt.com"
    
    # ─── Single source of truth: metadata + URL for every league ───
    # Cache for local file name map (loaded once across all scrapers)
    _local_name_map = None
    # Each entry: name, country, tier, id (Transfermarkt), url (path)
    LEAGUE_INFO = {
        # ── Europe – Tier 1 ──────────────────────────────────────
        "premier"                          : {"name": "Premier League",               "country": "England",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "GB1",  "url": "/premier-league/startseite/wettbewerb/GB1"},
        "laliga"                           : {"name": "LaLiga",                       "country": "Spain",              "tier": 1 , "is_cup": False, "is_youth": False, "id": "ES1",  "url": "/laliga/startseite/wettbewerb/ES1"},
        "seriea"                           : {"name": "Serie A",                      "country": "Italy",              "tier": 1 , "is_cup": False, "is_youth": False, "id": "IT1",  "url": "/serie-a/startseite/wettbewerb/IT1"},
        "bundesliga"                       : {"name": "Bundesliga",                   "country": "Germany",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "L1",   "url": "/bundesliga/startseite/wettbewerb/L1"},
        "ligue1"                           : {"name": "Ligue 1",                      "country": "France",             "tier": 1 , "is_cup": False, "is_youth": False, "id": "FR1",  "url": "/ligue-1/startseite/wettbewerb/FR1"},
        "liga_portugal"                    : {"name": "Liga Portugal",                "country": "Portugal",           "tier": 1 , "is_cup": False, "is_youth": False, "id": "PO1",  "url": "/liga-portugal/startseite/wettbewerb/PO1"},
        "turkish"                          : {"name": "Süper Lig",                    "country": "Turkey",             "tier": 1 , "is_cup": False, "is_youth": False, "id": "TR1",  "url": "/super-lig/startseite/wettbewerb/TR1"},
        "eredivisie"                       : {"name": "Eredivisie",                   "country": "Netherlands",        "tier": 1 , "is_cup": False, "is_youth": False, "id": "NL1",  "url": "/eredivisie/startseite/wettbewerb/NL1"},
        "russian"                          : {"name": "Russian Premier League",       "country": "Russia",             "tier": 1 , "is_cup": False, "is_youth": False, "id": "RU1",  "url": "/premier-liga/startseite/wettbewerb/RU1"},
        "belgian"                          : {"name": "Jupiler Pro League",           "country": "Belgium",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "BE1",  "url": "/jupiler-pro-league/startseite/wettbewerb/BE1"},
        "greek"                            : {"name": "Super League Greece",          "country": "Greece",             "tier": 1 , "is_cup": False, "is_youth": False, "id": "GR1",  "url": "/super-league-1/startseite/wettbewerb/GR1"},
        "ukrainian"                        : {"name": "Ukrainian Premier League",     "country": "Ukraine",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "UKR1", "url": "/premier-liga/startseite/wettbewerb/UKR1"},
        "czech"                            : {"name": "Chance Liga",                  "country": "Czech Republic",     "tier": 1 , "is_cup": False, "is_youth": False, "id": "TS1",  "url": "/chance-liga/startseite/wettbewerb/TS1"},
        "danish"                           : {"name": "Superliga",                    "country": "Denmark",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "DK1",  "url": "/superliga/startseite/wettbewerb/DK1"},
        "scottish"                         : {"name": "Scottish Premiership",         "country": "Scotland",           "tier": 1 , "is_cup": False, "is_youth": False, "id": "SC1",  "url": "/scottish-premiership/startseite/wettbewerb/SC1"},
        "polish"                           : {"name": "Ekstraklasa",                  "country": "Poland",             "tier": 1 , "is_cup": False, "is_youth": False, "id": "PL1",  "url": "/pko-bp-ekstraklasa/startseite/wettbewerb/PL1"},
        "swiss"                            : {"name": "Swiss Super League",           "country": "Switzerland",        "tier": 1 , "is_cup": False, "is_youth": False, "id": "C1",   "url": "/super-league/startseite/wettbewerb/C1"},
        "austrian"                         : {"name": "Austrian Bundesliga",          "country": "Austria",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "A1",   "url": "/bundesliga/startseite/wettbewerb/A1"},
        "norwegian"                        : {"name": "Eliteserien",                  "country": "Norway",             "tier": 1 , "is_cup": False, "is_youth": False, "id": "NO1",  "url": "/eliteserien/startseite/wettbewerb/NO1"},
        "serbian"                          : {"name": "Super liga Srbije",            "country": "Serbia",             "tier": 1 , "is_cup": False, "is_youth": False, "id": "SER1", "url": "/super-liga-srbije/startseite/wettbewerb/SER1"},
        "swedish"                          : {"name": "Allsvenskan",                  "country": "Sweden",             "tier": 1 , "is_cup": False, "is_youth": False, "id": "SE1",  "url": "/allsvenskan/startseite/wettbewerb/SE1"},
        "romanian"                         : {"name": "SuperLiga",                    "country": "Romania",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "RO1",  "url": "/superliga/startseite/wettbewerb/RO1"},
        "croatian"                         : {"name": "SuperSport HNL",               "country": "Croatia",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "KR1",  "url": "/supersport-hnl/startseite/wettbewerb/KR1"},
        "bulgarian"                        : {"name": "efbet Liga",                   "country": "Bulgaria",           "tier": 1 , "is_cup": False, "is_youth": False, "id": "BU1",  "url": "/efbet-liga/startseite/wettbewerb/BU1"},
        "israeli"                          : {"name": "Ligat ha'Al",                  "country": "Israel",             "tier": 1 , "is_cup": False, "is_youth": False, "id": "ISR1", "url": "/ligat-haal/startseite/wettbewerb/ISR1"},
        "cypriot"                          : {"name": "Cyprus League",                "country": "Cyprus",             "tier": 1 , "is_cup": False, "is_youth": False, "id": "ZYP1", "url": "/cyprus-league/startseite/wettbewerb/ZYP1"},
        "hungarian"                        : {"name": "NB I.",                        "country": "Hungary",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "UNG1", "url": "/nemzeti-bajnoksag/startseite/wettbewerb/UNG1"},
        "azerbaijani"                      : {"name": "Premyer Liqa",                 "country": "Azerbaijan",         "tier": 1 , "is_cup": False, "is_youth": False, "id": "AZ1",  "url": "/premyer-liqa/startseite/wettbewerb/AZ1"},
        "slovak"                           : {"name": "Niké Liga",                    "country": "Slovakia",           "tier": 1 , "is_cup": False, "is_youth": False, "id": "SLO1", "url": "/nike-liga/startseite/wettbewerb/SLO1"},
        "premier_liga_kas1"                : {"name": "Premier Liga",                 "country": "Kazakhstan",         "tier": 1 , "is_cup": False, "is_youth": False, "id": "KAS1", "url": "/premier-liga/startseite/wettbewerb/KAS1"},
        "prva_liga_sl1"                    : {"name": "Prva Liga",                    "country": "Slovenia",           "tier": 1 , "is_cup": False, "is_youth": False, "id": "SL1",  "url": "/prva-liga/startseite/wettbewerb/SL1"},
        "vysheyshaya_liga_wer1"            : {"name": "Vysheyshaya Liga",             "country": "Belarus",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "WER1", "url": "/vysheyshaya-liga/startseite/wettbewerb/WER1"},
        "premijer_liga_bih_bos1"           : {"name": "Premijer Liga BiH",            "country": "Bosnia-Herzegovina", "tier": 1 , "is_cup": False, "is_youth": False, "id": "BOS1", "url": "/premijer-liga-bosne-i-hercegovine/startseite/wettbewerb/BOS1"},
        "premier_league_arm1"              : {"name": "Premier League",               "country": "Armenia",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "ARM1", "url": "/premier-league/startseite/wettbewerb/ARM1"},
        "superliga_e_kosovës_ko1"          : {"name": "Superliga e Kosovës",          "country": "Kosovo",             "tier": 1 , "is_cup": False, "is_youth": False, "id": "KO1",  "url": "/superliga-e-kosoves/startseite/wettbewerb/KO1"},
        "kategoria_superiore_alb1"         : {"name": "Kategoria Superiore",          "country": "Albania",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "ALB1", "url": "/kategoria-superiore/startseite/wettbewerb/ALB1"},
        "premier_league_opening_round_mt1n": {"name": "Premier League Opening Round", "country": "Malta",              "tier": 1 , "is_cup": False, "is_youth": False, "id": "MT1N", "url": "/premier-league-opening-round/startseite/wettbewerb/MT1N"},
        "premier_league_closing_round_mt1p": {"name": "Premier League Closing Round", "country": "Malta",              "tier": 1 , "is_cup": False, "is_youth": False, "id": "MT1P", "url": "/premier-league-closing-round/startseite/wettbewerb/MT1P"},
        "virsliga_let1"                    : {"name": "Virsliga",                     "country": "Latvia",             "tier": 1 , "is_cup": False, "is_youth": False, "id": "LET1", "url": "/virsliga/startseite/wettbewerb/LET1"},
        "toplyga_li1"                      : {"name": "Toplyga",                      "country": "Lithuania",          "tier": 1 , "is_cup": False, "is_youth": False, "id": "LI1",  "url": "/toplyga/startseite/wettbewerb/LI1"},
        "veikkausliiga_fi1"                : {"name": "Veikkausliiga",                "country": "Finland",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "FI1",  "url": "/veikkausliiga/startseite/wettbewerb/FI1"},
        "prva_liga_maz1"                   : {"name": "Prva liga",                    "country": "North Macedonia",    "tier": 1 , "is_cup": False, "is_youth": False, "id": "MAZ1", "url": "/prva-makedonska-fudbalska-liga/startseite/wettbewerb/MAZ1"},
        "premier_division_ir1"             : {"name": "Premier Division",             "country": "Ireland",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "IR1",  "url": "/league-of-ireland-premier-division/startseite/wettbewerb/IR1"},
        "besta_deild_is1"                  : {"name": "Besta deild",                  "country": "Iceland",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "IS1",  "url": "/besta-deild/startseite/wettbewerb/IS1"},
        "erovnuli_liga_ge1n"               : {"name": "Erovnuli Liga",                "country": "Georgia",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "GE1N", "url": "/erovnuli-liga/startseite/wettbewerb/GE1N"},
        "meridianbet_1_cfl_mne1"           : {"name": "Meridianbet 1. CFL",           "country": "Montenegro",         "tier": 1 , "is_cup": False, "is_youth": False, "id": "MNE1", "url": "/meridianbet-1-cfl/startseite/wettbewerb/MNE1"},
        "premiership_nir1"                 : {"name": "Premiership",                  "country": "Northern Ireland",   "tier": 1 , "is_cup": False, "is_youth": False, "id": "NIR1", "url": "/premiership/startseite/wettbewerb/NIR1"},
        "super_liga_mo1n"                  : {"name": "Super Liga",                   "country": "Moldova",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "MO1N", "url": "/super-liga/startseite/wettbewerb/MO1N"},
        "bgl_ligue_lux1"                   : {"name": "BGL Ligue",                    "country": "Luxembourg",         "tier": 1 , "is_cup": False, "is_youth": False, "id": "LUX1", "url": "/bgl-ligue/startseite/wettbewerb/LUX1"},
        "super_liga_(phase_2)_mop2"        : {"name": "Super Liga (Phase 2)",         "country": "Moldova",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "MOP2", "url": "/super-liga-phase-2-/startseite/wettbewerb/MOP2"},
        "primera_divisió_and1"             : {"name": "Primera Divisió",              "country": "Andorra",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "AND1", "url": "/primera-divisio/startseite/wettbewerb/AND1"},
        "premium_liiga_est1"               : {"name": "Premium Liiga",                "country": "Estonia",            "tier": 1 , "is_cup": False, "is_youth": False, "id": "EST1", "url": "/premium-liiga/startseite/wettbewerb/EST1"},
        "cymru_premier_wal1"               : {"name": "Cymru Premier",                "country": "Wales",              "tier": 1 , "is_cup": False, "is_youth": False, "id": "WAL1", "url": "/cymru-premier/startseite/wettbewerb/WAL1"},
        "meistaradeildin_faro"             : {"name": "Meistaradeildin",              "country": "Faroe Islands",      "tier": 1 , "is_cup": False, "is_youth": False, "id": "FARO", "url": "/meistaradeildin/startseite/wettbewerb/FARO"},
        "camp_sammarinese_smr1"            : {"name": "Camp. Sammarinese",            "country": "San Marino",         "tier": 1 , "is_cup": False, "is_youth": False, "id": "SMR1", "url": "/campionato-sammarinese/startseite/wettbewerb/SMR1"},
        "gibraltar_football_league_gi1"    : {"name": "Gibraltar Football League",    "country": "Gibraltar",          "tier": 1 , "is_cup": False, "is_youth": False, "id": "GI1",  "url": "/gibraltar-football-league/startseite/wettbewerb/GI1"},
        # ── Europe – Tier 2 ──────────────────────────────────────
        "championship"         : {"name": "Championship",            "country": "England",            "tier": 2 , "is_cup": False, "is_youth": False, "id": "GB2",  "url": "/championship/startseite/wettbewerb/GB2"},
        "serieb"               : {"name": "Serie B",                 "country": "Italy",              "tier": 2 , "is_cup": False, "is_youth": False, "id": "IT2",  "url": "/serie-b/startseite/wettbewerb/IT2"},
        "bundesliga2"          : {"name": "2. Bundesliga",           "country": "Germany",            "tier": 2 , "is_cup": False, "is_youth": False, "id": "L2",   "url": "/2-bundesliga/startseite/wettbewerb/L2"},
        "segunda"              : {"name": "LaLiga 2",                "country": "Spain",              "tier": 2 , "is_cup": False, "is_youth": False, "id": "ES2",  "url": "/laliga2/startseite/wettbewerb/ES2"},
        "ligue2"               : {"name": "Ligue 2",                 "country": "France",             "tier": 2 , "is_cup": False, "is_youth": False, "id": "FR2",  "url": "/ligue-2/startseite/wettbewerb/FR2"},
        "liga_portugal2"       : {"name": "Liga Portugal 2",         "country": "Portugal",           "tier": 2 , "is_cup": False, "is_youth": False, "id": "PO2",  "url": "/liga-portugal-2/startseite/wettbewerb/PO2"},
        "turkish2"             : {"name": "1. Lig",                  "country": "Turkey",             "tier": 2 , "is_cup": False, "is_youth": False, "id": "TR2",  "url": "/1-lig/startseite/wettbewerb/TR2"},
        "dutch2"               : {"name": "Keuken Kampioen Divisie", "country": "Netherlands",        "tier": 2 , "is_cup": False, "is_youth": False, "id": "NL2",  "url": "/keuken-kampioen-divisie/startseite/wettbewerb/NL2"},
        "russian2"             : {"name": "1. Division",             "country": "Russia",             "tier": 2 , "is_cup": False, "is_youth": False, "id": "RU2",  "url": "/1-division/startseite/wettbewerb/RU2"},
        "belgian2"             : {"name": "Challenger Pro League",   "country": "Belgium",            "tier": 2 , "is_cup": False, "is_youth": False, "id": "BE2",  "url": "/challenger-pro-league/startseite/wettbewerb/BE2"},
        "super_league_2_grs2"  : {"name": "Super League 2",          "country": "Greece",             "tier": 2 , "is_cup": False, "is_youth": False, "id": "GRS2", "url": "/super-league-2/startseite/wettbewerb/GRS2"},
        "betclic_1_liga_pl2"   : {"name": "Betclic 1 Liga",          "country": "Poland",             "tier": 2 , "is_cup": False, "is_youth": False, "id": "PL2",  "url": "/betclic-1-liga/startseite/wettbewerb/PL2"},
        "1division_dk2"        : {"name": "1.Division",              "country": "Denmark",            "tier": 2 , "is_cup": False, "is_youth": False, "id": "DK2",  "url": "/1-division/startseite/wettbewerb/DK2"},
        "2_liga_a2"            : {"name": "2. Liga",                 "country": "Austria",            "tier": 2 , "is_cup": False, "is_youth": False, "id": "A2",   "url": "/2-liga/startseite/wettbewerb/A2"},
        "superettan_se2"       : {"name": "Superettan",              "country": "Sweden",             "tier": 2 , "is_cup": False, "is_youth": False, "id": "SE2",  "url": "/superettan/startseite/wettbewerb/SE2"},
        "obos_ligaen_no2"      : {"name": "OBOS-ligaen",             "country": "Norway",             "tier": 2 , "is_cup": False, "is_youth": False, "id": "NO2",  "url": "/obos-ligaen/startseite/wettbewerb/NO2"},
        "chnl_ts2"             : {"name": "ChNL",                    "country": "Czech Republic",     "tier": 2 , "is_cup": False, "is_youth": False, "id": "TS2",  "url": "/chance-narodni-liga/startseite/wettbewerb/TS2"},
        "liga_2_ro2"           : {"name": "Liga 2",                  "country": "Romania",            "tier": 2 , "is_cup": False, "is_youth": False, "id": "RO2",  "url": "/liga-2/startseite/wettbewerb/RO2"},
        "prva_liga_srbije_ser2": {"name": "Prva liga Srbije",        "country": "Serbia",             "tier": 2 , "is_cup": False, "is_youth": False, "id": "SER2", "url": "/prva-liga-srbije/startseite/wettbewerb/SER2"},
        "challenge_league_c2"  : {"name": "Challenge League",        "country": "Switzerland",        "tier": 2 , "is_cup": False, "is_youth": False, "id": "C2",   "url": "/challenge-league/startseite/wettbewerb/C2"},
        "liga_leumit_isr2"     : {"name": "Liga Leumit",             "country": "Israel",             "tier": 2 , "is_cup": False, "is_youth": False, "id": "ISR2", "url": "/liga-leumit/startseite/wettbewerb/ISR2"},
        "persha_liga_ukr2"     : {"name": "Persha Liga",             "country": "Ukraine",            "tier": 2 , "is_cup": False, "is_youth": False, "id": "UKR2", "url": "/persha-liga/startseite/wettbewerb/UKR2"},
        "vtora_liga_bu2"       : {"name": "Vtora Liga",              "country": "Bulgaria",           "tier": 2 , "is_cup": False, "is_youth": False, "id": "BU2",  "url": "/vtora-liga/startseite/wettbewerb/BU2"},
        "nb_ii_un2"            : {"name": "NB II.",                  "country": "Hungary",            "tier": 2 , "is_cup": False, "is_youth": False, "id": "UN2",  "url": "/nemzeti-bajnoksag-ii-/startseite/wettbewerb/UN2"},
        "prva_nl_kr2"          : {"name": "Prva NL",                 "country": "Croatia",            "tier": 2 , "is_cup": False, "is_youth": False, "id": "KR2",  "url": "/prva-nogometna-liga/startseite/wettbewerb/KR2"},
        "championship_sc2"     : {"name": "Championship",            "country": "Scotland",           "tier": 2 , "is_cup": False, "is_youth": False, "id": "SC2",  "url": "/scottish-championship/startseite/wettbewerb/SC2"},
        "druga_liga_sl2"       : {"name": "Druga Liga",              "country": "Slovenia",           "tier": 2 , "is_cup": False, "is_youth": False, "id": "SL2",  "url": "/druga-liga/startseite/wettbewerb/SL2"},
        "kategoria_e_parë_alb2": {"name": "Kategoria e Parë",        "country": "Albania",            "tier": 2 , "is_cup": False, "is_youth": False, "id": "ALB2", "url": "/kategoria-e-pare/startseite/wettbewerb/ALB2"},
        "pershaya_liga_wer2"   : {"name": "Pershaya Liga",           "country": "Belarus",            "tier": 2 , "is_cup": False, "is_youth": False, "id": "WER2", "url": "/pershaya-liga/startseite/wettbewerb/WER2"},
        "prva_liga_fbih_bos2"  : {"name": "Prva liga FBIH",          "country": "Bosnia-Herzegovina", "tier": 2 , "is_cup": False, "is_youth": False, "id": "BOS2", "url": "/prva-liga-fbih/startseite/wettbewerb/BOS2"},
        "monacobet_liga_sk2"   : {"name": "MONACObet liga",          "country": "Slovakia",           "tier": 2 , "is_cup": False, "is_youth": False, "id": "SK2",  "url": "/monacobet-liga/startseite/wettbewerb/SK2"},
        "prva_liga_rs_bh2s"    : {"name": "Prva Liga RS",            "country": "Bosnia-Herzegovina", "tier": 2 , "is_cup": False, "is_youth": False, "id": "BH2S", "url": "/prva-liga-rs/startseite/wettbewerb/BH2S"},
        # ── Europe – Tier 3 ──────────────────────────────────────
        "leagueone"                  : {"name": "League One",              "country": "England",  "tier": 3 , "is_cup": False, "is_youth": False, "id": "GB3",  "url": "/league-one/startseite/wettbewerb/GB3"},
        "bundesliga3"                : {"name": "3. Liga",                 "country": "Germany",  "tier": 3 , "is_cup": False, "is_youth": False, "id": "L3",   "url": "/3-liga/startseite/wettbewerb/L3"},
        "primeraref1"                : {"name": "Primera Federación I",    "country": "Spain",    "tier": 3 , "is_cup": False, "is_youth": False, "id": "E3G1", "url": "/primera-federacion-grupo-i/startseite/wettbewerb/E3G1"},
        "seriec3"                    : {"name": "Serie C Girone C",        "country": "Italy",    "tier": 3 , "is_cup": False, "is_youth": False, "id": "IT3C", "url": "/serie-c-girone-c/startseite/wettbewerb/IT3C"},
        "primeraref2"                : {"name": "Primera Federación II",   "country": "Spain",    "tier": 3 , "is_cup": False, "is_youth": False, "id": "E3G2", "url": "/primera-federacion-grupo-ii/startseite/wettbewerb/E3G2"},
        "seriec1"                    : {"name": "Serie C Girone A",        "country": "Italy",    "tier": 3 , "is_cup": False, "is_youth": False, "id": "IT3A", "url": "/serie-c-girone-a/startseite/wettbewerb/IT3A"},
        "seriec2"                    : {"name": "Serie C Girone B",        "country": "Italy",    "tier": 3 , "is_cup": False, "is_youth": False, "id": "IT3B", "url": "/serie-c-girone-b/startseite/wettbewerb/IT3B"},
        "championnat_national_fr3"   : {"name": "Championnat National",    "country": "France",   "tier": 3 , "is_cup": False, "is_youth": False, "id": "FR3",  "url": "/championnat-national/startseite/wettbewerb/FR3"},
        "2_division_a_(phase_2)_r3d2": {"name": "2. Division A (Phase 2)", "country": "Russia",   "tier": 3 , "is_cup": False, "is_youth": False, "id": "R3D2", "url": "/2-division-a-phase-2-/startseite/wettbewerb/R3D2"},
        "2_division_a_(phase_1)_r3d1": {"name": "2. Division A (Phase 1)", "country": "Russia",   "tier": 3 , "is_cup": False, "is_youth": False, "id": "R3D1", "url": "/2-division-a-phase-1-/startseite/wettbewerb/R3D1"},
        "2lig_kirmizi_tr3b"          : {"name": "2.Lig Kirmizi",           "country": "Türkiye",  "tier": 3 , "is_cup": False, "is_youth": False, "id": "TR3B", "url": "/2-lig-kirmizi/startseite/wettbewerb/TR3B"},
        "2lig_beyaz_tr3a"            : {"name": "2.Lig Beyaz",             "country": "Türkiye",  "tier": 3 , "is_cup": False, "is_youth": False, "id": "TR3A", "url": "/2-lig-beyaz/startseite/wettbewerb/TR3A"},
        "liga_3_pt3a"                : {"name": "Liga 3",                  "country": "Portugal", "tier": 3 , "is_cup": False, "is_youth": False, "id": "PT3A", "url": "/liga-3/startseite/wettbewerb/PT3A"},
        # ── Europe – Tier 4 ──────────────────────────────────────
        "leaguetwo"                       : {"name": "League Two",                   "country": "England", "tier": 4 , "is_cup": False, "is_youth": False, "id": "GB4",  "url": "/league-two/startseite/wettbewerb/GB4"},
        "segunda_federación___gr_iii_e4g3": {"name": "Segunda Federación - Gr. III", "country": "Spain",   "tier": 4 , "is_cup": False, "is_youth": False, "id": "E4G3", "url": "/segunda-federacion-grupo-iii/startseite/wettbewerb/E4G3"},
        "regionalliga_bayern_rlb3"        : {"name": "Regionalliga Bayern",          "country": "Germany", "tier": 4 , "is_cup": False, "is_youth": False, "id": "RLB3", "url": "/regionalliga-bayern/startseite/wettbewerb/RLB3"},
        "regionalliga_west_rlw3"          : {"name": "Regionalliga West",            "country": "Germany", "tier": 4 , "is_cup": False, "is_youth": False, "id": "RLW3", "url": "/regionalliga-west/startseite/wettbewerb/RLW3"},
        "regionalliga_südwest_rlsw"       : {"name": "Regionalliga Südwest",         "country": "Germany", "tier": 4 , "is_cup": False, "is_youth": False, "id": "RLSW", "url": "/regionalliga-sudwest/startseite/wettbewerb/RLSW"},
        "segunda_federación___gr_v_e4g5"  : {"name": "Segunda Federación - Gr. V",   "country": "Spain",   "tier": 4 , "is_cup": False, "is_youth": False, "id": "E4G5", "url": "/segunda-federacion-grupo-v/startseite/wettbewerb/E4G5"},
        "regionalliga_northeast_rln4"     : {"name": "Regionalliga Northeast",       "country": "Germany", "tier": 4 , "is_cup": False, "is_youth": False, "id": "RLN4", "url": "/regionalliga-northeast/startseite/wettbewerb/RLN4"},
        "segunda_federación___gr_iv_e4g4" : {"name": "Segunda Federación - Gr. IV",  "country": "Spain",   "tier": 4 , "is_cup": False, "is_youth": False, "id": "E4G4", "url": "/segunda-federacion-grupo-iv/startseite/wettbewerb/E4G4"},
        "segunda_federación___gr_i_e4g1"  : {"name": "Segunda Federación - Gr. I",   "country": "Spain",   "tier": 4 , "is_cup": False, "is_youth": False, "id": "E4G1", "url": "/segunda-federacion-grupo-i/startseite/wettbewerb/E4G1"},
        "segunda_federación___gr_ii_e4g2" : {"name": "Segunda Federación - Gr. II",  "country": "Spain",   "tier": 4 , "is_cup": False, "is_youth": False, "id": "E4G2", "url": "/segunda-federacion-grupo-ii/startseite/wettbewerb/E4G2"},
        "regionalliga_nord_rln3"          : {"name": "Regionalliga Nord",            "country": "Germany", "tier": 4 , "is_cup": False, "is_youth": False, "id": "RLN3", "url": "/regionalliga-nord/startseite/wettbewerb/RLN3"},
        "serie_d___b_it4b"                : {"name": "Serie D - B",                  "country": "Italy",   "tier": 4 , "is_cup": False, "is_youth": False, "id": "IT4B", "url": "/serie-d-girone-b/startseite/wettbewerb/IT4B"},
        "serie_d___h_it4h"                : {"name": "Serie D - H",                  "country": "Italy",   "tier": 4 , "is_cup": False, "is_youth": False, "id": "IT4H", "url": "/serie-d-girone-h/startseite/wettbewerb/IT4H"},
        "serie_d___f_it4f"                : {"name": "Serie D - F",                  "country": "Italy",   "tier": 4 , "is_cup": False, "is_youth": False, "id": "IT4F", "url": "/serie-d-girone-f/startseite/wettbewerb/IT4F"},
        "serie_d___e_it4e"                : {"name": "Serie D - E",                  "country": "Italy",   "tier": 4 , "is_cup": False, "is_youth": False, "id": "IT4E", "url": "/serie-d-girone-e/startseite/wettbewerb/IT4E"},
        "serie_d___d_it4d"                : {"name": "Serie D - D",                  "country": "Italy",   "tier": 4 , "is_cup": False, "is_youth": False, "id": "IT4D", "url": "/serie-d-girone-d/startseite/wettbewerb/IT4D"},
        "serie_d___c_it4c"                : {"name": "Serie D - C",                  "country": "Italy",   "tier": 4 , "is_cup": False, "is_youth": False, "id": "IT4C", "url": "/serie-d-girone-c/startseite/wettbewerb/IT4C"},
        "serie_d___a_it4a"                : {"name": "Serie D - A",                  "country": "Italy",   "tier": 4 , "is_cup": False, "is_youth": False, "id": "IT4A", "url": "/serie-d-girone-a/startseite/wettbewerb/IT4A"},
        "serie_d___g_it4g"                : {"name": "Serie D - G",                  "country": "Italy",   "tier": 4 , "is_cup": False, "is_youth": False, "id": "IT4G", "url": "/serie-d-girone-g/startseite/wettbewerb/IT4G"},
        "serie_d___i_it4i"                : {"name": "Serie D - I",                  "country": "Italy",   "tier": 4 , "is_cup": False, "is_youth": False, "id": "IT4I", "url": "/serie-d-girone-i/startseite/wettbewerb/IT4I"},
        # ── Americas – Tier 1 ──────────────────────────────────────
        "brazilian"                             : {"name": "Brasileirão",                       "country": "Brazil",      "tier": 1 , "is_cup": False, "is_youth": False, "id": "BRA1", "url": "/campeonato-brasileiro-serie-a/startseite/wettbewerb/BRA1"},
        "mls"                                   : {"name": "MLS",                               "country": "USA",         "tier": 1 , "is_cup": False, "is_youth": False, "id": "MLS1", "url": "/major-league-soccer/startseite/wettbewerb/MLS1"},
        "argentine"                             : {"name": "Liga Profesional",                  "country": "Argentina",   "tier": 1 , "is_cup": False, "is_youth": False, "id": "ARG1", "url": "/torneo-apertura/startseite/wettbewerb/ARG1"},
        "mexican"                               : {"name": "Liga MX",                           "country": "Mexico",      "tier": 1 , "is_cup": False, "is_youth": False, "id": "MEX1", "url": "/liga-mx-clausura/startseite/wettbewerb/MEX1"},
        "colombian"                             : {"name": "Liga DIMAYOR",                      "country": "Colombia",    "tier": 1 , "is_cup": False, "is_youth": False, "id": "COLP", "url": "/liga-dimayor-apertura/startseite/wettbewerb/COLP"},
        "uruguayan"                             : {"name": "Liga AUF",                          "country": "Uruguay",     "tier": 1 , "is_cup": False, "is_youth": False, "id": "URU1", "url": "/liga-auf-apertura/startseite/wettbewerb/URU1"},
        "ecuadorian"                            : {"name": "LigaPro Serie A",                   "country": "Ecuador",     "tier": 1 , "is_cup": False, "is_youth": False, "id": "EC1N", "url": "/ligapro-serie-a/startseite/wettbewerb/EC1N"},
        "chilean"                               : {"name": "Liga Primera",                      "country": "Chile",       "tier": 1 , "is_cup": False, "is_youth": False, "id": "CLPD", "url": "/liga-de-primera/startseite/wettbewerb/CLPD"},
        "peruvian"                              : {"name": "Liga 1",                            "country": "Peru",        "tier": 1 , "is_cup": False, "is_youth": False, "id": "TDeA", "url": "/liga-1-apertura/startseite/wettbewerb/TDeA"},
        "paraguayan"                            : {"name": "Primera División",                  "country": "Paraguay",    "tier": 1 , "is_cup": False, "is_youth": False, "id": "PR1A", "url": "/primera-division-apertura/startseite/wettbewerb/PR1A"},
        "división_profesional_bo1a"             : {"name": "División Profesional",              "country": "Bolivia",     "tier": 1 , "is_cup": False, "is_youth": False, "id": "BO1A", "url": "/division-profesional/startseite/wettbewerb/BO1A"},
        "liga_futve_apertura_vz1a"              : {"name": "Liga FUTVE Apertura",               "country": "Venezuela",   "tier": 1 , "is_cup": False, "is_youth": False, "id": "VZ1A", "url": "/liga-futve-apertura/startseite/wettbewerb/VZ1A"},
        "primera_división_apertura_crpd"        : {"name": "Primera División Apertura",         "country": "Costa Rica",  "tier": 1 , "is_cup": False, "is_youth": False, "id": "CRPD", "url": "/primera-division-apertura/startseite/wettbewerb/CRPD"},
        "primera_división_clausura_pdv1"        : {"name": "Primera División Clausura",         "country": "Costa Rica",  "tier": 1 , "is_cup": False, "is_youth": False, "id": "PDV1", "url": "/primera-division-clausura/startseite/wettbewerb/PDV1"},
        "national_league_apertura_gu1a"         : {"name": "National League Apertura",          "country": "Guatemala",   "tier": 1 , "is_cup": False, "is_youth": False, "id": "GU1A", "url": "/national-league-apertura/startseite/wettbewerb/GU1A"},
        "national_league_clausura_gu1c"         : {"name": "National League Clausura",          "country": "Guatemala",   "tier": 1 , "is_cup": False, "is_youth": False, "id": "GU1C", "url": "/national-league-clausura/startseite/wettbewerb/GU1C"},
        "primera_división_apertura_sl1a"        : {"name": "Primera División Apertura",         "country": "El Salvador", "tier": 1 , "is_cup": False, "is_youth": False, "id": "SL1A", "url": "/primera-division-apertura/startseite/wettbewerb/SL1A"},
        "primera_división_clausura_sl1c"        : {"name": "Primera División Clausura",         "country": "El Salvador", "tier": 1 , "is_cup": False, "is_youth": False, "id": "SL1C", "url": "/primera-division-clausura/startseite/wettbewerb/SL1C"},
        "liga_nacional_apertura_ho1a"           : {"name": "Liga Nacional Apertura",            "country": "Honduras",    "tier": 1 , "is_cup": False, "is_youth": False, "id": "HO1A", "url": "/liga-nacional-apertura/startseite/wettbewerb/HO1A"},
        "liga_nacional_clausura_hoc1"           : {"name": "Liga Nacional Clausura",            "country": "Honduras",    "tier": 1 , "is_cup": False, "is_youth": False, "id": "HOC1", "url": "/liga-nacional-clausura/startseite/wettbewerb/HOC1"},
        "liga_panameña_clausura_pn1c"           : {"name": "Liga Panameña Clausura",            "country": "Panama",      "tier": 1 , "is_cup": False, "is_youth": False, "id": "PN1C", "url": "/liga-panamena-de-futbol-clausura/startseite/wettbewerb/PN1C"},
        "canpl_cdn1"                            : {"name": "CanPL",                             "country": "Canada",      "tier": 1 , "is_cup": False, "is_youth": False, "id": "CDN1", "url": "/canadian-premier-league/startseite/wettbewerb/CDN1"},
        # ── Americas – Tier 2 ──────────────────────────────────────
        "brazilian2"                         : {"name": "Série B",                        "country": "Brazil",        "tier": 2 , "is_cup": False, "is_youth": False, "id": "BRA2", "url": "/campeonato-brasileiro-serie-b/startseite/wettbewerb/BRA2"},
        "argentine2"                         : {"name": "Primera Nacional",               "country": "Argentina",     "tier": 2 , "is_cup": False, "is_youth": False, "id": "ARG2", "url": "/primera-nacional/startseite/wettbewerb/ARG2"},
        "liga_expansión_mx_cl_mex2"          : {"name": "Liga Expansión MX Cl.",          "country": "Mexico",        "tier": 2 , "is_cup": False, "is_youth": False, "id": "MEX2", "url": "/liga-de-expansion-mx-clausura/startseite/wettbewerb/MEX2"},
        "liga_expansión_mx_ap_mexb"          : {"name": "Liga Expansión MX Ap.",          "country": "Mexico",        "tier": 2 , "is_cup": False, "is_youth": False, "id": "MEXB", "url": "/liga-de-expansion-mx-apertura/startseite/wettbewerb/MEXB"},
        "uslc_usl"                           : {"name": "USLC",                           "country": "United States", "tier": 2 , "is_cup": False, "is_youth": False, "id": "USL",  "url": "/usl-championship/startseite/wettbewerb/USL"},
        "liga_de_ascenso_cl2b"               : {"name": "Liga de Ascenso",                "country": "Chile",         "tier": 2 , "is_cup": False, "is_youth": False, "id": "CL2B", "url": "/liga-de-ascenso/startseite/wettbewerb/CL2B"},
        # "liguilla_de_expansión_apertura_mxba": {"name": "Liguilla de Expansión Apertura", "country": "Mexico",        "tier": 2 , "is_cup": False, "is_youth": False, "id": "MXBA", "url": "/liguilla-de-expansion-apertura/startseite/wettbewerb/MXBA"},
        "torneo_dimayor_i_co2t"              : {"name": "Torneo DIMAYOR I",               "country": "Colombia",      "tier": 2 , "is_cup": False, "is_youth": False, "id": "CO2T", "url": "/torneo-dimayor-i/startseite/wettbewerb/CO2T"},
        "liga_2_per2"                        : {"name": "Liga 2",                         "country": "Peru",          "tier": 2 , "is_cup": False, "is_youth": False, "id": "PER2", "url": "/liga-2/startseite/wettbewerb/PER2"},
        "segunda_división_uru2"              : {"name": "Segunda División",               "country": "Uruguay",       "tier": 2 , "is_cup": False, "is_youth": False, "id": "URU2", "url": "/segunda-division-fase-regular/startseite/wettbewerb/URU2"},
        "liga_pro_serie_b_ec2l"              : {"name": "Liga Pro Serie B",               "country": "Ecuador",       "tier": 2 , "is_cup": False, "is_youth": False, "id": "EC2L", "url": "/liga-pro-serie-b/startseite/wettbewerb/EC2L"},
        "liga_futve_2_vn2a"                  : {"name": "Liga FUTVE 2",                   "country": "Venezuela",     "tier": 2 , "is_cup": False, "is_youth": False, "id": "VN2A", "url": "/liga-futve-2/startseite/wettbewerb/VN2A"},
        # ── Americas – Tier 3 ──────────────────────────────────────
        "usl1_usc3"        : {"name": "USL1",         "country": "United States", "tier": 3 , "is_cup": False, "is_youth": False, "id": "USC3", "url": "/usl-league-one/startseite/wettbewerb/USC3"},
        "mls_next_pro_mnp3": {"name": "MLS Next Pro", "country": "United States", "tier": 3 , "is_cup": False, "is_youth": False, "id": "MNP3", "url": "/mls-next-pro/startseite/wettbewerb/MNP3"},
        # ── Asia – Tier 1 ──────────────────────────────────────
        "saudi"                        : {"name": "Saudi Pro League",         "country": "Saudi Arabia", "tier": 1 , "is_cup": False, "is_youth": False, "id": "SA1",  "url": "/saudi-pro-league/startseite/wettbewerb/SA1"},
        "emirati"                      : {"name": "UAE Pro League",           "country": "UAE",          "tier": 1 , "is_cup": False, "is_youth": False, "id": "UAE1", "url": "/uae-pro-league/startseite/wettbewerb/UAE1"},
        "qatari"                       : {"name": "Stars League",             "country": "Qatar",        "tier": 1 , "is_cup": False, "is_youth": False, "id": "QSL",  "url": "/qatar-stars-league/startseite/wettbewerb/QSL"},
        "japanese"                     : {"name": "J1 League",                "country": "Japan",        "tier": 1 , "is_cup": False, "is_youth": False, "id": "JAP1", "url": "/j1-league/startseite/wettbewerb/JAP1"},
        "chinese"                      : {"name": "Chinese Super League",     "country": "China",        "tier": 1 , "is_cup": False, "is_youth": False, "id": "CSL",  "url": "/chinese-super-league/startseite/wettbewerb/CSL"},
        "iranian"                      : {"name": "Persian Gulf Pro League",  "country": "Iran",         "tier": 1 , "is_cup": False, "is_youth": False, "id": "IRN1", "url": "/persian-gulf-pro-league/startseite/wettbewerb/IRN1"},
        "korean"                       : {"name": "K League 1",               "country": "South Korea",  "tier": 1 , "is_cup": False, "is_youth": False, "id": "RSK1", "url": "/k-league-1/startseite/wettbewerb/RSK1"},
        "australian"                   : {"name": "A-League Men",             "country": "Australia",    "tier": 1 , "is_cup": False, "is_youth": False, "id": "AUS1", "url": "/a-league-men/startseite/wettbewerb/AUS1"},
        "superliga_uz1"                : {"name": "Superliga",                "country": "Uzbekistan",   "tier": 1 , "is_cup": False, "is_youth": False, "id": "UZ1",  "url": "/ozbekiston-superligasi/startseite/wettbewerb/UZ1"},
        "iraq_stars_league_irq1"       : {"name": "Iraq Stars League",        "country": "Iraq",         "tier": 1 , "is_cup": False, "is_youth": False, "id": "IRQ1", "url": "/iraq-stars-league/startseite/wettbewerb/IRQ1"},
        "super_league_in1l"            : {"name": "Super League",             "country": "Indonesia",    "tier": 1 , "is_cup": False, "is_youth": False, "id": "IN1L", "url": "/super-league/startseite/wettbewerb/IN1L"},
        "thai_league_tha1"             : {"name": "Thai League",              "country": "Thailand",     "tier": 1 , "is_cup": False, "is_youth": False, "id": "THA1", "url": "/thai-league/startseite/wettbewerb/THA1"},
        "super_league_mys1"            : {"name": "Super League",             "country": "Malaysia",     "tier": 1 , "is_cup": False, "is_youth": False, "id": "MYS1", "url": "/malaysia-super-league/startseite/wettbewerb/MYS1"},
        "vleague_1_vie1"               : {"name": "V.League 1",               "country": "Vietnam",      "tier": 1 , "is_cup": False, "is_youth": False, "id": "VIE1", "url": "/v-league-1/startseite/wettbewerb/VIE1"},
        "jindal_league_om1l"           : {"name": "Jindal League",            "country": "Oman",         "tier": 1 , "is_cup": False, "is_youth": False, "id": "OM1L", "url": "/oman-jindal-league/startseite/wettbewerb/OM1L"},
        "jogorku_liga_kg1l"            : {"name": "Jogorku Liga",             "country": "Kyrgyzstan",   "tier": 1 , "is_cup": False, "is_youth": False, "id": "KG1L", "url": "/jogorku-liga/startseite/wettbewerb/KG1L"},
        "indian_super_league_ind1"     : {"name": "Indian Super League",      "country": "India",        "tier": 1 , "is_cup": False, "is_youth": False, "id": "IND1", "url": "/indian-super-league/startseite/wettbewerb/IND1"},
        "lebanese_premier_league_lib1" : {"name": "Lebanese Premier League",  "country": "Lebanon",      "tier": 1 , "is_cup": False, "is_youth": False, "id": "LIB1", "url": "/lebanese-premier-league/startseite/wettbewerb/LIB1"},
        "jordanian_pro_league_jo1l"    : {"name": "Jordanian Pro League",     "country": "Jordan",       "tier": 1 , "is_cup": False, "is_youth": False, "id": "JO1L", "url": "/jordanian-pro-league/startseite/wettbewerb/JO1L"},
        "hong_kong_premier_league_hgkg": {"name": "Hong Kong Premier League", "country": "Hongkong",     "tier": 1 , "is_cup": False, "is_youth": False, "id": "HGKG", "url": "/hong-kong-premier-league/startseite/wettbewerb/HGKG"},
        "vysshaya_liga_tad1"           : {"name": "Vysshaya Liga",            "country": "Tajikistan",   "tier": 1 , "is_cup": False, "is_youth": False, "id": "TAD1", "url": "/vysshaya-liga/startseite/wettbewerb/TAD1"},
        "premier_league_sin1"          : {"name": "Premier League",           "country": "Singapore",    "tier": 1 , "is_cup": False, "is_youth": False, "id": "SIN1", "url": "/singapore-premier-league/startseite/wettbewerb/SIN1"},
        "c_premier_league_khm1"        : {"name": "C. Premier League",        "country": "Cambodia",     "tier": 1 , "is_cup": False, "is_youth": False, "id": "KHM1", "url": "/cambodian-premier-league/startseite/wettbewerb/KHM1"},
        "myanmar_national_league_mya1" : {"name": "Myanmar National League",  "country": "Myanmar",      "tier": 1 , "is_cup": False, "is_youth": False, "id": "MYA1", "url": "/myanmar-national-league/startseite/wettbewerb/MYA1"},
        "bfl_bgd1"                     : {"name": "BFL",                      "country": "Bangladesh",   "tier": 1 , "is_cup": False, "is_youth": False, "id": "BGD1", "url": "/bangladesh-football-league/startseite/wettbewerb/BGD1"},
        "national_league___north_nnl1" : {"name": "National League - North",  "country": "New Zealand",  "tier": 1 , "is_cup": False, "is_youth": False, "id": "NNL1", "url": "/national-league-north/startseite/wettbewerb/NNL1"},
        "fiji_premier_league_fij1"     : {"name": "Fiji Premier League",      "country": "Fiji",         "tier": 1 , "is_cup": False, "is_youth": False, "id": "FIJ1", "url": "/fiji-premier-league/startseite/wettbewerb/FIJ1"},
        "pfl_pfl1"                     : {"name": "PFL",                      "country": "Philippines",  "tier": 1 , "is_cup": False, "is_youth": False, "id": "PFL1", "url": "/philippines-football-league/startseite/wettbewerb/PFL1"},
        # ── Asia – Tier 2 ──────────────────────────────────────
        "japanese2"                       : {"name": "J2 League",                   "country": "Japan",        "tier": 2 , "is_cup": False, "is_youth": False, "id": "JAP2", "url": "/j2-league/startseite/wettbewerb/JAP2"},
        "k_league_2_rsk2"                 : {"name": "K League 2",                  "country": "Korea, South", "tier": 2 , "is_cup": False, "is_youth": False, "id": "RSK2", "url": "/k-league-2/startseite/wettbewerb/RSK2"},
        "saudi_first_division_league_sa2l": {"name": "Saudi First Division League", "country": "Saudi Arabia", "tier": 2 , "is_cup": False, "is_youth": False, "id": "SA2L", "url": "/saudi-first-division-league/startseite/wettbewerb/SA2L"},
        "league_one_clo"                  : {"name": "League One",                  "country": "China",        "tier": 2 , "is_cup": False, "is_youth": False, "id": "CLO",  "url": "/china-league-one/startseite/wettbewerb/CLO"},
        "azadegan_league_irn2"            : {"name": "Azadegan League",             "country": "Iran",         "tier": 2 , "is_cup": False, "is_youth": False, "id": "IRN2", "url": "/azadegan-league/startseite/wettbewerb/IRN2"},
        "championship_ili2"               : {"name": "Championship",                "country": "Indonesia",    "tier": 2 , "is_cup": False, "is_youth": False, "id": "ILI2", "url": "/championship/startseite/wettbewerb/ILI2"},
        "qatari_second_division_qu2l"     : {"name": "Qatari Second Division",      "country": "Qatar",        "tier": 2 , "is_cup": False, "is_youth": False, "id": "QU2L", "url": "/qatari-second-division/startseite/wettbewerb/QU2L"},
        "thai_league_2_tha2"              : {"name": "Thai League 2",               "country": "Thailand",     "tier": 2 , "is_cup": False, "is_youth": False, "id": "THA2", "url": "/thai-league-2/startseite/wettbewerb/THA2"},
        "o'zbekiston_pro_liga_uz2l"       : {"name": "O'zbekiston Pro Liga",        "country": "Uzbekistan",   "tier": 2 , "is_cup": False, "is_youth": False, "id": "UZ2L", "url": "/ozbekiston-pro-liga/startseite/wettbewerb/UZ2L"},
        # ── Africa – Tier 1 ──────────────────────────────────────
        "egyptian"                  : {"name": "Egyptian Premier League", "country": "Egypt",        "tier": 1 , "is_cup": False, "is_youth": False, "id": "EGY1", "url": "/egyptian-premier-league/startseite/wettbewerb/EGY1"},
        "south_african"             : {"name": "Betway Premiership",      "country": "South Africa", "tier": 1 , "is_cup": False, "is_youth": False, "id": "SFA1", "url": "/betway-premiership/startseite/wettbewerb/SFA1"},
        "moroccan"                  : {"name": "Botola Pro Inwi",         "country": "Morocco",      "tier": 1 , "is_cup": False, "is_youth": False, "id": "MAR1", "url": "/botola-pro-inwi/startseite/wettbewerb/MAR1"},
        "ligue_1_alg1"              : {"name": "Ligue 1",                 "country": "Algeria",      "tier": 1 , "is_cup": False, "is_youth": False, "id": "ALG1", "url": "/ligue-1/startseite/wettbewerb/ALG1"},
        "ligue_1_tun1"              : {"name": "Ligue 1",                 "country": "Tunisia",      "tier": 1 , "is_cup": False, "is_youth": False, "id": "TUN1", "url": "/ligue-1/startseite/wettbewerb/TUN1"},
        "libyan_premier_league_lpl" : {"name": "Libyan Premier League",   "country": "Libya",        "tier": 1 , "is_cup": False, "is_youth": False, "id": "LPL",  "url": "/libyan-premier-league/startseite/wettbewerb/LPL"},
        "uganda_premier_league_ugl1": {"name": "Uganda Premier League",   "country": "Uganda",       "tier": 1 , "is_cup": False, "is_youth": False, "id": "UGL1", "url": "/uganda-premier-league/startseite/wettbewerb/UGL1"},
        "premier_league_etp1"       : {"name": "Premier League",          "country": "Ethiopia",     "tier": 1 , "is_cup": False, "is_youth": False, "id": "ETP1", "url": "/ethiopian-premier-league/startseite/wettbewerb/ETP1"},
        "premier_league_ghpl"       : {"name": "Premier League",          "country": "Ghana",        "tier": 1 , "is_cup": False, "is_youth": False, "id": "GHPL", "url": "/ghana-premier-league/startseite/wettbewerb/GHPL"},
        "ligue_1_sen1"              : {"name": "Ligue 1",                 "country": "Senegal",      "tier": 1 , "is_cup": False, "is_youth": False, "id": "SEN1", "url": "/ligue-1/startseite/wettbewerb/SEN1"},
        # ── Asia – Tier 3 ──────────────────────────────────────
        "j3_league_jap3": {"name": "J3 League", "country": "Japan", "tier": 3 , "is_cup": False, "is_youth": False, "id": "JAP3", "url": "/j3-league/startseite/wettbewerb/JAP3"},
        # # ── European Cups ────────────────────────────────────────
        # "champions"    : {"name": "UEFA Champions League",  "country": "Europe", "tier": 1 , "is_cup": True , "is_youth": False, "id": "CL",   "url": "/uefa-champions-league/startseite/pokalwettbewerb/CL"},
        # "europa_league": {"name": "UEFA Europa League",     "country": "Europe", "tier": 1 , "is_cup": True , "is_youth": False, "id": "EL",   "url": "/europa-league/startseite/pokalwettbewerb/EL"},
        # "conference"   : {"name": "UEFA Conference League", "country": "Europe", "tier": 1 , "is_cup": True , "is_youth": False, "id": "UCOL", "url": "/europa-conference-league/startseite/pokalwettbewerb/UCOL"},
        # # ── Americas Cups ────────────────────────────────────────
        # "copa_do_brasil_brc"                    : {"name": "Copa do Brasil",                    "country": "Brazil",        "tier": 1 , "is_cup": True , "is_youth": False, "id": "BRC",  "url": "/copa-do-brasil/startseite/wettbewerb/BRC"},
        # "copa_argentina_arca"                   : {"name": "Copa Argentina",                    "country": "Argentina",     "tier": 1 , "is_cup": True , "is_youth": False, "id": "ARCA", "url": "/copa-argentina/startseite/wettbewerb/ARCA"},
        # "supercopa_rei_scbr"                    : {"name": "Supercopa Rei",                     "country": "Brazil",        "tier": 1 , "is_cup": True , "is_youth": False, "id": "SCBR", "url": "/supercopa-rei/startseite/wettbewerb/SCBR"},
        # "copa_chile_ch1c"                       : {"name": "Copa Chile",                        "country": "Chile",         "tier": 1 , "is_cup": True , "is_youth": False, "id": "CH1C", "url": "/copa-chile/startseite/wettbewerb/CH1C"},
        # "copa_de_la_liga_cllc"                  : {"name": "Copa de la Liga",                   "country": "Chile",         "tier": 1 , "is_cup": True , "is_youth": False, "id": "CLLC", "url": "/copa-de-la-liga-de-chile/startseite/wettbewerb/CLLC"},
        # "copa_do_nordeste_brne"                 : {"name": "Copa do Nordeste",                  "country": "Brazil",        "tier": 1 , "is_cup": True , "is_youth": False, "id": "BRNE", "url": "/copa-do-nordeste/startseite/wettbewerb/BRNE"},
        # "usl_cup_uslc"                          : {"name": "USL Cup",                           "country": "United States", "tier": 1 , "is_cup": True , "is_youth": False, "id": "USLC", "url": "/usl-cup/startseite/wettbewerb/USLC"},
        # "supercopa_internacional_scin"          : {"name": "Supercopa Internacional",           "country": "Argentina",     "tier": 1 , "is_cup": True , "is_youth": False, "id": "SCIN", "url": "/supercopa-internacional/startseite/wettbewerb/SCIN"},
        # "copa_verde_brve"                       : {"name": "Copa Verde",                        "country": "Brazil",        "tier": 1 , "is_cup": True , "is_youth": False, "id": "BRVE", "url": "/copa-verde/startseite/wettbewerb/BRVE"},
        # "supercopa_ursc"                        : {"name": "Supercopa",                         "country": "Uruguay",       "tier": 1 , "is_cup": True , "is_youth": False, "id": "URSC", "url": "/supercopa-uruguaya/startseite/wettbewerb/URSC"},
        # "copa_de_costa_rica_crpo"               : {"name": "Copa de Costa Rica",                "country": "Costa Rica",    "tier": 1 , "is_cup": True , "is_youth": False, "id": "CRPO", "url": "/copa-de-costa-rica/startseite/wettbewerb/CRPO"},
        # "supercopa_de_chile_csuc"               : {"name": "Supercopa de Chile",                "country": "Chile",         "tier": 1 , "is_cup": True , "is_youth": False, "id": "CSUC", "url": "/supercopa-de-chile/startseite/wettbewerb/CSUC"},
        # "copa_el_salvador_elc1"                 : {"name": "Copa El Salvador",                  "country": "El Salvador",   "tier": 1 , "is_cup": True , "is_youth": False, "id": "ELC1", "url": "/copa-el-salvador/startseite/wettbewerb/ELC1"},
        # "superliga_águila_de_campeones_cosp"    : {"name": "Superliga Águila de Campeones",     "country": "Colombia",      "tier": 1 , "is_cup": True , "is_youth": False, "id": "COSP", "url": "/superliga-aguila-de-campeones/startseite/wettbewerb/COSP"},
        # "copa_ecuador_ecup"                     : {"name": "Copa Ecuador",                      "country": "Ecuador",       "tier": 1 , "is_cup": True , "is_youth": False, "id": "ECUP", "url": "/copa-ecuador/startseite/wettbewerb/ECUP"},
        # "taça_acesc_70_anos_brp6"               : {"name": "Taça Acesc 70 anos",                "country": "Brazil",        "tier": 1 , "is_cup": True , "is_youth": False, "id": "BRP6", "url": "/taca-acesc-70-anos/startseite/wettbewerb/BRP6"},
        # "recopa_costa_rica_csc2"                : {"name": "Recopa Costa Rica",                 "country": "Costa Rica",    "tier": 1 , "is_cup": True , "is_youth": False, "id": "CSC2", "url": "/recopa-costa-rica/startseite/wettbewerb/CSC2"},
        # "campeonato_paulista_bcp1"              : {"name": "Campeonato Paulista",               "country": "Brazil",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "BCP1", "url": "/campeonato-paulista/startseite/wettbewerb/BCP1"},
        # "campeonato_carioca_brcg"               : {"name": "Campeonato Carioca",                "country": "Brazil",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "BRCG", "url": "/campeonato-carioca/startseite/wettbewerb/BRCG"},
        # "campeonato_mineiro_brcm"               : {"name": "Campeonato Mineiro",                "country": "Brazil",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "BRCM", "url": "/campeonato-mineiro/startseite/wettbewerb/BRCM"},
        # "campeonato_gaúcho_brrs"                : {"name": "Campeonato Gaúcho",                 "country": "Brazil",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "BRRS", "url": "/campeonato-gaucho/startseite/wettbewerb/BRRS"},
        # "campeonato_baiano_brcb"                : {"name": "Campeonato Baiano",                 "country": "Brazil",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "BRCB", "url": "/campeonato-baiano/startseite/wettbewerb/BRCB"},
        # "carioca___taça_rio_brcr"               : {"name": "Carioca - Taça Rio",                "country": "Brazil",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "BRCR", "url": "/campeonato-carioca-taca-rio/startseite/wettbewerb/BRCR"},
        # "campeonato_paranaense_brpr"            : {"name": "Campeonato Paranaense",             "country": "Brazil",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "BRPR", "url": "/campeonato-paranaense/startseite/wettbewerb/BRPR"},
        # "campeonato_cearense_brce"              : {"name": "Campeonato Cearense",               "country": "Brazil",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "BRCE", "url": "/campeonato-cearense/startseite/wettbewerb/BRCE"},
        # "campeonato_catarinense_brsc"           : {"name": "Campeonato Catarinense",            "country": "Brazil",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "BRSC", "url": "/campeonato-catarinense/startseite/wettbewerb/BRSC"},
        # "campeonato_goiano_brgo"                : {"name": "Campeonato Goiano",                 "country": "Brazil",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "BRGO", "url": "/campeonato-goiano/startseite/wettbewerb/BRGO"},
        # "campeonato_paraense_brpa"              : {"name": "Campeonato Paraense",               "country": "Brazil",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "BRPA", "url": "/campeonato-paraense/startseite/wettbewerb/BRPA"},
        # "campeonato_pernambucano_brpe"          : {"name": "Campeonato Pernambucano",           "country": "Brazil",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "BRPE", "url": "/campeonato-pernambucano/startseite/wettbewerb/BRPE"},
        # "campeonato_alagoano_bral"              : {"name": "Campeonato Alagoano",               "country": "Brazil",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "BRAL", "url": "/campeonato-alagoano/startseite/wettbewerb/BRAL"},
        # "campeonato_mato_grossense_brms"        : {"name": "Campeonato Mato-Grossense",         "country": "Brazil",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "BRMS", "url": "/campeonato-mato-grossense/startseite/wettbewerb/BRMS"},
        # "national_league_apertura_play_off_gupa": {"name": "National League Apertura Play-Off", "country": "Guatemala",     "tier": 1 , "is_cup": True, "is_youth": False, "id": "GUPA", "url": "/national-league-apertura-play-off/startseite/wettbewerb/GUPA"},
        # "lnphn_apertura_playoff_hoap"           : {"name": "LNPHN Apertura Playoff",            "country": "Honduras",      "tier": 1 , "is_cup": True, "is_youth": False, "id": "HOAP", "url": "/liga-nacional-apertura-playoff/startseite/wettbewerb/HOAP"},
        # "apertura_final_stages_slp1"            : {"name": "Apertura Final stages",             "country": "El Salvador",   "tier": 1 , "is_cup": True, "is_youth": False, "id": "SLP1", "url": "/primera-division-apertura-final-stages/startseite/wettbewerb/SLP1"},
        # "torneo_competencia_ur2t"               : {"name": "Torneo Competencia",                "country": "Uruguay",       "tier": 2 , "is_cup": True, "is_youth": False, "id": "UR2T", "url": "/segunda-division-torneo-competencia/startseite/wettbewerb/UR2T"},
        # # ── Africa Cups ────────────────────────────────────────
        # "egypt_cup_egyp"           : {"name": "Egypt Cup",              "country": "Egypt",        "tier": 1 , "is_cup": True , "is_youth": False, "id": "EGYP", "url": "/egypt-cup/startseite/wettbewerb/EGYP"},
        # "egyptian_league_cup_eglc" : {"name": "Egyptian League Cup",    "country": "Egypt",        "tier": 1 , "is_cup": True , "is_youth": False, "id": "EGLC", "url": "/egyptian-league-cup/startseite/wettbewerb/EGLC"},
        # "nedbank_cup_nedc"         : {"name": "Nedbank Cup",            "country": "South Africa", "tier": 1 , "is_cup": True , "is_youth": False, "id": "NEDC", "url": "/nedbank-cup/startseite/wettbewerb/NEDC"},
        # "carling_knockout_telk"    : {"name": "Carling Knockout",       "country": "South Africa", "tier": 1 , "is_cup": True , "is_youth": False, "id": "TELK", "url": "/carling-knockout/startseite/wettbewerb/TELK"},
        # "mtn8_sfal"                : {"name": "MTN8",                   "country": "South Africa", "tier": 1 , "is_cup": True , "is_youth": False, "id": "SFAL", "url": "/mtn8/startseite/wettbewerb/SFAL"},
        # "coupe_d'algerie_algp"     : {"name": "Coupe d'Algerie",        "country": "Algeria",      "tier": 1 , "is_cup": True , "is_youth": False, "id": "ALGP", "url": "/coupe-dalgerie/startseite/wettbewerb/ALGP"},
        # "tunisian_cup_tunp"        : {"name": "Tunisian Cup",           "country": "Tunisia",      "tier": 1 , "is_cup": True , "is_youth": False, "id": "TUNP", "url": "/tunisian-cup/startseite/wettbewerb/TUNP"},
        # "egyptian_super_cup_escu"  : {"name": "Egyptian Super Cup",     "country": "Egypt",        "tier": 1 , "is_cup": True , "is_youth": False, "id": "ESCU", "url": "/egyptian-super-cup/startseite/wettbewerb/ESCU"},
        # "supercoupe_d'algérie_agsc": {"name": "Supercoupe d'Algérie",   "country": "Algeria",      "tier": 1 , "is_cup": True , "is_youth": False, "id": "AGSC", "url": "/supercoupe-dalgerie/startseite/wettbewerb/AGSC"},
        # "championship_playoff_egcp" : {"name": "Championship Playoff",  "country": "Egypt",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "EGCP", "url": "/championship-playoff/startseite/wettbewerb/EGCP"},
        # "relegation_playoff_egrp"   : {"name": "Relegation Playoff",    "country": "Egypt",        "tier": 1 , "is_cup": True, "is_youth": False, "id": "EGRP", "url": "/relegation-playoff/startseite/wettbewerb/EGRP"},
        # ── Youth ────────────────────────────────────────────────
        "primavera1"             : {"name": "Primavera 1",             "country": "Italy",    "tier": 1 , "is_cup": False, "is_youth": True , "id": "IJ1",  "url": "/primavera-1/startseite/wettbewerb/IJ1"},
        # "copinha_spjr"           : {"name": "Copinha",                 "country": "Brazil",   "tier": 1 , "is_cup": True , "is_youth": True , "id": "SPjr", "url": "/copa-sao-paulo-de-futebol-junior/startseite/wettbewerb/SPjr"},
        "cbf_brasileiro_u20_cb20": {"name": "CBF Brasileiro U20",      "country": "Brazil",   "tier": 1 , "is_cup": False, "is_youth": True , "id": "CB20", "url": "/cbf-brasileiro-u20/startseite/wettbewerb/CB20"},
        "u19_bundesliga_a"       : {"name": "U19 DFB-Nachwuchsliga A", "country": "Germany",  "tier": 1 , "is_cup": False, "is_youth": True , "id": "19LA", "url": "/u19-dfb-nachwuchsliga-hauptrunde-liga-a/startseite/wettbewerb/19LA"},
        # "u19_bundesliga_h"       : {"name": "U19 DFB-Nachwuchsliga H", "country": "Germany",  "tier": 1 , "is_cup": False, "is_youth": True , "id": "19D8", "url": "/u19-dfb-nachwuchsliga-vorrunde-gruppe-h/startseite/wettbewerb/19D8"},
        "liga_revelacao"         : {"name": "Liga Revelação U23",      "country": "Portugal", "tier": 1 , "is_cup": False, "is_youth": True , "id": "PT23", "url": "/liga-revelacao-u23/startseite/wettbewerb/PT23"},
    }
    
    
    def __init__(
        self,
        season: str = None,
        delay: float = 0.25,
        max_retries: int = 5,
        retry_pause: float = 60.0,
        verbose: bool = True,
        use_downloaded_data: bool = False,
        skip_scraped: bool = False,
    ):
        """
        Initialize the scraper.
        
        Args:
            season: Season to scrape (e.g., "2024-2025"). Defaults to current.
            delay: Delay between requests in seconds.
            max_retries: Maximum retry attempts for failed requests.
            retry_pause: Pause between retries in seconds.
            verbose: Print progress information.
            use_downloaded_data: If True, skip leagues whose per-league JSON
                already exists and reuse the downloaded data instead.
            skip_scraped: If True, skip scraping for leagues that already have a saved JSON file.
        """
        if season:
            self.season = season
            self.season_year = self._get_season_year(season)
        else:
            year = datetime.now().year
            if datetime.now().month < 7:
                year -= 1
            self.season = f"{year}-{year+1}"
            self.season_year = year
        
        self.delay = delay
        self.max_retries = max_retries
        self.retry_pause = retry_pause
        self.verbose = verbose
        self.use_downloaded_data = use_downloaded_data
        self.skip_scraped = skip_scraped
        
        # Ensure data directory exists
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    def _has_scraped_file(self, file_name: str) -> bool:
        """Check if a saved JSON file already exists (including multi-part files)."""
        from scraping.utils.helpers import _get_json_part_paths
        return len(_get_json_part_paths(file_name)) > 0
    
    def _get_season_year(self, season: str) -> int:
        """Extract starting year from season string."""
        match = re.search(r"(\d{4})", str(season))
        if match:
            return int(match.group(1))
        return datetime.now().year
    
    def log(self, message: str):
        """Print message if verbose mode is on."""
        if self.verbose:
            try:
                print(message)
            except UnicodeEncodeError:
                print(str(message).encode("utf-8", "replace").decode("cp1252", "replace"))
    
    def fetch_page(
        self,
        url: str,
        tries: int = None,
        pause: float = None,
    ) -> Optional[BeautifulSoup]:
        """
        Fetch a URL and return BeautifulSoup object.
        
        Args:
            url: URL to fetch
            tries: Number of retry attempts
            pause: Pause between retries
        
        Returns:
            BeautifulSoup object or None if failed
        """
        tries = tries or self.max_retries
        pause = pause or self.retry_pause
        
        for attempt in range(1, tries + 1):
            try:
                time.sleep(self.delay)
                headers = pick_headers()
                
                if USE_TLS:
                    response = tls_requests.get(url, headers=headers)
                else:
                    response = requests.get(url, headers=headers)
                
                if response.status_code == 200:
                    return BeautifulSoup(response.content, "html.parser")
                else:
                    self.log(f"  Attempt {attempt}/{tries}: HTTP {response.status_code}")
                    
            except Exception as e:
                self.log(f"  Attempt {attempt}/{tries}: Error {e!r}")
            
            if attempt < tries:
                time.sleep(pause)
        
        return None
    
    def generate_id(self, *parts: str) -> str:
        """Generate a unique ID from parts."""
        combined = "_".join(str(p) for p in parts if p)
        return hashlib.md5(combined.encode()).hexdigest()[:12]
    
    def extract_team_id(self, url: str) -> Optional[str]:
        """Extract team ID from URL."""
        match = re.search(r"/verein/(\d+)", url)
        return match.group(1) if match else None
    
    def extract_player_id(self, url: str) -> Optional[str]:
        """Extract player ID from URL."""
        match = re.search(r"/spieler/(\d+)", url)
        return match.group(1) if match else None
    
    def get_league_url(self, league: str) -> str:
        """Get the URL path for a league."""
        league_lower = league.lower().strip().replace(" ", "_")
        entry = self.LEAGUE_INFO.get(league_lower)
        if entry:
            return entry["url"]
        return f"/{league_lower}/startseite/wettbewerb"
    
    def search_team(self, team_name: str) -> Optional[Dict[str, str]]:
        """
        Search for a team by name.
        
        Args:
            team_name: Team name to search
        
        Returns:
            Dict with team_name, team_url, team_id or None
        """
        search_url = f"{self.BASE_URL}/schnellsuche/ergebnis/schnellsuche?query={team_name.replace(' ', '+')}"
        
        self.log(f"Searching for team: {team_name}")
        soup = self.fetch_page(search_url)
        
        if not soup:
            return None
        
        # Find team results
        for box in soup.select("div.box"):
            header = box.select_one("h2")
            if header and "club" in header.text.lower():
                link = box.select_one("table.items td.hauptlink a")
                if link:
                    href = link.get("href", "")
                    name = link.text.strip()
                    team_id = self.extract_team_id(href)
                    
                    return {
                        "team_name": name,
                        "team_url": f"{self.BASE_URL}{href}",
                        "team_id": team_id,
                    }
        
        # Fallback: first link with verein
        link = soup.select_one("a[href*='/verein/']")
        if link:
            href = link.get("href", "")
            name = link.get("title") or link.text.strip()
            team_id = self.extract_team_id(href)
            if team_id:
                return {
                    "team_name": name,
                    "team_url": f"{self.BASE_URL}{href}",
                    "team_id": team_id,
                }
        
        return None
    
    def get_league_teams(self, league: str) -> List[Dict[str, str]]:
        """
        Get all teams from a league.
        
        Args:
            league: League name (e.g., "laliga", "premier")
        
        Returns:
            List of dicts with team_name, team_url, team_id
        """
        league_path = self.get_league_url(league)
        url = f"{self.BASE_URL}{league_path}/saison_id/{self.season_year}"
        
        self.log(f"Fetching teams from {league}...")
        soup = self.fetch_page(url)
        
        if not soup:
            self.log(f"Failed to fetch league page")
            return []
        
        teams = []
        seen_ids = set()
        
        # Try multiple selectors
        for selector in ["table.items tbody tr td.hauptlink a", "div.responsive-table table tbody tr td a[title]"]:
            for a in soup.select(selector):
                href = a.get("href", "")
                title = a.get("title", "") or a.text.strip()
                
                if "verein" in href and title:
                    team_id = self.extract_team_id(href)
                    if team_id and team_id not in seen_ids:
                        seen_ids.add(team_id)
                        teams.append({
                            "team_name": title,
                            "team_url": f"{self.BASE_URL}{href}",
                            "team_id": team_id,
                        })
        
        self.log(f"Found {len(teams)} teams")
        return teams
    
    def get_transferred_player_ids(self, team_id: str, team_name: str = "") -> List[tuple]:
        """
        Scrape the season transfer page for a team and return the
        (player_id, player_name) pairs found in arrivals & departures.

        This is a lightweight helper used by the players, valuations and
        transfers scrapers to discover players that are not in the current
        squad (Phase 2).
        """
        season_year = str(self.season_year)
        url = f"{self.BASE_URL}/-/transfers/verein/{team_id}/saison_id/{season_year}"

        self.log(f"  Scanning transfer page: {team_name or team_id} ({self.season})")
        soup = self.fetch_page(url)

        if not soup:
            return []

        players: List[tuple] = []
        seen: set = set()

        for box in soup.select("div.box"):
            header = box.select_one("h2")
            if not header:
                continue
            ht = header.text.strip().lower()
            if not any(kw in ht for kw in ("arrival", "departure", "llegada", "salida", "zugänge", "abgänge")):
                continue

            table = box.select_one("table.items")
            if not table:
                continue
            tbody = table.select_one("tbody")
            if not tbody:
                continue

            for row in tbody.select("tr.odd, tr.even"):
                link = row.select_one("a[href*='/profil/spieler/'], a[href*='/spieler/']")
                if not link:
                    continue
                pid = self.extract_player_id(link.get("href", ""))
                pname = link.get("title", "") or link.text.strip()
                if pid and pid not in seen:
                    seen.add(pid)
                    players.append((pid, pname))

        self.log(f"    Found {len(players)} players on transfer page")
        return players

    def save_json(
        self,
        data: Any,
        file_name: str,
        validate: bool = True,
        create_backup: bool = True,
        min_items: int = 5,
        id_field: str = "team_id",
        data_type: str = "teams"
    ) -> Path:
        """
        Save data to JSON file with optional validation and backup.
        
        Args:
            data: Data to save
            file_name: Filename without extension
            validate: If True, validate data before saving
            create_backup: If True, create _OLD backup of previous file
            min_items: Minimum items for validation
            id_field: Field for unique ID when merging
            data_type: Type of data for validation
        
        Returns:
            Path to saved file
        """
        from scraping.utils.helpers import overwrite_dict_data, write_dict_to_json, DATA_DIR
        
        file_path = DATA_DIR / f"{file_name}.json"
        
        if create_backup:
            # Use overwrite with backup and optional validation
            success = overwrite_dict_data(
                data=data,
                file_name=file_name,
                ignore_valid_file=not validate,
                ignore_old_data=False,
                min_items=min_items,
                id_field=id_field,
                data_type=data_type
            )
            if success:
                self.log(f"Saved (with backup): {file_path}")
            else:
                self.log(f"Warning: Save failed or skipped for {file_name}")
        else:
            # Simple save without backup
            write_dict_to_json(data, file_name)
            self.log(f"Saved: {file_path}")
        
        return file_path
    
    def load_json(self, file_name: str) -> Optional[Any]:
        """
        Load data from JSON file.
        
        Args:
            file_name: Filename without extension
        
        Returns:
            Data or None if file doesn't exist
        """
        from scraping.utils.helpers import load_json
        return load_json(file_name)
    
    @staticmethod
    def normalize_string(s: str) -> str:
        """Normalize string for comparison."""
        if not s:
            return ""
        return unidecode(str(s)).lower().replace(" ", "").replace("-", "")
    
    @staticmethod
    def parse_market_value(value_str: str) -> Optional[float]:
        """Parse market value string to float (in euros)."""
        if not value_str:
            return None
        
        # Clean the string - remove all non-numeric except decimal separators and multiplier letters
        value_str = value_str.strip().lower()
        
        # Remove currency symbols and other unicode chars (keep only alphanumeric, dots, commas)
        value_str = re.sub(r"[^\d.,a-z]", "", value_str)
        
        # Normalize decimal separator
        value_str = value_str.replace(",", ".")
        
        multiplier = 1
        if "bn" in value_str:
            multiplier = 1_000_000_000
            value_str = value_str.replace("bn", "")
        elif "b" in value_str:
            multiplier = 1_000_000_000
            value_str = value_str.replace("b", "")
        elif "mill" in value_str:
            multiplier = 1_000_000
            value_str = value_str.replace("mill", "")
        elif "m" in value_str:
            multiplier = 1_000_000
            value_str = value_str.replace("m", "")
        elif "k" in value_str:
            multiplier = 1_000
            value_str = value_str.replace("k", "")
        elif "th" in value_str:
            multiplier = 1_000
            value_str = value_str.replace("th", "")
        
        # Remove any remaining non-numeric chars except dot
        value_str = re.sub(r"[^\d.]", "", value_str)
        
        try:
            return round(float(value_str) * multiplier, 0)
        except ValueError:
            return None
