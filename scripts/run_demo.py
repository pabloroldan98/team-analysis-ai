#!/usr/bin/env python3
"""
Launch the full demo stack: FastAPI backend + React frontend dev server.

Usage:
    python scripts/run_demo.py                    # default: port 8000
    python scripts/run_demo.py --port 8080        # custom port
    python scripts/run_demo.py --streamlit        # launch Streamlit instead

The script:
  1. Checks that cached data exists (gives instructions if not)
  2. Builds the React frontend (production) OR starts Vite dev server
  3. Starts the FastAPI backend with uvicorn
  4. Opens the browser automatically
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "json" / "cache"
FRONTEND_DIR = ROOT / "frontend"


def check_cache() -> bool:
    """Return True if at least one season cache file exists."""
    if not CACHE_DIR.exists():
        return False
    return any(CACHE_DIR.glob("season_data_*.json"))


def check_node() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def build_frontend():
    """Run npm install + npm run build for the React frontend."""
    if not (FRONTEND_DIR / "package.json").exists():
        print("[WARN] frontend/package.json not found — skipping frontend build")
        return False

    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        print("[INFO] Installing frontend dependencies...")
        subprocess.run(["npm", "install"], cwd=str(FRONTEND_DIR), check=True, shell=True)

    dist_dir = FRONTEND_DIR / "dist"
    print("[INFO] Building frontend (npm run build)...")
    subprocess.run(
        ["npm", "run", "build"],
        cwd=str(FRONTEND_DIR),
        check=True,
        shell=True,
        stderr=subprocess.STDOUT,
    )

    return dist_dir.exists()


def run_streamlit(port: int):
    """Launch Streamlit app."""
    print(f"\n{'='*60}")
    print(f"  Launching Streamlit demo on http://localhost:{port}")
    print(f"{'='*60}\n")
    time.sleep(1)
    webbrowser.open(f"http://localhost:{port}")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "streamlit_app.py",
         "--server.port", str(port), "--server.headless", "true"],
        cwd=str(ROOT),
    )


def run_fastapi(port: int):
    """Launch FastAPI + serve built frontend."""
    has_frontend = build_frontend() if check_node() else False

    print(f"\n{'='*60}")
    print(f"  Launching FastAPI demo on http://localhost:{port}")
    if has_frontend:
        print(f"  React frontend served from /frontend/dist")
    else:
        print(f"  (frontend not built — API-only mode)")
        print(f"  API docs at http://localhost:{port}/docs")
    print(f"{'='*60}\n")

    time.sleep(1)
    webbrowser.open(f"http://localhost:{port}")

    subprocess.run(
        [sys.executable, "-m", "uvicorn", "api.main:app",
         "--host", "0.0.0.0", "--port", str(port), "--reload"],
        cwd=str(ROOT),
    )


def main():
    parser = argparse.ArgumentParser(description="Launch Team Analysis AI demo")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    parser.add_argument("--streamlit", action="store_true", help="Use Streamlit frontend instead of React+FastAPI")
    args = parser.parse_args()

    if not check_cache():
        print("="*60)
        print("  WARNING: No cached season data found!")
        print("  The app will work but loading will be slow.")
        print()
        print("  To precompute caches, run:")
        print("    python scripts/precompute_active_players_cache.py --all-seasons")
        print("    python scripts/precompute_active_players_cache.py --season today")
        print("="*60)
        print()

    if args.streamlit:
        run_streamlit(args.port)
    else:
        run_fastapi(args.port)


if __name__ == "__main__":
    main()
