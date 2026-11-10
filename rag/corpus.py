"""
corpus.py - loads a freelancer's portfolio (the "corpus" that RAG searches over).

By default it reads data/personas/<persona_id>/portfolio.json. Anyone using the
Portfolio MCP server for themselves can set PORTFOLIO_PATH to their own file
with the same format.
"""

import json
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def portfolio_path(persona_id: str) -> Path:
    custom = os.getenv("PORTFOLIO_PATH")
    if custom:
        return Path(custom)
    private = ROOT / "data" / "processed" / "portfolios" / persona_id / "portfolio.json"   # a user's own copy
    return private if private.exists() else ROOT / "data" / "personas" / persona_id / "portfolio.json"


def load_portfolio(persona_id: str) -> dict:
    """Return {'persona_id', 'name', 'headline', ..., 'items': [...]}. Re-read if the file changed."""
    path = portfolio_path(persona_id)
    if not path.exists():
        raise FileNotFoundError(f"no portfolio found for '{persona_id}' at {path}")
    return _read(str(path), path.stat().st_mtime_ns)


@lru_cache(maxsize=16)
def _read(path: str, mtime_ns: int) -> dict:
    """Cached by (path, modified-time): editing the file automatically invalidates the cache."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def items(persona_id: str) -> list[dict]:
    return load_portfolio(persona_id)["items"]


def get_item(persona_id: str, item_id: str) -> dict | None:
    return next((i for i in items(persona_id) if i["id"] == item_id), None)
