import asyncio
import logging
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger("effiflo-dev-unifier")

class StackOverflowClient:
    def __init__(self, stackoverflow_key: Optional[str] = None):
        self.key = stackoverflow_key
        self.base_url = "https://api.stackexchange.com/2.3"

    async def _request(self, path: str, params: Optional[dict] = None, is_list: bool = False) -> Any:
        url = f"{self.base_url}{path}"
        req_params = {
            "site": "stackoverflow"
        }
        if self.key:
            req_params["key"] = self.key
        if params:
            req_params.update(params)

        logger.info(f"→ GET {url}")

        async def do_request():
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=req_params)
                return response

        try:
            res = await do_request()
        except httpx.HTTPError as e:
            logger.error(f"HTTP connection error during StackOverflow request to {url}: {str(e)}")
            res = None

        if res is not None and (res.status_code == 429 or res.status_code == 503):
            logger.warning(f"StackOverflow returned status {res.status_code}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
            try:
                res = await do_request()
            except httpx.HTTPError as e:
                logger.error(f"HTTP connection error during StackOverflow retry request to {url}: {str(e)}")
                res = None

        if res is None:
            return [] if is_list else {}

        if res.status_code == 404:
            return [] if is_list else {}

        res.raise_for_status()
        data = res.json()

        # Handle quota_remaining warning
        if isinstance(data, dict):
            quota_remaining = data.get("quota_remaining")
            if quota_remaining is not None and quota_remaining < 5:
                logger.warning(f"StackExchange quota remaining is low: {quota_remaining}")

        return data

    async def search_user(self, name: str) -> list[dict]:
        path = "/users"
        params = {
            "inname": name,
            "order": "desc",
            "sort": "reputation",
            "pagesize": 5
        }
        res = await self._request(path, params=params, is_list=False)
        if isinstance(res, dict) and "items" in res:
            items = res["items"]
            if isinstance(items, list):
                users = []
                for item in items:
                    users.append({
                        "user_id": item.get("user_id"),
                        "display_name": item.get("display_name"),
                        "reputation": item.get("reputation"),
                        "location": item.get("location"),
                        "website_url": item.get("website_url"),
                        "link": item.get("link"),
                        "profile_image": item.get("profile_image"),
                        "top_answers": item.get("top_answers", []),
                        "top_questions": item.get("top_questions", [])
                    })
                return users
        return []

    async def get_user(self, user_id: int) -> dict:
        path = f"/users/{user_id}"
        res = await self._request(path, is_list=False)
        if isinstance(res, dict) and "items" in res:
            items = res["items"]
            if isinstance(items, list) and len(items) > 0:
                return items[0]
        return {}

    async def get_top_tags(self, user_id: int) -> list[dict]:
        path = f"/users/{user_id}/top-answer-tags"
        params = {"pagesize": 10}
        res = await self._request(path, params=params, is_list=False)
        if isinstance(res, dict) and "items" in res:
            items = res["items"]
            if isinstance(items, list):
                return [{"tag_name": item.get("tag_name"), "answer_count": item.get("answer_count")} for item in items]
        return []

    async def get_top_answers(self, user_id: int) -> list[dict]:
        path = f"/users/{user_id}/answers"
        params = {
            "order": "desc",
            "sort": "votes",
            "pagesize": 5,
            "filter": "withbody"
        }
        res = await self._request(path, params=params, is_list=False)
        if isinstance(res, dict) and "items" in res:
            items = res["items"]
            return items if isinstance(items, list) else []
        return []
