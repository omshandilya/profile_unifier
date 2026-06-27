import asyncio
import logging
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger("effiflo-dev-unifier")

class DevToClient:
    def __init__(self):
        self.base_url = "https://dev.to/api"

    async def _request(self, path: str, params: Optional[dict] = None, is_list: bool = False) -> Any:
        url = f"{self.base_url}{path}"
        logger.info(f"→ GET {url}")

        async def do_request():
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params)
                return response

        try:
            res = await do_request()
        except httpx.HTTPError as e:
            logger.error(f"HTTP connection error during dev.to request to {url}: {str(e)}")
            res = None

        if res is not None and (res.status_code == 429 or res.status_code == 503):
            logger.warning(f"dev.to returned status {res.status_code}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
            try:
                res = await do_request()
            except httpx.HTTPError as e:
                logger.error(f"HTTP connection error during dev.to retry request to {url}: {str(e)}")
                res = None

        if res is None:
            return [] if is_list else {}

        if res.status_code == 404:
            return [] if is_list else {}

        res.raise_for_status()
        return res.json()

    async def get_user(self, username: str) -> dict:
        path = "/users/by_username"
        params = {"url": username}
        res = await self._request(path, params=params, is_list=False)
        return res if isinstance(res, dict) else {}

    async def get_articles(self, username: str) -> list[dict]:
        path = "/articles"
        params = {"username": username, "per_page": 10}
        res = await self._request(path, params=params, is_list=True)
        if isinstance(res, list):
            articles = []
            for item in res:
                if isinstance(item, dict):
                    articles.append({
                        "id": item.get("id"),
                        "title": item.get("title"),
                        "tag_list": item.get("tag_list"),
                        "published_at": item.get("published_at"),
                        "positive_reactions_count": item.get("positive_reactions_count"),
                        "reading_time_minutes": item.get("reading_time_minutes")
                    })
            return articles
        return []

    @staticmethod
    def extract_tags(articles: list[dict]) -> dict:
        tag_freq = {}
        for article in articles:
            tags = article.get("tag_list")
            # dev.to returns tags either as a list or a comma-separated string,
            # but the schema projection maps it to tag_list directly.
            if isinstance(tags, list):
                for tag in tags:
                    tag_str = str(tag).lower().strip()
                    if tag_str:
                        tag_freq[tag_str] = tag_freq.get(tag_str, 0) + 1
            elif isinstance(tags, str):
                # Fallback just in case it is a string
                for tag in tags.split(","):
                    tag_str = tag.lower().strip()
                    if tag_str:
                        tag_freq[tag_str] = tag_freq.get(tag_str, 0) + 1
        return tag_freq
