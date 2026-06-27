import logging
import time
from datetime import datetime, timezone
from collections import defaultdict
from typing import Optional

logger = logging.getLogger("effiflo-dev-unifier")


class MetricsTracker:
    """
    In-memory singleton that accumulates live telemetry for the /health endpoint
    and for passing to the observability_metrics Supabase table via SupabaseStore.
    """

    def __init__(self):
        # Keyed by source name e.g. "github", "stackoverflow", "devto", "hackernews", "gemini"
        self.total_api_calls: dict[str, int] = defaultdict(int)
        # Sum of latencies per source for average calculation
        self._total_latency_ms: dict[str, int] = defaultdict(int)
        self.total_profiles_resolved: int = 0
        self.resolution_times_ms: list[int] = []
        self.llm_tokens_used: int = 0
        # GitHub rate-limit snapshot updated after every GitHub response
        self.github_rate_limit: dict = {
            "remaining": None,
            "limit": None,
            "reset_time": None,   # unix timestamp int
        }

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def record_api_call(self, source: str, latency_ms: int) -> None:
        """Increment the call counter and accumulate latency for a given source."""
        self.total_api_calls[source] += 1
        self._total_latency_ms[source] += latency_ms

    def record_profile_resolved(self, resolution_time_ms: int) -> None:
        """Increment the resolved-profile counter and append the resolution time."""
        self.total_profiles_resolved += 1
        self.resolution_times_ms.append(resolution_time_ms)

    def record_llm_usage(self, tokens: int) -> None:
        """Accumulate Gemini token usage."""
        self.llm_tokens_used += tokens

    def update_github_rate_limit(
        self, remaining: int, limit: int, reset_time: int
    ) -> None:
        """
        Overwrite the cached GitHub rate-limit snapshot.
        reset_time is a Unix timestamp (seconds).
        """
        self.github_rate_limit = {
            "remaining": remaining,
            "limit": limit,
            "reset_time": reset_time,
        }

    # ------------------------------------------------------------------
    # Summary (used by GET /health)
    # ------------------------------------------------------------------

    def get_summary(self) -> dict:
        """Return a serialisable summary dict for the health endpoint."""

        # GitHub rate-limit block
        rl = self.github_rate_limit
        reset_at = None
        if rl.get("reset_time") is not None:
            try:
                reset_at = datetime.fromtimestamp(
                    rl["reset_time"], tz=timezone.utc
                ).isoformat()
            except (OSError, OverflowError, ValueError):
                reset_at = None

        github_rl_summary = {
            "remaining": rl.get("remaining"),
            "total": rl.get("limit"),
            "reset_at": reset_at,
        }

        # Average resolution time
        if self.resolution_times_ms:
            avg_resolution = round(
                sum(self.resolution_times_ms) / len(self.resolution_times_ms), 2
            )
        else:
            avg_resolution = 0.0

        return {
            "github_rate_limit": github_rl_summary,
            "api_calls_by_source": dict(self.total_api_calls),
            "total_profiles_resolved": self.total_profiles_resolved,
            "average_resolution_time_ms": avg_resolution,
            "llm_tokens_used": self.llm_tokens_used,
            # Gemini free tier — always 0
            "estimated_llm_cost_usd": 0.0,
        }

    # ------------------------------------------------------------------
    # Legacy compatibility — used by existing routes.py
    # ------------------------------------------------------------------

    def increment(self, metric_name: str) -> None:
        """Legacy method kept for backward compat with routes.py placeholder code."""
        self.total_api_calls[metric_name] += 1

    def get_metrics(self) -> dict:
        """Legacy method — returns a flat dict expected by the original /health route."""
        return {
            "resolve_requests": self.total_api_calls.get("resolve_requests", 0),
            "profile_lookups": self.total_api_calls.get("profile_lookups", 0),
            "errors": self.total_api_calls.get("errors", 0),
        }


# Module-level singleton — import this everywhere.
metrics_tracker = MetricsTracker()
# Also expose as `metrics` for the new API described in the prompt.
metrics = metrics_tracker
