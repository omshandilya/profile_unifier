import pytest
from app.storage.supabase_client import SupabaseStore, client

@pytest.mark.asyncio
async def test_supabase_store_fallback():
    # Since credentials are not set in testing environment, client should be None
    assert client is None
    
    store = SupabaseStore()
    
    # Assert fallback dummy values
    raw_id = await store.insert_raw_profile("github", "123", "octocat", {}, None)
    assert raw_id == "dummy-raw-id"
    
    canonical_id = await store.insert_canonical_profile({})
    assert canonical_id == "dummy-canonical-id"
    
    request_id = await store.insert_resolution_request({})
    assert request_id == "dummy-request-id"
    
    profile = await store.get_canonical_profile("some-id")
    assert profile == {}
    
    summary = await store.get_observability_summary()
    assert summary["total_api_calls_by_source"] == {}
    assert summary["profile_count"] == 0
