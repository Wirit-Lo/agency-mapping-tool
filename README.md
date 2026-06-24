# Agency Data Mapping Tool — Python rewrite

Rewrite of the C# WinForms tool that converts THP Pay@Post agency config
(Excel **or** Google Sheets) into Escher SBA WebObject `.txt` files.

## Status
- [x] **Phase 1** — `LOGIC_SPEC.md`: full logic extracted from the C# source
- [x] **Phase 2** — models, helpers, rules, serializers, golden harness
- [x] **Phase 3** — loaders (Excel) → RawData
- [x] **Phase 4** — full 18-step enrichment pipeline + barcode state machine
- [x] **Verified** — all **8/8** output files are **byte-identical** to the
      original C# output (line order + content + UTF-8 BOM)
- [x] **Google Sheets** — pluggable source; same pipeline, no logic change
- [x] **Phase 6** — FastAPI backend (8/8 downloads byte-identical through HTTP)
- [x] **Phase 7** — minimal web UI (single-page, no build step)

## Verification
```
pip install -r requirements.txt
python -m pytest tests/ -v
```
`tests/test_golden_full.py` runs the real pipeline against snapshotted source
workbooks and asserts every output file matches `tests/golden/` byte-for-byte.

## Run (local Excel)
```
python -m app.cli --source tests/fixtures/source \
    --config "tests/fixtures/THP Agency Data Mapping.json" --out ./out
```

## Run (Google Sheets)
1. Create a Google Cloud service account, enable the Sheets API, download its
   JSON key, and share each source spreadsheet with the service account email
   (read-only).
2. Spreadsheet IDs are pre-filled in `app/sheets/google_sheets.py`
   (`SPREADSHEET_IDS`) from the THP Drive folder — verify they're current.
```
python -m app.cli --google-sheets --service-account sa.json \
    --config "tests/fixtures/THP Agency Data Mapping.json" --out ./out
```

## Run the web app
```
pip install -r requirements.txt
uvicorn app.api:app --host 0.0.0.0 --port 8000
```
Then open http://localhost:8000 — pick a source, click **Generate files**,
download individually or as a zip. The per-file grid shows object counts so you
can sanity-check a run at a glance. Downloads are byte-identical to the engine
output (verified in `tests/test_api.py`).

## Deploy on Render
1. Push this project to a new GitHub repository.
2. In Render, create a new **Blueprint** or **Web Service** from that repo.
3. Use the included `render.yaml`, or set:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.api:app --host 0.0.0.0 --port $PORT`
   - Health Check Path: `/api/health`
4. Add `GOOGLE_SERVICE_ACCOUNT_JSON` as a secret environment variable. Paste the
   full Google service account JSON as the value, and share the source
   spreadsheets with that service account email.

For deployed Google Sheets runs, choose **Google Sheets** in the web UI and click
**Generate files**. The backend reads the latest sheet data at run time.

## Layout
```
app/
  models/raw.py            # Pydantic models, 1:1 with C# RawData
  pipeline/
    rules.py               # static business-rule ID lists (verbatim)
    helpers.py             # GetCellValue / ToInt / GetFeeValue / type maps
    enrich.py              # agency+field builder + 18 enrichment steps
    barcode.py             # barcode state machine + 2 field post-passes
  sheets/
    loaders.py             # Excel loaders (pluggable grid provider)
    google_sheets.py       # Google Sheets grid provider (cache + TTL)
  serialize/webobjects.py  # 8 format templates (Consts.cs authority)
  runner.py                # orchestrator: load -> enrich -> serialize -> write
  cli.py                   # command-line entry point
  api.py                   # FastAPI backend (generate / download / download-all)
web/
  index.html               # minimal single-page UI (no build step)
tests/
  golden/                  # real RA_*.txt output from the C# tool (expected)
  fixtures/source/         # source .xlsx snapshots
  test_golden_50478.py     # per-object serializer golden test
  test_golden_full.py      # full byte-identity regression guard (8 files)
  test_api.py              # HTTP layer byte-identity tests
```

## Fidelity notes (hard-won, do not "simplify")
- Output: UTF-8 **with BOM**, **LF** line endings
- DerivedData uses `<Attibute:>` (typo) — intentional
- Optional tags omitted entirely when empty (never blank)
- iframe/exe services emit **two** scheme objects (Custom + _Actual)
- Fee uses string "00" padding (satang); Min/Max Amount uses ×100 — different
- `(blank)` is a sentinel meaning empty; integer-valued floats render w/o ".0"
- Date cells with a non-midnight time are dropped (matches C# OADate quirk);
  malformed `"01/10,2018"` (comma) is salvaged to a date
- 93005 MaxValue is 500000 (not 5000000); 93004 likewise
