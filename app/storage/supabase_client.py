import asyncio
import logging
from typing import Dict, Any, Optional, List
from supabase import create_async_client, AsyncClient
from app.config import settings

logger = logging.getLogger("effiflo-dev-unifier")

class SupabaseStore:
    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.key = settings.SUPABASE_SERVICE_KEY
        self._client: Optional[AsyncClient] = None

    async def get_client(self) -> Optional[AsyncClient]:
        if self._client is None:
            if self.url and self.key:
                try:
                    self._client = await create_async_client(self.url, self.key)
                except Exception as e:
                    logger.error(f"Failed to initialize Supabase AsyncClient: {str(e)}")
            else:
                logger.warning("Supabase URL or Service Key is missing in configurations. DB store operations will be bypassed.")
        return self._client

    async def insert_raw_profile(
        self, source: str, source_user_id: str, username: Optional[str], raw_data: dict, ingestion_run_id: Optional[str]
    ) -> str:
        client = await self.get_client()
        if not client:
            logger.warning("Bypassing insert_raw_profile - client not initialized.")
            return "dummy-raw-id"
        
        data = {
            "source": source,
            "source_user_id": source_user_id,
            "username": username,
            "raw_data": raw_data,
            "ingestion_run_id": ingestion_run_id
        }
        try:
            res = await client.table("raw_profile_data").insert(data).execute()
            if res.data and len(res.data) > 0:
                return res.data[0].get("id", "")
        except Exception as e:
            logger.error(f"Failed to insert raw profile to Supabase: {str(e)}")
        return ""

    async def insert_canonical_profile(self, data: dict) -> str:
        client = await self.get_client()
        if not client:
            logger.warning("Bypassing insert_canonical_profile - client not initialized.")
            return "dummy-canonical-id"
        try:
            res = await client.table("canonical_profiles").insert(data).execute()
            if res.data and len(res.data) > 0:
                return res.data[0].get("id", "")
        except Exception as e:
            logger.error(f"Failed to insert canonical profile: {str(e)}")
        return ""

    async def update_canonical_profile(self, profile_id: str, data: dict):
        client = await self.get_client()
        if not client:
            logger.warning("Bypassing update_canonical_profile - client not initialized.")
            return
        try:
            await client.table("canonical_profiles").update(data).eq("id", profile_id).execute()
        except Exception as e:
            logger.error(f"Failed to update canonical profile {profile_id}: {str(e)}")

    async def insert_profile_source(
        self, canonical_profile_id: str, raw_profile_id: str, source: str, confidence_score: float, signals_fired: Optional[list], resolution_method: str
    ):
        client = await self.get_client()
        if not client:
            logger.warning("Bypassing insert_profile_source - client not initialized.")
            return
        data = {
            "canonical_profile_id": canonical_profile_id,
            "raw_profile_id": raw_profile_id,
            "source": source,
            "confidence_score": confidence_score,
            "signals_fired": signals_fired,
            "resolution_method": resolution_method
        }
        try:
            await client.table("profile_sources").insert(data).execute()
        except Exception as e:
            logger.error(f"Failed to insert profile source: {str(e)}")

    async def insert_resolution_request(self, input_query: dict) -> str:
        client = await self.get_client()
        if not client:
            logger.warning("Bypassing insert_resolution_request - client not initialized.")
            return "dummy-request-id"
        data = {
            "input_query": input_query,
            "status": "pending"
        }
        try:
            res = await client.table("resolution_requests").insert(data).execute()
            if res.data and len(res.data) > 0:
                return res.data[0].get("id", "")
        except Exception as e:
            logger.error(f"Failed to insert resolution request: {str(e)}")
        return ""

    async def update_resolution_request(self, request_id: str, data: dict):
        client = await self.get_client()
        if not client:
            logger.warning("Bypassing update_resolution_request - client not initialized.")
            return
        try:
            await client.table("resolution_requests").update(data).eq("id", request_id).execute()
        except Exception as e:
            logger.error(f"Failed to update resolution request {request_id}: {str(e)}")

    async def get_canonical_profile(self, profile_id: str) -> dict:
        client = await self.get_client()
        if not client:
            logger.warning("Bypassing get_canonical_profile - client not initialized.")
            return {}
        try:
            res = await client.table("canonical_profiles").select("*").eq("id", profile_id).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
        except Exception as e:
            logger.error(f"Failed to fetch canonical profile {profile_id}: {str(e)}")
        return {}

    async def log_api_call(self, source: str, endpoint: str, status_code: int, latency_ms: int, tokens_used: Optional[int] = None):
        client = await self.get_client()
        if not client:
            logger.warning("Bypassing log_api_call - client not initialized.")
            return
        data = {
            "source": source,
            "endpoint": endpoint,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "tokens_used": tokens_used
        }
        try:
            await client.table("observability_metrics").insert(data).execute()
        except Exception as e:
            logger.error(f"Failed to log API call metrics: {str(e)}")

    async def get_observability_summary(self) -> dict:
        client = await self.get_client()
        if not client:
            return {
                "total_api_calls": 0,
                "average_latency_ms": 0.0,
                "error_count": 0,
                "total_llm_tokens_used": 0
            }
        
        try:
            res = await client.table("observability_metrics").select("status_code, latency_ms, tokens_used").order("called_at", desc=True).limit(1000).execute()
            metrics = res.data or []
            total_calls = len(metrics)
            if total_calls == 0:
                return {
                    "total_api_calls": 0,
                    "average_latency_ms": 0.0,
                    "error_count": 0,
                    "total_llm_tokens_used": 0
                }
                
            sum_latency = 0
            error_count = 0
            total_tokens = 0
            
            for item in metrics:
                sum_latency += item.get("latency_ms") or 0
                status = item.get("status_code")
                if status is None or status >= 400:
                    error_count += 1
                total_tokens += item.get("tokens_used") or 0
                
            return {
                "total_api_calls": total_calls,
                "average_latency_ms": round(sum_latency / total_calls, 2),
                "error_count": error_count,
                "total_llm_tokens_used": total_tokens
            }
        except Exception as e:
            logger.error(f"Failed to retrieve observability metrics summary: {str(e)}")
            return {
                "total_api_calls": 0,
                "average_latency_ms": 0.0,
                "error_count": 0,
                "total_llm_tokens_used": 0
            }
