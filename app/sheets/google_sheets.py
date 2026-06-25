"""Google Sheets data source — provides the same grid interface as the Excel
loaders so the pipeline is unchanged when switching source.

Design: loaders.py reads via `_load_grid(path, sheet_index)` returning a
list-of-rows. This module offers `SheetsGrids`, which fetches each spreadsheet's
worksheets once (with caching) and serves grids by the same (key, sheet_index)
shape. A thin shim lets runner.py pass Sheets-backed grids into the existing
loader functions.

Requires a Google service account with read access to the source spreadsheets.
Install: pip install gspread google-auth
"""
from __future__ import annotations

import json
import os
import random
import time
from typing import Any, Optional

# Map logical source filename -> Google spreadsheet ID.
# Fill these in with the real IDs from the Drive folder.
SPREADSHEET_IDS: dict[str, str] = {
    "PayAtPost-PAP_ALL_ServiceID_V1.2-1.3.xlsx": "1_SrSUDJl05r944ZWDhqKiHdw5E_G9Rqn8qqstrZ-rTw",
    "PayAtPost-StatSUM_Master_V1.2.xlsx": "1VNe9nOa5wwL4Of67hhnLbhQWmTZwae4EwC_Y8p1yG0k",
    "PayAtPost-SpecBarcode_V1.5.xlsx": "1zgdfhYz4yaEFsAA_gsAR6xtTJNqmqDej6KWmSFbbmJo",
    "PayAtPost-ValidateScriptText.xlsx": "1-Tv5tbuxucm5peFVQTpJv4sO1sSxu88cWpIiJAN0dBs",
    "PayAtPost-DropdownValue.xlsx": "1CWPHwAThS0b4zKXafNvqP_kYFuUxnSQD7AJrpt7s3Z8",
    "PayAtPost-DefaultValue_V1.0.xlsx": "1FGWPMdC2_iRBGbsJJeBE65QVu0YLrXgjvX86jKoCNos",
    "PayAtPost-ConfigReceipt_V1.0.xlsx": "1_HxLML_uIpSL-7d5_Nh42RxtYc_B1lu160F8PHA5UNY",
    "AgencyDerivedDataRequirements.xlsx": "1S8Q52tIQ4J8c9zWMeki15upRy6VlahgpEA3WK-nJ4EE",
    "AgencyServiceProviders.xlsx": "1DtC8yWZxMMbJUOLRd8AwzkJEOWgriDRznSLdNB3sAqA",
    "AgentMasterData.xlsx": "1Jzh4peRzhho_1V8UvkpecrwSJgaUag9UXY8nrtlLEmw",
}

_CACHE_TTL_SECONDS = 300


class SheetsGrids:
    """Fetches and caches worksheet grids from Google Sheets.

    Usage:
        grids = SheetsGrids(service_account_file="sa.json")
        grid = grids.load("PayAtPost-StatSUM_Master_V1.2.xlsx", sheet_index=0)
    Returns the same list-of-rows shape as loaders._load_grid, so the existing
    _cell()/_raw() helpers work unchanged.
    """

    def __init__(self, service_account_file: Optional[str] = None,
                 spreadsheet_ids: Optional[dict[str, str]] = None,
                 cache_ttl: int = _CACHE_TTL_SECONDS):
        self._sa_file = service_account_file
        self._ids = spreadsheet_ids or SPREADSHEET_IDS
        self._ttl = cache_ttl
        self._client = None
        self._cache: dict[tuple[str, int], tuple[float, list[list[Any]]]] = {}

    def _get_client(self):
        if self._client is None:
            import gspread
            from google.oauth2.service_account import Credentials
            scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
            if self._sa_file:
                creds = Credentials.from_service_account_file(self._sa_file, scopes=scopes)
            else:
                raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
                if not raw_json:
                    raise ValueError(
                        "Google Sheets source requires service_account_file or "
                        "GOOGLE_SERVICE_ACCOUNT_JSON."
                    )
                creds = Credentials.from_service_account_info(json.loads(raw_json), scopes=scopes)
            self._client = gspread.authorize(creds)
        return self._client

    def _with_backoff(self, fn):
        """Retry transient Sheets quota errors with truncated exponential backoff."""
        from gspread.exceptions import APIError

        delay = 1.0
        for attempt in range(6):
            try:
                return fn()
            except APIError as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status != 429 or attempt == 5:
                    raise
                time.sleep(delay + random.random())
                delay = min(delay * 2, 32)

    def _fetch_sheet(self, filename: str, sheet_index: int) -> list[list[Any]]:
        """Fetch only the worksheet the pipeline needs."""
        spreadsheet_id = self._ids[filename]
        client = self._get_client()
        ss = self._with_backoff(lambda: client.open_by_key(spreadsheet_id))
        ws = ss.get_worksheet(sheet_index)
        if ws is None:
            return []
        # get_all_values returns list[list[str]]; matches Excel grid shape.
        return self._with_backoff(ws.get_all_values)

    def load(self, filename: str, sheet_index: int = 0,
             force_refresh: bool = False) -> list[list[Any]]:
        now = time.time()
        key = (filename, sheet_index)
        cached = self._cache.get(key)
        if force_refresh or cached is None or (now - cached[0]) > self._ttl:
            grid = self._fetch_sheet(filename, sheet_index)
            self._cache[key] = (now, grid)
        else:
            grid = cached[1]
        return grid

    def invalidate(self, filename: Optional[str] = None) -> None:
        if filename is None:
            self._cache.clear()
        else:
            for key in [key for key in self._cache if key[0] == filename]:
                self._cache.pop(key, None)
