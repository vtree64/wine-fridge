"""SQLite storage layer for the wine inventory."""

import datetime
import os
import re
import sqlite3
import uuid

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS bottles (
    id                TEXT PRIMARY KEY,
    date_added        TEXT NOT NULL,
    wine              TEXT NOT NULL,
    variety           TEXT NOT NULL DEFAULT '',
    vintage           TEXT NOT NULL DEFAULT '',
    vineyard_producer TEXT NOT NULL DEFAULT '',
    shelf             TEXT NOT NULL,
    notes             TEXT NOT NULL DEFAULT '',
    label_image       BLOB,
    label_mime        TEXT
);
"""

UPDATABLE_FIELDS = ("wine", "variety", "vintage", "vineyard_producer", "shelf", "notes")


def get_conn() -> sqlite3.Connection:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def _clean(value) -> str:
    return str(value if value is not None else "").strip()


def _clean_vintage(value) -> str:
    text = _clean(value)
    match = re.search(r"\b(18|19|20|21)\d{2}\b", text)
    return match.group(0) if match else text


def _row_to_dict(row: sqlite3.Row, include_image: bool = False) -> dict:
    d = dict(row)
    d["has_image"] = bool(d.get("label_image"))
    if not include_image:
        d.pop("label_image", None)
        d.pop("label_mime", None)
    return d


def list_bottles() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM bottles ORDER BY date_added ASC, rowid ASC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_bottle(bottle_id: str) -> dict:
    """Return a bottle without its image blob. Raises KeyError if missing."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM bottles WHERE id = ?", (bottle_id,)).fetchone()
    if row is None:
        raise KeyError("Bottle not found.")
    return _row_to_dict(row)


def get_bottle_row(bottle_id: str) -> dict | None:
    """Return the raw row including the image blob, or None."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM bottles WHERE id = ?", (bottle_id,)).fetchone()
    return dict(row) if row else None


def add_bottle(
    data: dict,
    image_bytes: bytes | None = None,
    image_mime: str | None = None,
    bottle_id: str | None = None,
    date_added: str | None = None,
) -> dict:
    wine = _clean(data.get("wine"))
    shelf = _clean(data.get("shelf"))
    if not wine:
        raise ValueError("Wine name is required.")
    if shelf not in config.SHELVES:
        raise ValueError("Please select a valid shelf.")

    bottle_id = bottle_id or str(uuid.uuid4())
    date_added = date_added or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO bottles
               (id, date_added, wine, variety, vintage, vineyard_producer,
                shelf, notes, label_image, label_mime)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bottle_id,
                date_added,
                wine,
                _clean(data.get("variety")),
                _clean_vintage(data.get("vintage")),
                _clean(data.get("vineyard_producer")),
                shelf,
                _clean(data.get("notes")),
                image_bytes,
                image_mime,
            ),
        )
    return get_bottle(bottle_id)


def update_bottle(bottle_id: str, data: dict) -> dict:
    fields: dict[str, str] = {}
    for key in UPDATABLE_FIELDS:
        if key not in data:
            continue
        if key == "shelf":
            value = _clean(data[key])
            if value not in config.SHELVES:
                raise ValueError("Invalid shelf.")
        elif key == "vintage":
            value = _clean_vintage(data[key])
        else:
            value = _clean(data[key])
        if key == "wine" and not value:
            raise ValueError("Wine name is required.")
        fields[key] = value

    if not fields:
        raise ValueError("No fields to update.")

    sets = ", ".join(f"{key} = ?" for key in fields)
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE bottles SET {sets} WHERE id = ?",
            (*fields.values(), bottle_id),
        )
        if cur.rowcount == 0:
            raise KeyError("Bottle not found.")
    return get_bottle(bottle_id)


def delete_bottle(bottle_id: str) -> None:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM bottles WHERE id = ?", (bottle_id,))
        if cur.rowcount == 0:
            raise KeyError("Bottle not found.")


def count_bottles() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM bottles").fetchone()
    return int(row["n"])
