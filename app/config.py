"""Runtime configuration, all overridable via environment variables."""

import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


# llama.cpp server (OpenAI-compatible API)
LLAMA_SERVER_URL = os.environ.get("LLAMA_SERVER_URL", "http://192.168.1.132:8081").rstrip("/")
LLAMA_MODEL = os.environ.get("LLAMA_MODEL", "Qwen-3.8-27B-Q4")
LLM_TIMEOUT_SECONDS = _int("LLM_TIMEOUT_SECONDS", 600)
LLM_MAX_TOKENS = _int("LLM_MAX_TOKENS", 1024)
LLM_TEMPERATURE = _float("LLM_TEMPERATURE", 0.1)

# Storage
DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
DB_PATH = os.path.join(DATA_DIR, "inventory.db")

# Fridge shelves (comma-separated)
SHELVES = [
    s.strip()
    for s in os.environ.get(
        "SHELVES", "Shelf 1,Shelf 2,Shelf 3,Shelf 4,Shelf 5,Shelf 6,Shelf 7"
    ).split(",")
    if s.strip()
]

# Limits
MAX_IMAGE_BYTES = 8 * 1024 * 1024
