import asyncio
import logging
from typing import Dict, Any, Optional, List
from supabase import create_client
from app.config import settings

logger = logging.getLogger("effiflo-dev-unifier")

# Initialise Supabase Client synchronously as requested
client = None
if settings.supabase_url and settings.supabase_service_key:
    try:
        client = create_client(settings.supabase_url, settings.supabase_service_key)
    except Exception as e:
        logger.error(f"Failed to initialise Supabase Client: {str(e)}")


class SupabaseStore:
    def __init__(self):
        pass

    async def insert_raw_profile(
        self, source: str, source_user_id: str, username: Optional[str], raw_data: dict, ingestion_run_id: Optional[str]
    ) -> str:
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
        
        def run():
            return client.table("raw_profile_data").insert(data).execute()

        try:
            res = await asyncio.to_thread(run)
            if res.data and len(res.data) > 0:
                return res.data[0].get("id", "")
        except Exception as e:
            logger.error(f"Failed to insert raw profile to Supabase: {str(e)}")
        return ""

    async def insert_canonical_profile(self, data: dict) -> str:
        if not client:
            logger.warning("Bypassing insert_canonical_profile - client not initialized.")
            return "dummy-canonical-id"
        
        def run():
            return client.table("canonical_profiles").insert(data).execute()

        try:
            res = await asyncio.to_thread(run)
            if res.data and len(res.data) > 0:
                return res.data[0].get("id", "")
        except Exception as e:
            logger.error(f"Failed to insert canonical profile: {str(e)}")
        return ""

    async def update_canonical_profile(self, profile_id: str, data: dict):
        if not client:
            logger.warning("Bypassing update_canonical_profile - client not initialized.")
            return
        
        def run():
            return client.table("canonical_profiles").update(data).eq("id", profile_id).execute()

        try:
            await asyncio.to_thread(run)
        except Exception as e:
            logger.error(f"Failed to update canonical profile {profile_id}: {str(e)}")

    async def insert_profile_source(
        self, canonical_profile_id: str, raw_profile_id: str, source: str, confidence_score: float, signals_fired: Optional[list], resolution_method: str
    ):
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
        
        def run():
            return client.table("profile_sources").insert(data).execute()

        try:
            await asyncio.to_thread(run)
        except Exception as e:
            logger.error(f"Failed to insert profile source: {str(e)}")

    async def insert_resolution_request(self, input_query: dict) -> str:
        if not client:
            logger.warning("Bypassing insert_resolution_request - client not initialized.")
            return "dummy-request-id"
        
        data = {
            "input_query": input_query,
            "status": "pending"
        }
        
        def run():
            return client.table("resolution_requests").insert(data).execute()

        try:
            res = await asyncio.to_thread(run)
            if res.data and len(res.data) > 0:
                return res.data[0].get("id", "")
        except Exception as e:
            logger.error(f"Failed to insert resolution request: {str(e)}")
        return ""

    async def update_resolution_request(self, request_id: str, data: dict):
        if not client:
            logger.warning("Bypassing update_resolution_request - client not initialized.")
            return
        
        def run():
            return client.table("resolution_requests").update(data).eq("id", request_id).execute()

        try:
            await asyncio.to_thread(run)
        except Exception as e:
            logger.error(f"Failed to update resolution request {request_id}: {str(e)}")

    async def get_canonical_profile(self, profile_id: str) -> dict:
        """
        Fetches canonical profile and performs a nested select join of profile_sources and raw_profile_data in a single query.
        """
        if not client:
            logger.warning("Bypassing get_canonical_profile - client not initialized.")
            return {}
        
        def run():
            return client.table("canonical_profiles").select("*, profile_sources(*, raw_profile_data(*))").eq("id", profile_id).execute()

        try:
            res = await asyncio.to_thread(run)
            if res.data and len(res.data) > 0:
                return res.data[0]
        except Exception as e:
            logger.error(f"Failed to fetch canonical profile {profile_id}: {str(e)}")
        return {}

    async def log_api_call(self, source: str, endpoint: str, status_code: int, latency_ms: int, tokens_used: Optional[int] = None):
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
        
        def run():
            return client.table("observability_metrics").insert(data).execute()

        try:
            await asyncio.to_thread(run)
        except Exception as e:
            logger.error(f"Failed to log API call metrics: {str(e)}")

    async def get_observability_summary(self) -> dict:
        """
        Queries observability_metrics and aggregates:
        total calls by source, average latency per source, total LLM tokens, and canonical profile count.
        """
        if not client:
            return {
                "total_api_calls_by_source": {},
                "average_latency_by_source": {},
                "total_llm_tokens": 0,
                "profile_count": 0
            }
        
        try:
            # Query observability metrics
            def run_metrics():
                return client.table("observability_metrics").select("source, latency_ms, tokens_used").execute()
            
            # Query canonical profile counts
            def run_profiles():
                return client.table("canonical_profiles").select("id", count="exact").limit(1).execute()
            
            metrics_res, profiles_res = await asyncio.gather(
                asyncio.to_thread(run_metrics),
                asyncio.to_thread(run_profiles)
            )
            
            metrics_data = metrics_res.data or []
            profile_count = getattr(profiles_res, "count", 0) or len(profiles_res.data or [])
            
            total_calls = {}
            total_latency = {}
            total_llm_tokens = 0
            
            for item in metrics_data:
                src = item.get("source") or "unknown"
                latency = item.get("latency_ms") or 0
                tokens = item.get("tokens_used") or 0
                
                total_calls[src] = total_calls.get(src, 0) + 1
                total_latency[src] = total_latency.get(src, 0) + latency
                total_llm_tokens += tokens
                
            avg_latency = {}
            for src, count in total_calls.items():
                avg_latency[src] = round(total_latency[src] / count, 2)
                
            return {
                "total_api_calls_by_source": total_calls,
                "average_latency_by_source": avg_latency,
                "total_llm_tokens": total_llm_tokens,
                "profile_count": profile_count
            }
        except Exception as e:
            logger.error(f"Failed to retrieve observability metrics summary: {str(e)}")
            return {
                "total_api_calls_by_source": {},
                "average_latency_by_source": {},
                "total_llm_tokens": 0,
                "profile_count": 0
            }
