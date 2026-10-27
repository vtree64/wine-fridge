#!/usr/bin/env python3
"""One-time import of the old Google Sheet export (Wine Inventory.xlsx)
into the Vinotag SQLite database.

Usage (from the project folder, on the host):
    docker compose run --rm wine-fridge python import_xlsx.py

Or point it at a specific file:
    docker compose run --rm wine-fridge python import_xlsx.py /app/seed/Wine\\ Inventory.xlsx

The import is idempotent: bottles whose Bottle ID already exists are skipped.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.importer import import_from_xlsx  # noqa: E402

DEFAULT_XLSX = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "seed", "Wine Inventory.xlsx"
)


def main() -> int:
    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_XLSX
    if not os.path.exists(xlsx_path):
        print(f"Spreadsheet not found: {xlsx_path}")
        return 1

    added, skipped, total = import_from_xlsx(xlsx_path)
    print(f"Import complete: {added} added, {skipped} skipped. Total in database: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
