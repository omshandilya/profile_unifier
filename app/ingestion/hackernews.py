import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
import httpx
from app.observability.metrics import metrics

logger = logging.getLogger("effiflo-dev-unifier")

SOURCE = "hackernews"


class HackerNewsClient:
    def __init__(self, settings: Any = None):
        self.settings = settings
        self.base_url = "https://hn.algolia.com/api/v1"

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    async def _request(
        self,
        path: str,
        params: Optional[dict] = None,
        is_list: bool = False,
    ) -> Any:
        url = f"{self.base_url}{path}"
        logger.info(f"→ GET {url}")

        async def do_request() -> httpx.Response:
            async with httpx.AsyncClient() as client:
                return await client.get(url, params=params)

        t0 = time.monotonic()
        try:
            res = await do_request()
        except httpx.HTTPError as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            metrics.record_api_call(SOURCE, latency_ms)
            logger.error(f"HackerNews connection error {url}: {exc}")
            return [] if is_list else {}

        latency_ms = int((time.monotonic() - t0) * 1000)
        metrics.record_api_call(SOURCE, latency_ms)

        # --- 429 / 503 retry once ---
        if res.status_code in (429, 503):
            logger.warning(f"HackerNews {res.status_code} — retrying in 5 s…")
            await asyncio.sleep(5)
            t0 = time.monotonic()
            try:
                res = await do_request()
            except httpx.HTTPError as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                metrics.record_api_call(SOURCE, latency_ms)
                logger.error(f"HackerNews retry error {url}: {exc}")
                return [] if is_list else {}
            latency_ms = int((time.monotonic() - t0) * 1000)
            metrics.record_api_call(SOURCE, latency_ms)

        if res.status_code == 404:
            return [] if is_list else {}

        res.raise_for_status()
        return res.json()

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def search_user(self, username: str) -> dict:
        res = await self._request(f"/users/{username}", is_list=False)
        return res if isinstance(res, dict) else {}

    async def get_submissions(self, username: str) -> List[dict]:
        params = {"tags": f"author_{username},story", "hitsPerPage": 10}
        res = await self._request("/search", params=params)
        hits = res.get("hits", []) if isinstance(res, dict) else []
        return [
            {
                "objectID": h.get("objectID"),
                "title": h.get("title"),
                "url": h.get("url"),
                "points": h.get("points"),
                "created_at": h.get("created_at"),
            }
            for h in hits
            if isinstance(h, dict)
        ]

    async def get_comments(self, username: str) -> List[dict]:
        params = {"tags": f"author_{username},comment", "hitsPerPage": 10}
        res = await self._request("/search", params=params)
        hits = res.get("hits", []) if isinstance(res, dict) else []
        return [
            {
                "objectID": h.get("objectID"),
                "comment_text": h.get("comment_text"),
                "story_title": h.get("story_title"),
                "points": h.get("points"),
                "created_at": h.get("created_at"),
            }
            for h in hits
            if isinstance(h, dict)
        ]
