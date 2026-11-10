"""
gigsim.py - the adapter that plugs GigSim (our simulator) into the marketplace port.

It turns calls like `await adapter.get_job("job-001")` into HTTP requests to GigSim,
and handles a real platform's bad days:
    - timeouts            : give up on a call after N seconds
    - bounded retries     : retry 429 (too fast) and 5xx (server error) at most N times,
                            waiting longer each time (exponential backoff: 0.5s, 1s, 2s...)
    - clear failures      : if it still fails -> MarketplaceUnavailable (UI shows a banner)
Writes reuse the same Idempotency-Key on every retry, so a retry can never double-submit.
"""

import asyncio

import httpx

from agent.marketplace_port import MarketplaceError, MarketplaceUnavailable


class GigSimAdapter:
    def __init__(self, base_url: str, token: str, timeout: float = 10, max_retries: int = 3,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {token}"}
        self.timeout = timeout
        self.max_retries = max_retries
        self.transport = transport            # tests pass an in-process transport here

    async def _call(self, method: str, path: str, *, params=None, json=None, idem_key=None):
        headers = dict(self.headers)
        if idem_key:
            headers["Idempotency-Key"] = idem_key
        last_problem = "unknown"
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout,
                                             transport=self.transport) as http:
                    r = await http.request(method, path, params=params, json=json, headers=headers)
            except httpx.TransportError as e:            # connection refused, timeout, DNS...
                last_problem = f"cannot reach GigSim ({type(e).__name__})"
            else:
                if r.status_code < 400:
                    return r.json()
                if r.status_code == 429 or r.status_code >= 500:
                    last_problem = f"GigSim returned {r.status_code}"
                    if r.status_code == 429:               # respect the platform's Retry-After, capped
                        await asyncio.sleep(min(float(r.headers.get("Retry-After", 1)), 5))
                else:                                      # 4xx = our request was refused: don't retry
                    raise MarketplaceError(r.status_code, r.json().get("detail", r.text))
            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * 2 ** attempt)    # 0.5s, 1s, 2s ...
        raise MarketplaceUnavailable(last_problem)

    # --- read -----------------------------------------------------------------
    async def search_jobs(self, query="", category=None, posted_after=None, limit=20):
        params = {"q": query, "limit": limit}
        if category:
            params["category"] = category
        if posted_after:
            params["posted_after"] = posted_after
        return await self._call("GET", "/jobs", params=params)

    async def get_job(self, job_id):
        return await self._call("GET", f"/jobs/{job_id}")

    async def get_client_history(self, client_id):
        return await self._call("GET", f"/clients/{client_id}")

    async def get_connects_balance(self):
        return await self._call("GET", "/me/connects")

    async def get_policy(self):
        return await self._call("GET", "/policy")

    async def market_stats(self, category):
        return await self._call("GET", "/market/stats", params={"category": category})

    async def list_proposals(self):
        return await self._call("GET", "/proposals")

    async def list_threads(self):
        return await self._call("GET", "/threads")

    async def list_messages(self, thread_id):
        return await self._call("GET", f"/threads/{thread_id}/messages")

    # --- write ----------------------------------------------------------------
    async def preview_proposal(self, payload):
        return await self._call("POST", "/proposals", params={"dry_run": True}, json=payload)

    async def submit_proposal(self, payload, idempotency_key):
        return await self._call("POST", "/proposals", json=payload, idem_key=idempotency_key)

    async def send_message(self, thread_id, text, idempotency_key):
        return await self._call("POST", f"/threads/{thread_id}/messages", json={"text": text},
                                idem_key=idempotency_key)
