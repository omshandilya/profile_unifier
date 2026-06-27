import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import settings
from app.ingestion.github import GitHubClient
from app.observability.metrics import metrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("effiflo-dev-unifier")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("Dev Profile Unifier started")
    logger.info(f"Environment : {settings.ENVIRONMENT}")

    # Pre-fetch the GitHub rate-limit so the /health endpoint shows a real
    # value from the very first request, even before any resolution has run.
    if settings.GITHUB_TOKEN:
        try:
            gh = GitHubClient(github_token=settings.GITHUB_TOKEN)
            rl = await gh.get_rate_limit()
            core = (rl.get("resources") or {}).get("core") or rl.get("rate") or {}
            if core.get("remaining") is not None:
                metrics.update_github_rate_limit(
                    remaining=int(core["remaining"]),
                    limit=int(core.get("limit", 5000)),
                    reset_time=int(core.get("reset", 0)),
                )
                logger.info(
                    f"GitHub rate limit: {core['remaining']}/{core.get('limit', 5000)} "
                    f"remaining"
                )
        except Exception as exc:
            logger.warning(f"Could not prefetch GitHub rate limit on startup: {exc}")
    else:
        logger.warning("GITHUB_TOKEN not set — GitHub ingestion will be unauthenticated (60 req/hr).")

    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        logger.warning(
            "Supabase credentials not configured — persistence will be bypassed. "
            "Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env to enable."
        )

    if not settings.GEMINI_API_KEY:
        logger.warning(
            "GEMINI_API_KEY not set — LLM summaries will return placeholder text."
        )

    yield  # ── application runs ──

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Dev Profile Unifier shutting down")
    summary = metrics.get_summary()
    logger.info(
        f"Session stats — profiles resolved: {summary['total_profiles_resolved']}, "
        f"LLM tokens used: {summary['llm_tokens_used']}, "
        f"API calls: {dict(summary['api_calls_by_source'])}"
    )


app = FastAPI(
    title="Dev Profile Unifier",
    description=(
        "Resolves developer identities across GitHub, Stack Overflow, "
        "dev.to, and Hacker News into a single canonical profile using "
        "rule-based signal matching and Gemini AI enrichment."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(router)
