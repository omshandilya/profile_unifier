import httpx
from typing import Dict, Any, Optional
from app.config import settings

class StackOverflowClient:
    def __init__(self):
        self.key = settings.STACKOVERFLOW_KEY
        self.base_url = "https://api.stackexchange.com/2.3"

    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        params = {
            "site": "stackoverflow"
        }
        if self.key:
            params["key"] = self.key
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/users/{user_id}", params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get("items"):
                    return data["items"][0]
            return None
