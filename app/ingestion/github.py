import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger("effiflo-dev-unifier")

class GitHubClient:
    def __init__(self, github_token: Optional[str] = None):
        self.token = github_token
        self.headers = {}
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
        self.headers["Accept"] = "application/vnd.github.v3+json"
        self.base_url = "https://api.github.com"

    async def _request(self, url: str, headers: Optional[dict] = None, params: Optional[dict] = None, is_list: bool = False) -> Any:
        req_headers = {**self.headers, **(headers or {})}
        logger.info(f"→ GET {url}")
        
        async def do_request():
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=req_headers, params=params)
                
                # Check rate limit headers
                remaining = response.headers.get("X-RateLimit-Remaining")
                reset = response.headers.get("X-RateLimit-Reset")
                if remaining is not None:
                    try:
                        rem_val = int(remaining)
                        if rem_val < 10 and reset is not None:
                            reset_time = float(reset)
                            sleep_duration = max(0.0, reset_time - time.time())
                            if sleep_duration > 0:
                                logger.warning(f"GitHub Rate limit remaining ({rem_val}) < 10. Sleeping for {sleep_duration:.2f} seconds.")
                                await asyncio.sleep(sleep_duration)
                    except ValueError:
                        pass
                return response

        try:
            res = await do_request()
        except httpx.HTTPError as e:
            logger.error(f"HTTP connection error during GitHub request to {url}: {str(e)}")
            res = None

        if res is not None and (res.status_code == 429 or res.status_code == 503):
            logger.warning(f"GitHub returned status {res.status_code}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
            try:
                res = await do_request()
            except httpx.HTTPError as e:
                logger.error(f"HTTP connection error during GitHub retry request to {url}: {str(e)}")
                res = None

        if res is None:
            return [] if is_list else {}

        if res.status_code == 404:
            return [] if is_list else {}

        res.raise_for_status()
        return res.json()

    async def get_user(self, username: str) -> dict:
        url = f"{self.base_url}/users/{username}"
        res = await self._request(url, is_list=False)
        return res if isinstance(res, dict) else {}

    async def get_repos(self, username: str) -> list[dict]:
        url = f"{self.base_url}/users/{username}/repos"
        params = {"per_page": 100, "sort": "updated"}
        res = await self._request(url, params=params, is_list=True)
        return res if isinstance(res, list) else []

    async def get_languages(self, username: str, repos: list[dict]) -> dict:
        merged_languages = {}
        # Limit to first 20 repos
        for repo in repos[:20]:
            repo_name = repo.get("name")
            if not repo_name:
                continue
            url = f"{self.base_url}/repos/{username}/{repo_name}/languages"
            lang_data = await self._request(url, is_list=False)
            if isinstance(lang_data, dict):
                for lang, bytes_count in lang_data.items():
                    merged_languages[lang] = merged_languages.get(lang, 0) + bytes_count
        return merged_languages

    async def get_recent_commits(self, username: str) -> list[dict]:
        url = f"{self.base_url}/search/commits"
        headers = {"Accept": "application/vnd.github.cloak-preview"}
        params = {"q": f"author:{username}", "sort": "author-date", "per_page": 10}
        res = await self._request(url, headers=headers, params=params, is_list=False)
        if isinstance(res, dict) and "items" in res:
            items = res["items"]
            return items if isinstance(items, list) else []
        return []

    async def get_rate_limit(self) -> dict:
        url = f"{self.base_url}/rate_limit"
        res = await self._request(url, is_list=False)
        return res if isinstance(res, dict) else {}
