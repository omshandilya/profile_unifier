import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.observability.metrics import metrics

logger = logging.getLogger("effiflo-dev-unifier")

SOURCE = "stackoverflow"


class StackOverflowClient:
    def __init__(self, stackoverflow_key: Optional[str] = None):
        self.key = stackoverflow_key
        self.base_url = "https://api.stackexchange.com/2.3"

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
        req_params: Dict[str, Any] = {"site": "stackoverflow"}
        if self.key:
            req_params["key"] = self.key
        if params:
            req_params.update(params)

        logger.info(f"→ GET {url}")

        async def do_request() -> httpx.Response:
            async with httpx.AsyncClient() as client:
                return await client.get(url, params=req_params)

        t0 = time.monotonic()
        try:
            res = await do_request()
        except httpx.HTTPError as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            metrics.record_api_call(SOURCE, latency_ms)
            logger.error(f"StackOverflow connection error {url}: {exc}")
            return [] if is_list else {}

        latency_ms = int((time.monotonic() - t0) * 1000)
        metrics.record_api_call(SOURCE, latency_ms)

        # --- 429 / 503 retry once ---
        if res.status_code in (429, 503):
            logger.warning(f"StackOverflow {res.status_code} — retrying in 5 s…")
            await asyncio.sleep(5)
            t0 = time.monotonic()
            try:
                res = await do_request()
            except httpx.HTTPError as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                metrics.record_api_call(SOURCE, latency_ms)
                logger.error(f"StackOverflow retry error {url}: {exc}")
                return [] if is_list else {}
            latency_ms = int((time.monotonic() - t0) * 1000)
            metrics.record_api_call(SOURCE, latency_ms)

        if res.status_code == 404:
            return [] if is_list else {}

        res.raise_for_status()
        data = res.json()

        # Quota warning from StackExchange response body
        if isinstance(data, dict):
            quota = data.get("quota_remaining")
            if quota is not None and quota < 5:
                logger.warning(f"StackExchange quota remaining is very low: {quota}")

        return data

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def search_user(self, name: str) -> List[dict]:
        params = {
            "inname": name,
            "order": "desc",
            "sort": "reputation",
            "pagesize": 5,
        }
        data = await self._request("/users", params=params)
        items = data.get("items", []) if isinstance(data, dict) else []
        return [
            {
                "user_id": u.get("user_id"),
                "display_name": u.get("display_name"),
                "reputation": u.get("reputation"),
                "location": u.get("location"),
                "website_url": u.get("website_url"),
                "link": u.get("link"),
                "profile_image": u.get("profile_image"),
                "top_answers": u.get("top_answers", []),
                "top_questions": u.get("top_questions", []),
            }
            for u in items
        ]

    async def get_user(self, user_id: int) -> dict:
        data = await self._request(f"/users/{user_id}")
        if isinstance(data, dict):
            items = data.get("items", [])
            if items:
                return items[0]
        return {}

    async def get_top_tags(self, user_id: int) -> List[dict]:
        data = await self._request(
            f"/users/{user_id}/top-answer-tags", params={"pagesize": 10}
        )
        items = data.get("items", []) if isinstance(data, dict) else []
        return [
            {"tag_name": t.get("tag_name"), "answer_count": t.get("answer_count")}
            for t in items
        ]

    async def get_top_answers(self, user_id: int) -> List[dict]:
        params = {"order": "desc", "sort": "votes", "pagesize": 5, "filter": "withbody"}
        data = await self._request(f"/users/{user_id}/answers", params=params)
        items = data.get("items", []) if isinstance(data, dict) else []
        return items if isinstance(items, list) else []
