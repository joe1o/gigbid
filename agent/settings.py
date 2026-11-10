"""
settings.py - loads agent/config.yaml and the .env file once, for the whole project.

In simple words: every part of GigBid asks this file "what are my settings?"
instead of having numbers or URLs typed into the code.
"""

import asyncio
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]      # the gigbid/ folder
load_dotenv(ROOT / ".env")                       # secrets (API keys) -> environment variables

# Windows only (local dev): the async Postgres driver needs the "selector" event loop,
# not Windows' default "proactor" loop. Linux (Render, CI) is unaffected.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

CONFIG: dict = yaml.safe_load((ROOT / "agent" / "config.yaml").read_text(encoding="utf-8"))
PROCESSED = ROOT / "data" / "processed"          # generated files (databases, logs), git-ignored
PROCESSED.mkdir(parents=True, exist_ok=True)


def marketplace_mode() -> str:
    """gigsim or upwork_live. The env variable wins over the config file."""
    return os.getenv("MARKETPLACE_MODE", CONFIG["marketplace"]["mode"])


def mcp_url(server: str) -> str:
    """URL of one of our MCP servers, e.g. mcp_url('portfolio')."""
    return os.getenv(f"{server.upper()}_MCP_URL", CONFIG["mcp_servers"][server]["url"])
