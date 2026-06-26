import httpx
from typing import Dict, Any, Optional

class HackerNewsClient:
    def __init__(self):
        self.base_url = "https://hn.algolia.com/api/v1"

    async def get_user_profile(self, username: str) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/users/{username}")
            if response.status_code == 200:
                return response.json()
            return None
