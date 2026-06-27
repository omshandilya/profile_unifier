import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.observability.metrics import metrics

logger = logging.getLogger("effiflo-dev-unifier")

SOURCE = "devto"


class DevToClient:
    def __init__(self):
        self.base_url = "https://dev.to/api"

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
            logger.error(f"dev.to connection error {url}: {exc}")
            return [] if is_list else {}

        latency_ms = int((time.monotonic() - t0) * 1000)
        metrics.record_api_call(SOURCE, latency_ms)

        # --- 429 / 503 retry once ---
        if res.status_code in (429, 503):
            logger.warning(f"dev.to {res.status_code} — retrying in 5 s…")
            await asyncio.sleep(5)
            t0 = time.monotonic()
            try:
                res = await do_request()
            except httpx.HTTPError as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                metrics.record_api_call(SOURCE, latency_ms)
                logger.error(f"dev.to retry error {url}: {exc}")
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

    async def get_user(self, username: str) -> dict:
        res = await self._request("/users/by_username", params={"url": username})
        return res if isinstance(res, dict) else {}

    async def get_articles(self, username: str) -> List[dict]:
        res = await self._request(
            "/articles", params={"username": username, "per_page": 10}, is_list=True
        )
        if not isinstance(res, list):
            return []
        return [
            {
                "id": a.get("id"),
                "title": a.get("title"),
                "tag_list": a.get("tag_list"),
                "published_at": a.get("published_at"),
                "positive_reactions_count": a.get("positive_reactions_count"),
                "reading_time_minutes": a.get("reading_time_minutes"),
            }
            for a in res
            if isinstance(a, dict)
        ]

    @staticmethod
    def extract_tags(articles: List[dict]) -> Dict[str, int]:
        """Count tag frequency across all articles."""
        tag_freq: Dict[str, int] = {}
        for article in articles:
            tags = article.get("tag_list")
            if isinstance(tags, list):
                for tag in tags:
                    key = str(tag).lower().strip()
                    if key:
                        tag_freq[key] = tag_freq.get(key, 0) + 1
            elif isinstance(tags, str):
                for tag in tags.split(","):
                    key = tag.lower().strip()
                    if key:
                        tag_freq[key] = tag_freq.get(key, 0) + 1
        return tag_freq
