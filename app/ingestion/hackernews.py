import asyncio
import logging
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger("effiflo-dev-unifier")

class HackerNewsClient:
    def __init__(self):
        self.base_url = "https://hn.algolia.com/api/v1"

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
            logger.error(f"HTTP connection error during HackerNews request to {url}: {str(e)}")
            res = None

        if res is not None and (res.status_code == 429 or res.status_code == 503):
            logger.warning(f"HackerNews API returned status {res.status_code}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
            try:
                res = await do_request()
            except httpx.HTTPError as e:
                logger.error(f"HTTP connection error during HackerNews retry request to {url}: {str(e)}")
                res = None

        if res is None:
            return [] if is_list else {}

        if res.status_code == 404:
            return [] if is_list else {}

        res.raise_for_status()
        return res.json()

    async def search_user(self, username: str) -> dict:
        path = f"/users/{username}"
        res = await self._request(path, is_list=False)
        return res if isinstance(res, dict) else {}

    async def get_submissions(self, username: str) -> list[dict]:
        path = "/search"
        params = {
            "tags": f"author_{username},story",
            "hitsPerPage": 10
        }
        res = await self._request(path, params=params, is_list=False)
        if isinstance(res, dict) and "hits" in res:
            hits = res["hits"]
            if isinstance(hits, list):
                result = []
                for item in hits:
                    if isinstance(item, dict):
                        result.append({
                            "objectID": item.get("objectID"),
                            "title": item.get("title"),
                            "url": item.get("url"),
                            "points": item.get("points"),
                            "created_at": item.get("created_at")
                        })
                return result
        return []

    async def get_comments(self, username: str) -> list[dict]:
        path = "/search"
        params = {
            "tags": f"author_{username},comment",
            "hitsPerPage": 10
        }
        res = await self._request(path, params=params, is_list=False)
        if isinstance(res, dict) and "hits" in res:
            hits = res["hits"]
            if isinstance(hits, list):
                result = []
                for item in hits:
                    if isinstance(item, dict):
                        result.append({
                            "objectID": item.get("objectID"),
                            "comment_text": item.get("comment_text"),
                            "story_title": item.get("story_title"),
                            "points": item.get("points"),
                            "created_at": item.get("created_at")
                        })
                return result
        return []
