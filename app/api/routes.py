from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.enrichment.groq_client import GroqEnricher
from app.ingestion.devto import DevToClient
from app.ingestion.github import GitHubClient
from app.ingestion.hackernews import HackerNewsClient
from app.ingestion.stackoverflow import StackOverflowClient
from app.models.schemas import (
    HealthResponse,
    ProfileResponse,
    ProfileSource,
    ResolveRequest,
    ResolveResponse,
)
from app.observability.metrics import metrics
from app.resolution.resolver import EntityResolver
from app.storage.supabase_client import SupabaseStore

logger = logging.getLogger("effiflo-dev-unifier")
router = APIRouter()


@router.get("/")
async def root():
    return {"status": "healthy", "service": "Dev Profile Unifier"}


# ─────────────────────────────────────────────────────────────────────────────
# Helper: run one platform's ingestion, swallowing errors gracefully
# ─────────────────────────────────────────────────────────────────────────────

async def _ingest_github(username: Optional[str]) -> dict:
    if not username:
        return {}
    client = GitHubClient(settings)
    user = await client.get_user(username)
    repos = await client.get_repos(username)
    languages = await client.get_languages(username, repos)
    commits = await client.get_recent_commits(username)
    return {
        "user": user,
        "repos": repos,
        "languages": languages,
        "commits": commits,
        "github_repo_count": len(repos),
        "last_commit_date": (
            commits[0].get("commit", {}).get("author", {}).get("date")
            if commits else None
        ),
    }


async def _ingest_stackoverflow(query_name: str, user_id: Optional[str]) -> dict:
    client = StackOverflowClient(settings)
    # If a numeric ID was given use it directly, otherwise search by name
    if user_id and str(user_id).isdigit():
        user = await client.get_user(int(user_id))
        top_tags = await client.get_top_tags(int(user_id))
        top_answers = await client.get_top_answers(int(user_id))
    else:
        results = await client.search_user(query_name)
        if not results:
            return {}
        user = results[0]
        uid = user.get("user_id")
        if not uid:
            return {}
        top_tags = await client.get_top_tags(uid)
        top_answers = await client.get_top_answers(uid)
    return {
        "user": user,
        "top_tags": top_tags,
        "top_answers": top_answers,
        "stackoverflow_reputation": user.get("reputation", 0),
    }


async def _ingest_devto(devto_handle: Optional[str], query_name: str) -> dict:
    client = DevToClient(settings)
    handle = devto_handle or query_name
    user = await client.get_user(handle)
    articles = await client.get_articles(handle)
    tags = DevToClient.extract_tags(articles)
    return {
        "user": user,
        "articles": articles,
        "tags": tags,
        "devto_article_count": len(articles),
        "recent_article_titles": [a.get("title") for a in articles[:3] if a.get("title")],
    }


async def _ingest_hackernews(username: Optional[str]) -> dict:
    if not username:
        return {}
    client = HackerNewsClient(settings)
    user = await client.search_user(username)
    submissions = await client.get_submissions(username)
    comments = await client.get_comments(username)
    return {
        "user": user,
        "submissions": submissions,
        "comments": comments,
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /profiles/resolve
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/profiles/resolve", response_model=ResolveResponse)
async def resolve_profile(body: ResolveRequest) -> ResolveResponse:
    wall_start = time.monotonic()
    store = SupabaseStore()

    # 1. Create pending resolution_request row in Supabase
    request_id = await store.insert_resolution_request(body.model_dump())

    # 2. Unique ID grouping all raw rows from this ingestion run
    ingestion_run_id = str(uuid.uuid4())

    # 3. Concurrent ingestion with exception handling isolation
    results = await asyncio.gather(
        _ingest_github(body.github),
        _ingest_stackoverflow(body.name, body.stackoverflow),
        _ingest_devto(body.devto, body.name),
        _ingest_hackernews(body.hackernews),
        return_exceptions=True,
    )

    # Separate results and log any exceptions raised during ingestion
    gh_data = results[0] if not isinstance(results[0], Exception) else {}
    so_data = results[1] if not isinstance(results[1], Exception) else {}
    devto_data = results[2] if not isinstance(results[2], Exception) else {}
    hn_data = results[3] if not isinstance(results[3], Exception) else {}

    platform_names = ["GitHub", "StackOverflow", "dev.to", "HackerNews"]
    for idx, res in enumerate(results):
        if isinstance(res, Exception):
            logger.error(f"{platform_names[idx]} ingestion failed with error: {str(res)}")

    # 4. Persist raw profile data rows
    raw_ids: Dict[str, str] = {}
    source_map = {
        "github": (gh_data, body.github),
        "stackoverflow": (so_data, body.stackoverflow),
        "devto": (devto_data, body.devto),
        "hackernews": (hn_data, body.hackernews),
    }
    for source, (data, handle) in source_map.items():
        if data:
            source_user_id = str(
                (data.get("user") or {}).get("id")
                or (data.get("user") or {}).get("user_id")
                or (data.get("user") or {}).get("login")
                or (data.get("user") or {}).get("username")
                or handle
                or "unknown"
            )
            raw_id = await store.insert_raw_profile(
                source=source,
                source_user_id=source_user_id,
                username=handle,
                raw_data=data,
                ingestion_run_id=ingestion_run_id,
            )
            raw_ids[source] = raw_id

    # 5. Entity resolution
    search_query = {
        "name": body.name,
        "github": body.github,
        "stackoverflow": body.stackoverflow,
        "devto": body.devto,
        "hackernews": body.hackernews,
        "emailhint": body.emailhint,
    }
    resolver = EntityResolver(search_query)
    result = resolver.resolve(gh_data, so_data, devto_data, hn_data)

    # Enrich canonical profile with extra counts for the Gemini prompt
    merged = result.canonical_profile
    merged["github_repo_count"] = gh_data.get("github_repo_count", 0)
    merged["stackoverflow_reputation"] = so_data.get("stackoverflow_reputation", 0)
    merged["devto_article_count"] = devto_data.get("devto_article_count", 0)
    merged["recent_article_titles"] = devto_data.get("recent_article_titles", [])
    merged["last_commit_date"] = gh_data.get("last_commit_date")

    # 6. Insert canonical profile
    canonical_id = await store.insert_canonical_profile(
        {
            "display_name": merged.get("display_name"),
            "location": merged.get("location"),
            "bio": merged.get("bio"),
            "primary_email": merged.get("primary_email"),
            "merged_languages": merged.get("merged_languages"),
            "merged_tags": merged.get("merged_tags"),
            "resolution_confidence": result.confidence,
            "resolution_status": result.status,
        }
    )

    # 7. Insert profile_sources rows for each source with data
    for source, raw_id in raw_ids.items():
        per_conf = result.per_source_confidence.get(source, 0.0)
        await store.insert_profile_source(
            canonical_profile_id=canonical_id,
            raw_profile_id=raw_id,
            source=source,
            confidence_score=per_conf,
            signals_fired=result.signals_fired,
            resolution_method=result.resolution_method,
        )

    # 8. Groq enrichment
    enricher = GroqEnricher()
    llm_result = await enricher.generate_summary(merged)

    # 9. Update canonical profile with LLM output
    await store.update_canonical_profile(
        canonical_id,
        {
            "llm_summary": llm_result.get("summary"),
            "llm_tokens_used": llm_result.get("tokens_used", 0),
        },
    )

    # Measure final resolution time
    resolution_time_ms = int((time.monotonic() - wall_start) * 1000)

    # 10. Mark resolution_request complete
    api_calls_made = dict(metrics.total_api_calls)
    await store.update_resolution_request(
        request_id,
        {
            "canonical_profile_id": canonical_id,
            "status": "complete",
            "resolution_time_ms": resolution_time_ms,
            "api_calls_made": api_calls_made,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    # 11. In-memory metrics
    metrics.record_profile_resolved(resolution_time_ms)
    metrics.increment("resolve_requests")

    # Also log the API call to Supabase observability table
    await store.log_api_call(
        source="resolver",
        endpoint="/profiles/resolve",
        status_code=200,
        latency_ms=resolution_time_ms,
        tokens_used=llm_result.get("tokens_used", 0),
    )

    # 12. Response
    sources_found = [s for s, d in source_map.items() if d[0]]
    return ResolveResponse(
        profile_id=canonical_id,
        resolution_status=result.status,
        confidence=round(result.confidence, 4),
        sources_found=sources_found,
        message=(
            f"Profile resolved with {result.status} status "
            f"({round(result.confidence * 100, 1)}% confidence) "
            f"from {len(sources_found)} source(s). "
            f"Signals fired: {len(result.signals_fired)}."
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /profiles/{profile_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/profiles/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: str) -> ProfileResponse:
    metrics.increment("profile_lookups")
    store = SupabaseStore()

    # 1. Fetch canonical profile row joined with profile_sources and raw_profile_data via nested select
    profile = await store.get_canonical_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found.")

    # 2. Extract joined profile_sources data directly from the profile payload
    sources: List[ProfileSource] = []
    for ps in profile.get("profile_sources", []) or []:
        raw = ps.get("raw_profile_data") or {}
        signals = ps.get("signals_fired") or []
        if isinstance(signals, str):
            signals = [signals]
        
        sources.append(
            ProfileSource(
                source=ps.get("source", ""),
                confidence_score=ps.get("confidence_score", 0.0),
                signals_fired=signals,
                username=raw.get("username"),
                fetched_at=raw.get("fetched_at"),
            )
        )

    # 3. Return response
    return ProfileResponse(
        id=profile.get("id", profile_id),
        display_name=profile.get("display_name"),
        location=profile.get("location"),
        bio=profile.get("bio"),
        merged_languages=profile.get("merged_languages"),
        merged_tags=profile.get("merged_tags"),
        resolution_confidence=profile.get("resolution_confidence"),
        resolution_status=profile.get("resolution_status"),
        llm_summary=profile.get("llm_summary"),
        sources=sources,
        created_at=str(profile.get("created_at", "")),
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /health
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    # 1. DB-level observability stats
    store = SupabaseStore()
    db_summary = await store.get_observability_summary()

    # 2. In-memory metrics
    mem_summary = metrics.get_summary()

    # 3. Live GitHub rate-limit snapshot
    gh_rl: Dict[str, Any] = {}
    try:
        gh_client = GitHubClient(settings)
        rl_data = await gh_client.get_rate_limit()
        core = (rl_data.get("resources") or {}).get("core") or rl_data.get("rate") or {}
        gh_rl = {
            "remaining": core.get("remaining"),
            "total": core.get("limit"),
            "reset_at": (
                datetime.fromtimestamp(core["reset"], tz=timezone.utc).isoformat()
                if core.get("reset") else None
            ),
        }
    except Exception as exc:
        logger.warning(f"Could not fetch GitHub rate limit: {exc}")
        # Fall back to the cached in-memory snapshot
        gh_rl = mem_summary.get("github_rate_limit") or {}

    from app.models.schemas import GitHubRateLimitHealth

    return HealthResponse(
        status="healthy",
        environment=settings.ENVIRONMENT,
        github_rate_limit=GitHubRateLimitHealth(**gh_rl) if gh_rl else None,
        api_calls_by_source=mem_summary.get("api_calls_by_source", {}),
        total_profiles_resolved=mem_summary.get("total_profiles_resolved", 0),
        average_resolution_time_ms=mem_summary.get("average_resolution_time_ms", 0.0),
        llm_tokens_used=mem_summary.get("llm_tokens_used", 0),
        estimated_llm_cost_usd=mem_summary.get("estimated_llm_cost_usd", 0.0),
        db_summary=db_summary,
    )
