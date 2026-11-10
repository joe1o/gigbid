"""runs.py - live run viewer: Server-Sent Events stream + the events so far."""

import os

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from apps.api.deps import current_user
from apps.api.streaming import hub

router = APIRouter(prefix="/api", tags=["runs"])


def _own(thread_id: str, user: dict) -> None:
    """Thread ids contain the user id ('bid:<user>:<job>'), so users can only watch their own runs."""
    if thread_id.split(":")[1:2] != [user["user_id"]]:
        raise HTTPException(404, "run not found")


@router.get("/runs/{thread_id}/stream")
async def stream(thread_id: str, user=Depends(current_user)):
    """SSE: one JSON event per finished node, then 'interrupt' (waiting for you) or 'done'."""
    _own(thread_id, user)
    return EventSourceResponse(hub.stream(thread_id))


@router.get("/runs/{thread_id}/events")
async def events(thread_id: str, user=Depends(current_user)) -> dict:
    _own(thread_id, user)
    project = os.getenv("LANGSMITH_PROJECT", "gigbid")
    trace = (f"https://smith.langchain.com/projects?search={project}" if os.getenv("LANGSMITH_API_KEY") else None)
    return {"events": hub.events.get(thread_id, []), "trace_url": trace, "trace_filter": f"thread_id = {thread_id}"}
