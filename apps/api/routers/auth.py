"""auth.py - sign up, sign in, onboarding, settings, connected accounts and portfolio."""

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from apps.api.auth import users as U
from apps.api.auth.security import SESSION_COOKIE, make_session
from apps.api.deps import current_user, get_rt
from apps.api.schemas.models import (
    LoginIn,
    OnboardIn,
    PortfolioItemIn,
    PortfolioOut,
    SettingsIn,
    SignupIn,
    UserOut,
)
from rag.corpus import load_portfolio

router = APIRouter(prefix="/api", tags=["auth"])


def user_out(user: dict) -> UserOut:
    g = user.get("accounts", {}).get("gigsim")
    return UserOut(user_id=user["user_id"], email=user["email"], onboarded=user.get("onboarded", False),
                   settings=user.get("settings") or None,
                   gigsim={"account": g["account"], "connected_at": g["connected_at"]} if g else None,
                   upwork_connected=bool(user.get("accounts", {}).get("upwork")))


def set_cookie(resp: Response, user_id: str) -> None:
    resp.set_cookie(SESSION_COOKIE, make_session(user_id), httponly=True, samesite="lax", max_age=7 * 86400)


@router.post("/auth/signup", response_model=UserOut)
async def signup(body: SignupIn, response: Response, rt=Depends(get_rt)):
    if await U.get_user(rt.store, U.user_id_for(body.email)):
        raise HTTPException(409, "an account with this email already exists")
    user = await U.create_user(rt.store, body.email, body.password)
    set_cookie(response, user["user_id"])
    return user_out(user)


@router.post("/auth/login", response_model=UserOut)
async def login(body: LoginIn, response: Response, rt=Depends(get_rt)):
    user = await U.authenticate(rt.store, body.email, body.password)
    if not user:
        raise HTTPException(401, "wrong email or password")
    set_cookie(response, user["user_id"])
    return user_out(user)


@router.post("/auth/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user=Depends(current_user)):
    return user_out(user)


@router.post("/onboarding", response_model=UserOut)
async def onboarding(body: OnboardIn, user=Depends(current_user), rt=Depends(get_rt)):
    """Pick a persona (or a private copy to edit), connect a GigSim account, set rates and budget."""
    settings = U.settings_for_persona(body.persona)
    if body.own_profile:
        settings["persona"] = U.start_own_portfolio(user, body.persona)
    settings.update(fixed_floor_usd=body.fixed_floor_usd, hourly_floor_usd=body.hourly_floor_usd,
                    connects_weekly_budget=body.connects_weekly_budget, autonomy=body.autonomy,
                    searches=[s.model_dump() for s in body.searches] or settings["searches"])
    user["settings"] = settings
    user["onboarded"] = True
    await U.connect_gigsim(rt.store, user, body.account)
    return user_out(user)


@router.put("/settings", response_model=UserOut)
async def update_settings(body: SettingsIn, user=Depends(current_user), rt=Depends(get_rt)):
    user["settings"] = {**user["settings"], **body.model_dump(), "searches": [s.model_dump() for s in body.searches]}
    await U.save_user(rt.store, user)
    return user_out(user)


@router.post("/accounts/upwork")
async def connect_upwork(user=Depends(current_user)) -> dict:
    """Live mode needs Upwork's OAuth 2.1 app credentials; not configured in this deployment."""
    raise HTTPException(501, "Upwork live mode is not configured here: it needs an Upwork account and OAuth app. "
                             "GigBid works against GigSim; see docs/TOOLS.md.")


@router.get("/portfolio", response_model=PortfolioOut)
async def portfolio(user=Depends(current_user)):
    persona = user["settings"]["persona"]
    p = load_portfolio(persona)
    return PortfolioOut(persona=persona, name=p["name"], headline=p["headline"],
                        editable=persona == user["user_id"], items=p["items"])


@router.post("/portfolio/items", response_model=PortfolioOut)
async def add_item(body: PortfolioItemIn, request: Request, user=Depends(current_user), rt=Depends(get_rt)):
    """Add your own work. The first upload creates a private copy of your portfolio; the search
    index re-embeds only the new chunks (incremental re-indexing)."""
    if user["settings"]["persona"] != user["user_id"]:
        user["settings"]["persona"] = U.start_own_portfolio(user, user["settings"]["persona"])
        await U.save_user(rt.store, user)
    path = U.own_portfolio_path(user["user_id"])
    data = json.loads(path.read_text(encoding="utf-8"))
    item = {"id": f"own-{int(time.time() * 1000)}", **body.model_dump(), "date": time.strftime("%Y-%m"),
            "client_industry": None}
    data["items"].append(item)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return await portfolio(user)
