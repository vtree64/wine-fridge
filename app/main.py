"""FastAPI application: serves the static UI and the /api/* endpoints."""

import base64
import csv
import io
import os
import re
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import config, db, llm

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Vinotag", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Config / status
# ---------------------------------------------------------------------------

@app.get("/api/config")
def api_config():
    return {
        "shelves": config.SHELVES,
        "llm": {
            "server": config.LLAMA_SERVER_URL,
            "model": config.LLAMA_MODEL,
        },
        "bottleCount": db.count_bottles(),
    }


@app.get("/api/llm/status")
def api_llm_status():
    return llm.server_status()


# ---------------------------------------------------------------------------
# Label analysis
# ---------------------------------------------------------------------------

@app.post("/api/analyze")
async def api_analyze(request: Request):
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")
    try:
        return llm.analyze_image(body.get("image", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# Bottles
# ---------------------------------------------------------------------------

def _decode_image(data_url: str | None) -> tuple[bytes | None, str | None]:
    if not data_url:
        return None, None
    match = re.match(r"^data:([^;]+);base64,(.+)$", data_url, re.DOTALL)
    if not match:
        raise ValueError("Invalid image data.")
    mime = match.group(1)
    raw = base64.b64decode(match.group(2))
    if len(raw) > config.MAX_IMAGE_BYTES:
        raise ValueError("The label photo is too large.")
    return raw, mime


@app.get("/api/bottles")
def api_list_bottles():
    return db.list_bottles()


@app.post("/api/bottles")
async def api_add_bottle(request: Request):
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")
    try:
        image_bytes, image_mime = _decode_image(body.get("label_image"))
        return db.add_bottle(body, image_bytes, image_mime)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.patch("/api/bottles/{bottle_id}")
async def api_update_bottle(bottle_id: str, request: Request):
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")
    try:
        return db.update_bottle(bottle_id, body)
    except KeyError:
        raise HTTPException(status_code=404, detail="Bottle not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/bottles/{bottle_id}")
def api_delete_bottle(bottle_id: str):
    try:
        db.delete_bottle(bottle_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Bottle not found.")
    return {"success": True}


@app.get("/api/bottles/{bottle_id}/image")
def api_bottle_image(bottle_id: str):
    row = db.get_bottle_row(bottle_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Bottle not found.")
    if not row.get("label_image"):
        raise HTTPException(status_code=404, detail="No label photo stored for this bottle.")
    return Response(
        content=row["label_image"],
        media_type=row.get("label_mime") or "image/jpeg",
    )


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@app.get("/api/export.csv")
def api_export_csv():
    bottles = db.list_bottles()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["Bottle ID", "Date Added", "Wine", "Variety", "Vintage",
         "Vineyard / Producer", "Shelf", "Notes"]
    )
    for b in bottles:
        writer.writerow(
            [b["id"], b["date_added"], b["wine"], b["variety"],
             b["vintage"], b["vineyard_producer"], b["shelf"], b["notes"]]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="wine-inventory.csv"'},
    )


# ---------------------------------------------------------------------------
# Spreadsheet import
# ---------------------------------------------------------------------------

SEED_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "seed")
)


@app.post("/api/import")
async def api_import(file: UploadFile | None = File(None)):
    """Import bottles from a spreadsheet.

    With a multipart file upload, imports that file. Without one, imports the
    bundled spreadsheet (data dir first, then the seed copy baked into the
    image — the data dir is a bind mount that shadows the image's /app/data).
    """
    from .importer import import_from_xlsx

    tmp_path = None
    try:
        if file is not None and file.filename:
            suffix = os.path.splitext(file.filename)[1] or ".xlsx"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(await file.read())
                tmp_path = tmp.name
        else:
            candidates = [
                os.path.join(config.DATA_DIR, "Wine Inventory.xlsx"),
                os.path.join(SEED_DIR, "Wine Inventory.xlsx"),
            ]
            tmp_path = next((p for p in candidates if os.path.exists(p)), None)
            if tmp_path is None:
                raise HTTPException(404, "No bundled spreadsheet found. Upload a .xlsx file instead.")
        added, skipped, total = import_from_xlsx(tmp_path)
        return {"success": True, "added": added, "skipped": skipped, "total": total}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Import failed: {exc}")
    finally:
        if (
            tmp_path
            and tmp_path.startswith(tempfile.gettempdir())
            and os.path.exists(tmp_path)
        ):
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Static UI (mounted last so /api/* routes take precedence)
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
