# scraping/utils/tm_club_api_cache.py
"""
Shared on-disk cache for the Transfermarkt alpha API ``/clubs`` and
``/club/<id>`` endpoints.

The cache lives at ``data/cache/tm_club_api_cache.json`` and stores, keyed by
``club_id``:

* ``name``          – club name (may be empty / missing until resolved)
* ``main_club_id``  – parent club id, or ``None`` if the club has no parent
* ``has_base_details`` – ``True`` when ``baseDetails`` was seen in the
                         API response (so ``main_club_id`` can be trusted
                         as "known-null" vs. "unknown")
* ``fetched_at``    – ISO timestamp of the last update

The goal is to make it cheap to:

1. Batch-resolve many club fields in a single ``/clubs?ids[]=...`` call with
   adaptive splitting on 414/429/5xx errors (the same pattern used by
   ``fill_club_names.py``).
2. Reuse that work across different scripts (``fill_club_names.py``,
   ``fill_parent_team_id.py``, the team scraper, …) so we do not hit the
   API twice for the same club id in a single pipeline run.

Typical usage::

    from scraping.utils.tm_club_api_cache import TmClubApiCache

    cache = TmClubApiCache.load()
    resolved = cache.fetch(ids={"583", "92878"}, need=("name", "main_club_id"))
    cache.save()

    # resolved is {"583": {"name": "Barcelona", "main_club_id": None, ...}, ...}
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import requests

from scraping.utils.helpers import ROOT_DIR

# ── Constants ────────────────────────────────────────────────────────────────

TM_API_URL = "https://tmapi-alpha.transfermarkt.technology"

CACHE_DIR = ROOT_DIR / "data" / "cache"
CACHE_FILE = CACHE_DIR / "tm_club_api_cache.json"

_DEFAULT_MAX_RETRIES = 50
_DEFAULT_RETRY_PAUSE = 10  # seconds
_DEFAULT_REQUEST_DELAY = 0  # seconds


# ── Entry dataclass ──────────────────────────────────────────────────────────


@dataclass
class _Entry:
    name: Optional[str] = None
    main_club_id: Optional[str] = None
    has_base_details: bool = False
    fetched_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "main_club_id": self.main_club_id,
            "has_base_details": self.has_base_details,
            "fetched_at": self.fetched_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "_Entry":
        return cls(
            name=d.get("name"),
            main_club_id=d.get("main_club_id"),
            has_base_details=bool(d.get("has_base_details", False)),
            fetched_at=d.get("fetched_at"),
        )


# ── Cache class ──────────────────────────────────────────────────────────────


@dataclass
class TmClubApiCache:
    """In-memory + on-disk cache of club metadata pulled from the TM API."""

    entries: Dict[str, _Entry] = field(default_factory=dict)
    path: Path = CACHE_FILE
    max_retries: int = _DEFAULT_MAX_RETRIES
    retry_pause: float = _DEFAULT_RETRY_PAUSE
    request_delay: float = _DEFAULT_REQUEST_DELAY
    verbose: bool = True
    _dirty: bool = False

    # ── Persistence ──────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Path = CACHE_FILE, **kwargs) -> "TmClubApiCache":
        inst = cls(path=path, **kwargs)
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                if isinstance(raw, dict):
                    inst.entries = {
                        str(k): _Entry.from_dict(v) for k, v in raw.items() if isinstance(v, dict)
                    }
            except Exception as exc:
                inst._log(f"  [cache] Could not read {path}: {exc!r}. Starting fresh.")
                inst.entries = {}
        return inst

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(
                {k: v.to_dict() for k, v in self.entries.items()},
                fh,
                ensure_ascii=False,
                indent=0,
            )
        tmp.replace(self.path)
        self._dirty = False

    # ── Helpers ──────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        if self.verbose:
            try:
                from tqdm import tqdm  # noqa: WPS433

                tqdm.write(msg)
            except Exception:
                print(msg)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def get(self, club_id: str) -> Optional[_Entry]:
        return self.entries.get(str(club_id))

    def set(
        self,
        club_id: str,
        *,
        name: Optional[str] = None,
        main_club_id: Optional[str] = None,
        has_base_details: Optional[bool] = None,
    ) -> None:
        cid = str(club_id)
        entry = self.entries.get(cid) or _Entry()
        if name is not None:
            entry.name = name
        if main_club_id is not None or has_base_details:
            entry.main_club_id = main_club_id
        if has_base_details is not None:
            entry.has_base_details = has_base_details
        entry.fetched_at = self._now()
        self.entries[cid] = entry
        self._dirty = True

    def missing(self, ids: Iterable[str], need: Tuple[str, ...]) -> List[str]:
        """Return ids that still lack at least one requested field."""
        out: List[str] = []
        for raw in ids:
            if not raw:
                continue
            cid = str(raw)
            entry = self.entries.get(cid)
            if entry is None:
                out.append(cid)
                continue
            if "name" in need and not entry.name:
                out.append(cid)
                continue
            if "main_club_id" in need and not entry.has_base_details:
                out.append(cid)
                continue
        return out

    # ── HTTP ─────────────────────────────────────────────────────────────

    def _api_get(self, url: str, timeout: int = 60) -> Optional[dict]:
        """GET with retry logic. Returns parsed JSON, ``{"_status": code}`` on
        persistent transient errors (414/429/5xx), or ``None`` on hard failure.
        """
        last_transient_code: Optional[int] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                if self.request_delay:
                    time.sleep(self.request_delay)
                resp = requests.get(url, timeout=timeout)

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code == 414:
                    return {"_status": 414}

                if resp.status_code in (429, 500, 502, 503, 504):
                    last_transient_code = resp.status_code
                    self._log(
                        f"    Attempt {attempt}/{self.max_retries}: HTTP {resp.status_code}"
                    )
                else:
                    self._log(f"    HTTP {resp.status_code} – giving up")
                    return None

            except Exception as exc:
                last_transient_code = last_transient_code or 429
                self._log(f"    Attempt {attempt}/{self.max_retries}: {exc!r}")

            if attempt < self.max_retries:
                self._log(f"    Retrying in {self.retry_pause}s …")
                time.sleep(self.retry_pause)

        self._log(f"    All {self.max_retries} attempts failed for {url}")
        if last_transient_code is not None:
            return {"_status": last_transient_code}
        return None

    # ── Parsing ──────────────────────────────────────────────────────────

    @staticmethod
    def _extract_club_fields(club: dict) -> Tuple[Optional[str], Optional[str], bool]:
        """Return ``(name, main_club_id, has_base_details)`` from a club blob.

        ``main_club_id`` follows the project convention: equal to own ``id``
        or ``"0"`` → treat as *no parent* (``None``).  Absence of
        ``baseDetails`` on the payload → ``has_base_details=False`` and the
        caller should fall back to the single-club endpoint.
        """
        own_id = str(club.get("id") or "") or None
        name = club.get("name") or None
        base_details = club.get("baseDetails")
        if not isinstance(base_details, dict):
            return name, None, False

        raw = base_details.get("mainClubId")
        if raw is None:
            return name, None, True
        sraw = str(raw).strip()
        if not sraw or sraw == "0":
            return name, None, True
        if own_id and sraw == own_id:
            return name, None, True
        return name, sraw, True

    # ── Public fetch API ─────────────────────────────────────────────────

    def resolve_names(
        self,
        ids: Iterable[str],
        *,
        pbar_desc: str = "Fetching club names",
    ) -> Dict[str, str]:
        """Convenience wrapper: return ``{club_id: name}`` for every id.

        Only the ``name`` field is required, so this will NOT fall back to
        the single-club endpoint when ``baseDetails`` is missing from the
        batch response (``/clubs?ids[]=...`` is always enough for names).
        """
        resolved = self.fetch(ids, need=("name",), pbar_desc=pbar_desc)
        out: Dict[str, str] = {}
        for raw in ids:
            if not raw:
                continue
            cid = str(raw)
            entry = resolved.get(cid) or self.get(cid)
            if entry and entry.name:
                out[cid] = entry.name
        return out

    def fetch(
        self,
        ids: Iterable[str],
        need: Tuple[str, ...] = ("name", "main_club_id"),
        *,
        pbar_desc: str = "Fetching clubs",
    ) -> Dict[str, _Entry]:
        """Resolve the requested ``need`` fields for every id in *ids*.

        Strategy:

        1. Split ids into (already cached) vs (missing at least one field).
        2. For missing ids, call the batch ``/clubs?ids[]=...`` endpoint with
           adaptive halving on 414/429/5xx.
        3. If the response did not include ``baseDetails`` for a given club
           (and the caller needs ``main_club_id``), fall back to the single
           ``/club/<id>`` endpoint.

        Returns a ``{club_id: _Entry}`` dict limited to the ids in *ids*
        (and only for those we managed to resolve at least partially).
        """
        from tqdm import tqdm  # local import to keep module lightweight

        ids_list = sorted({str(i) for i in ids if i})
        if not ids_list:
            return {}

        need_main = "main_club_id" in need
        missing = self.missing(ids_list, need)

        if missing:
            pbar = tqdm(total=len(missing), desc=pbar_desc, unit="id")
            self._fetch_batch(missing, need_main=need_main, pbar=pbar)
            pbar.close()

        # Collect output — only ids that ended up with at least one value
        out: Dict[str, _Entry] = {}
        for cid in ids_list:
            entry = self.entries.get(cid)
            if entry is not None:
                out[cid] = entry
        return out

    def _fetch_batch(
        self,
        batch: List[str],
        *,
        need_main: bool,
        pbar,
    ) -> None:
        if not batch:
            return

        params = "&".join(f"ids[]={cid}" for cid in batch)
        api_url = f"{TM_API_URL}/clubs?{params}"
        data = self._api_get(api_url)

        if data is None:
            self._log(f"    FAILED to fetch batch of {len(batch)} – skipping")
            pbar.update(len(batch))
            return

        status = data.get("_status") if isinstance(data, dict) else None
        if status is not None:
            if len(batch) <= 1:
                self._log(f"    Cannot split further, skipping ID: {batch[0]}")
                pbar.update(len(batch))
                return
            mid = len(batch) // 2
            self._log(f"    HTTP {status} with {len(batch)} IDs → splitting")
            self._fetch_batch(batch[:mid], need_main=need_main, pbar=pbar)
            self._fetch_batch(batch[mid:], need_main=need_main, pbar=pbar)
            return

        seen: Set[str] = set()
        need_fallback: List[str] = []

        if isinstance(data, dict) and data.get("success") and isinstance(data.get("data"), list):
            for club in data["data"]:
                if not isinstance(club, dict):
                    continue
                cid = str(club.get("id") or "")
                if not cid:
                    continue
                name, main_id, has_base = self._extract_club_fields(club)
                self.set(cid, name=name, main_club_id=main_id, has_base_details=has_base)
                seen.add(cid)
                if need_main and not has_base:
                    need_fallback.append(cid)

        # Any id we did not see at all → fallback per-id
        for cid in batch:
            if cid not in seen:
                need_fallback.append(cid)

        pbar.update(len(batch) - len(need_fallback))

        for cid in need_fallback:
            self._fetch_single(cid)
            pbar.update(1)

    def _fetch_single(self, club_id: str) -> None:
        """Fallback to ``/club/<id>`` when the batch endpoint lacks baseDetails."""
        url = f"{TM_API_URL}/club/{club_id}"
        data = self._api_get(url)
        if not isinstance(data, dict):
            return
        status = data.get("_status")
        if status is not None:
            self._log(f"    [{club_id}] single fetch transient error {status} – skipping")
            return

        payload = data.get("data") if data.get("success") is not False else None
        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if not isinstance(payload, dict):
            return

        name, main_id, has_base = self._extract_club_fields(payload)
        self.set(club_id, name=name, main_club_id=main_id, has_base_details=has_base)
