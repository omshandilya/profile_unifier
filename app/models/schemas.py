from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
#  POST /profiles/resolve
# ─────────────────────────────────────────────

class ResolveRequest(BaseModel):
    name: str = Field(..., description="Full name or alias to search for")
    github: Optional[str] = Field(None, description="GitHub username")
    stackoverflow: Optional[str] = Field(None, description="Stack Overflow user ID or username")
    devto: Optional[str] = Field(None, description="dev.to username")
    hackernews: Optional[str] = Field(None, description="Hacker News username")
    emailhint: Optional[str] = Field(None, description="Known email to assist matching")


class ResolveResponse(BaseModel):
    profile_id: str
    resolution_status: str          # resolved | ambiguous | unresolved
    confidence: float
    sources_found: List[str]
    message: str


# ─────────────────────────────────────────────
#  GET /profiles/{profile_id}
# ─────────────────────────────────────────────

class ProfileSource(BaseModel):
    source: str
    confidence_score: float
    signals_fired: List[str]
    username: Optional[str]
    fetched_at: Optional[str]


class ProfileResponse(BaseModel):
    id: str
    display_name: Optional[str]
    location: Optional[str]
    bio: Optional[str]
    merged_languages: Optional[Dict[str, Any]]
    merged_tags: Optional[Any]          # list or dict depending on resolution path
    resolution_confidence: Optional[float]
    resolution_status: Optional[str]
    llm_summary: Optional[str]
    sources: List[ProfileSource]
    created_at: Optional[str]


# ─────────────────────────────────────────────
#  GET /health
# ─────────────────────────────────────────────

class GitHubRateLimitHealth(BaseModel):
    remaining: Optional[int]
    total: Optional[int]
    reset_at: Optional[str]


class HealthResponse(BaseModel):
    status: str
    environment: str
    github_rate_limit: Optional[GitHubRateLimitHealth]
    api_calls_by_source: Dict[str, Any]
    total_profiles_resolved: int
    average_resolution_time_ms: float
    total_llm_tokens: int
    estimated_llm_cost_usd: float
