import httpx
from typing import Dict, Any, Optional

class DevToClient:
    def __init__(self):
        self.base_url = "https://dev.to/api"

    async def get_user_profile(self, username: str) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/users/by_username", params={"username": username})
            if response.status_code == 200:
                return response.json()
            return None
