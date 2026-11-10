"""deps.py - shared FastAPI dependencies: the runtime and the logged-in user."""

from fastapi import HTTPException, Request

from apps.api.auth.security import SESSION_COOKIE, read_session
from apps.api.auth.users import get_user


def get_rt(request: Request):
    return request.app.state.rt


async def current_user(request: Request) -> dict:
    """The logged-in user (from the session cookie or an 'Authorization: Bearer' header), or 401."""
    token = request.cookies.get(SESSION_COOKIE) or request.headers.get("authorization", "").removeprefix("Bearer ")
    uid = read_session(token)
    user = await get_user(request.app.state.rt.store, uid) if uid else None
    if not user:
        raise HTTPException(401, "not signed in")
    return user


async def onboarded_user(request: Request) -> dict:
    user = await current_user(request)
    if not user.get("onboarded"):
        raise HTTPException(409, "finish onboarding first")
    return user
