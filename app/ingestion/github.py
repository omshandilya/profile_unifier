import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.observability.metrics import metrics

logger = logging.getLogger("effiflo-dev-unifier")

SOURCE = "github"


class GitHubClient:
    def __init__(self, github_token: Optional[str] = None):
        self.token = github_token
        self.headers: Dict[str, str] = {}
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
        self.headers["Accept"] = "application/vnd.github.v3+json"
        self.base_url = "https://api.github.com"

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    async def _request(
        self,
        url: str,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        is_list: bool = False,
    ) -> Any:
        req_headers = {**self.headers, **(headers or {})}
        logger.info(f"→ GET {url}")

        async def do_request() -> httpx.Response:
            async with httpx.AsyncClient() as client:
                return await client.get(url, headers=req_headers, params=params)

        t0 = time.monotonic()
        try:
            res = await do_request()
        except httpx.HTTPError as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            metrics.record_api_call(SOURCE, latency_ms)
            logger.error(f"GitHub connection error {url}: {exc}")
            return [] if is_list else {}

        latency_ms = int((time.monotonic() - t0) * 1000)
        metrics.record_api_call(SOURCE, latency_ms)

        # --- Rate-limit housekeeping ---
        remaining = res.headers.get("X-RateLimit-Remaining")
        limit = res.headers.get("X-RateLimit-Limit")
        reset = res.headers.get("X-RateLimit-Reset")

        try:
            if remaining is not None and limit is not None and reset is not None:
                metrics.update_github_rate_limit(
                    remaining=int(remaining),
                    limit=int(limit),
                    reset_time=int(reset),
                )
            if remaining is not None and int(remaining) < 10 and reset is not None:
                sleep_for = max(0.0, float(reset) - time.time())
                if sleep_for > 0:
                    logger.warning(
                        f"GitHub rate limit remaining ({remaining}) < 10. "
                        f"Sleeping {sleep_for:.1f}s."
                    )
                    await asyncio.sleep(sleep_for)
        except ValueError:
            pass

        # --- 429 / 503 retry once ---
        if res.status_code in (429, 503):
            logger.warning(f"GitHub {res.status_code} — retrying in 5 s…")
            await asyncio.sleep(5)
            t0 = time.monotonic()
            try:
                res = await do_request()
            except httpx.HTTPError as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                metrics.record_api_call(SOURCE, latency_ms)
                logger.error(f"GitHub retry connection error {url}: {exc}")
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
        url = f"{self.base_url}/users/{username}"
        res = await self._request(url, is_list=False)
        return res if isinstance(res, dict) else {}

    async def get_repos(self, username: str) -> List[dict]:
        url = f"{self.base_url}/users/{username}/repos"
        params = {"per_page": 100, "sort": "updated"}
        res = await self._request(url, params=params, is_list=True)
        return res if isinstance(res, list) else []

    async def get_languages(self, username: str, repos: List[dict]) -> dict:
        """Merge language byte-counts across first 20 repos."""
        merged: Dict[str, int] = {}
        for repo in repos[:20]:
            repo_name = repo.get("name")
            if not repo_name:
                continue
            url = f"{self.base_url}/repos/{username}/{repo_name}/languages"
            lang_data = await self._request(url, is_list=False)
            if isinstance(lang_data, dict):
                for lang, count in lang_data.items():
                    merged[lang] = merged.get(lang, 0) + count
        return merged

    async def get_recent_commits(self, username: str) -> List[dict]:
        url = f"{self.base_url}/search/commits"
        headers = {"Accept": "application/vnd.github.cloak-preview"}
        params = {"q": f"author:{username}", "sort": "author-date", "per_page": 10}
        res = await self._request(url, headers=headers, params=params, is_list=False)
        if isinstance(res, dict):
            items = res.get("items")
            return items if isinstance(items, list) else []
        return []

    async def get_rate_limit(self) -> dict:
        url = f"{self.base_url}/rate_limit"
        res = await self._request(url, is_list=False)
        return res if isinstance(res, dict) else {}
