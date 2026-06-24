"""FastAPI app — wraps the generation engine for browser-based use.

Endpoints:
  GET  /                  -> serves the UI (static index.html)
  GET  /api/health        -> liveness
  POST /api/generate      -> run pipeline, return per-file content + metadata
  GET  /api/download/{name}-> download a single generated file (from last run)
  GET  /api/download-all  -> zip of all files from last run

The engine is identical to the CLI path; this only adds an HTTP surface.
"""
from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.runner import generate

app = FastAPI(title="Agency Data Mapping Tool", version="1.0")

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_SOURCE = os.path.join(_BASE_DIR, "tests", "fixtures", "source")
_DEFAULT_CONFIG = os.path.join(_BASE_DIR, "tests", "fixtures", "THP Agency Data Mapping.json")
_STATIC_DIR = os.path.join(_BASE_DIR, "web")

# In-memory store of the most recent generation (per-process; fine for an
# internal single-instance tool). Keyed by filename -> content string.
_LAST_RUN: dict[str, str] = {}
_LAST_RUN_META: dict[str, object] = {}


class GenerateRequest(BaseModel):
    source: str = "excel"  # "excel" | "google_sheets"
    source_dir: Optional[str] = None
    config_path: Optional[str] = None
    service_account_file: Optional[str] = None


class FileResult(BaseModel):
    name: str
    lines: int
    bytes: int


class GenerateResponse(BaseModel):
    generated_at: str
    source: str
    files: list[FileResult]
    total_objects: int


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/generate", response_model=GenerateResponse)
def api_generate(req: GenerateRequest) -> GenerateResponse:
    source_dir = req.source_dir or _DEFAULT_SOURCE
    config_path = req.config_path or _DEFAULT_CONFIG
    use_sheets = req.source == "google_sheets"

    if not os.path.exists(config_path):
        raise HTTPException(status_code=400, detail=f"Config not found: {config_path}")
    has_env_service_account = bool(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip())
    if use_sheets and not (req.service_account_file or has_env_service_account):
        raise HTTPException(
            status_code=400,
            detail="Google Sheets source requires service_account_file or GOOGLE_SERVICE_ACCOUNT_JSON.",
        )

    try:
        outputs = generate(
            source_dir=source_dir,
            config_path=config_path,
            out_dir=None,
            use_google_sheets=use_sheets,
            service_account_file=req.service_account_file,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # surface engine errors to the UI
        raise HTTPException(status_code=500, detail=f"Generation failed: {exc}")

    _LAST_RUN.clear()
    _LAST_RUN.update(outputs)

    files: list[FileResult] = []
    total_objects = 0
    for name, content in outputs.items():
        # objects = lines minus the Begin/End wrapper (2 lines) and trailing newline
        line_count = content.count("\n")
        objects = max(line_count - 2, 0)
        total_objects += objects
        files.append(FileResult(
            name=name,
            lines=objects,
            bytes=len(content.encode("utf-8-sig")),
        ))

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": req.source,
    }
    _LAST_RUN_META.clear()
    _LAST_RUN_META.update(meta)

    return GenerateResponse(
        generated_at=str(meta["generated_at"]),
        source=req.source,
        files=files,
        total_objects=total_objects,
    )


@app.get("/api/download/{name}")
def download_one(name: str) -> Response:
    if name not in _LAST_RUN:
        raise HTTPException(status_code=404, detail="File not in last run. Generate first.")
    data = _LAST_RUN[name].encode("utf-8-sig")
    return Response(
        content=data,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.get("/api/download-all")
def download_all() -> Response:
    if not _LAST_RUN:
        raise HTTPException(status_code=404, detail="Nothing generated yet.")
    buf = io.BytesIO()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in _LAST_RUN.items():
            zf.writestr(name, content.encode("utf-8-sig"))
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="webobjects-{stamp}.zip"'},
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    index_path = os.path.join(_STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h1>UI not built</h1>", status_code=404)
    with open(index_path, encoding="utf-8") as fh:
        return HTMLResponse(fh.read())


if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
