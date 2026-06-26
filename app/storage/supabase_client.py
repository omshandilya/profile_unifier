from supabase import create_client, Client
from typing import Optional
from app.config import settings

class SupabaseStorage:
    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.key = settings.SUPABASE_SERVICE_KEY
        self.client: Optional[Client] = None
        if self.url and self.key:
            self.client = create_client(self.url, self.key)

    async def save_profile(self, profile: dict) -> bool:
        if not self.client:
            return False
        # Stub for saving to database
        # self.client.table("profiles").upsert(profile).execute()
        return True
