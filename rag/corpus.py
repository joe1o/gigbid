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


@lru_cache(maxsize=16)
def load_portfolio(persona_id: str) -> dict:
    """Return {'persona_id', 'name', 'headline', ..., 'items': [...]}."""
    custom = os.getenv("PORTFOLIO_PATH")
    path = Path(custom) if custom else ROOT / "data" / "personas" / persona_id / "portfolio.json"
    if not path.exists():
        raise FileNotFoundError(f"no portfolio found for '{persona_id}' at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def items(persona_id: str) -> list[dict]:
    return load_portfolio(persona_id)["items"]


def get_item(persona_id: str, item_id: str) -> dict | None:
    return next((i for i in items(persona_id) if i["id"] == item_id), None)
