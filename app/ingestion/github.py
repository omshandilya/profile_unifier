import httpx
from typing import Dict, Any, Optional
from app.config import settings

class GitHubClient:
    def __init__(self):
        self.token = settings.GITHUB_TOKEN
        self.headers = {}
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
        self.headers["Accept"] = "application/vnd.github.v3+json"
        self.base_url = "https://api.github.com"

    async def get_user_profile(self, username: str) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient(headers=self.headers) as client:
            response = await client.get(f"{self.base_url}/users/{username}")
            if response.status_code == 200:
                return response.json()
            return None
