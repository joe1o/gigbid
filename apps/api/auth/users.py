"""
users.py - user accounts, kept in the same database as everything else (the LangGraph store).

Every user's data lives under a namespace that starts with THEIR user id, e.g.
("jobs", user_id). Every query is scoped that way, so one user can never read another's
jobs, drafts or memories (multi-tenant isolation).
"""

import hashlib
import json
import os
import time

from agent.runtime import default_settings
from agent.settings import CONFIG, ROOT
from apps.api.auth.security import check_password, encrypt, hash_password

USERS = ("users",)
PERSONAS = ["ml_engineer", "web_developer", "data_analyst"]


def user_id_for(email: str) -> str:
    return "u_" + hashlib.sha1(email.strip().lower().encode()).hexdigest()[:12]


async def get_user(store, user_id: str) -> dict | None:
    item = await store.aget(USERS, user_id)
    return {"user_id": user_id, **item.value} if item else None


async def create_user(store, email: str, password: str) -> dict:
    uid = user_id_for(email)
    await store.aput(USERS, uid, {"email": email.strip().lower(), "password_hash": hash_password(password),
                                  "created_at": time.time(), "onboarded": False, "settings": {}, "accounts": {}})
    return await get_user(store, uid)


async def authenticate(store, email: str, password: str) -> dict | None:
    user = await get_user(store, user_id_for(email))
    return user if user and check_password(password, user["password_hash"]) else None


async def save_user(store, user: dict) -> dict:
    value = {k: v for k, v in user.items() if k != "user_id"}
    await store.aput(USERS, user["user_id"], value)
    return user


def settings_for_persona(persona: str) -> dict:
    return default_settings(persona)


async def connect_gigsim(store, user: dict, account: str) -> dict:
    """'Connect' a GigSim account: store its credential ENCRYPTED in the user record."""
    token = CONFIG["marketplace"]["dev_accounts"][account]
    user["accounts"]["gigsim"] = {"account": account, "token": encrypt(token), "connected_at": time.time()}
    user["settings"]["account"] = account
    return await save_user(store, user)


def own_portfolio_path(user_id: str):
    return ROOT / "data" / "processed" / "portfolios" / user_id / "portfolio.json"


def start_own_portfolio(user: dict, base_persona: str | None) -> str:
    """Give the user a private, editable portfolio (a copy of a persona's, or empty)."""
    path = own_portfolio_path(user["user_id"])
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        if base_persona:
            data = json.loads((ROOT / "data" / "personas" / base_persona / "portfolio.json").read_text(encoding="utf-8"))
        else:
            data = {"name": user["email"].split("@")[0], "headline": "Freelancer", "category": "ml",
                    "hourly_floor_usd": 25, "fixed_floor_usd": 200, "items": []}
        data["persona_id"] = user["user_id"]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return user["user_id"]


async def ensure_reviewer(store) -> None:
    """Preload the reviewer login with a persona (password comes from the environment, never the repo)."""
    email = os.getenv("REVIEWER_EMAIL", "reviewer@gigbid.app")
    password = os.getenv("REVIEWER_PASSWORD", "review-local-only")
    user = await get_user(store, user_id_for(email))
    if user:
        if os.getenv("REVIEWER_PASSWORD") and not check_password(password, user["password_hash"]):
            user["password_hash"] = hash_password(password)       # password rotated via the environment
            await save_user(store, user)
        return
    user = await create_user(store, email, password)
    user["settings"] = settings_for_persona("ml_engineer")
    if os.getenv("REVIEWER_SEARCH"):            # e.g. the browser tests use a narrower saved search
        user["settings"]["searches"] = [{"query": os.getenv("REVIEWER_SEARCH"), "category": "ml"}]
    user["onboarded"] = True
    await connect_gigsim(store, user, "ml_engineer")
