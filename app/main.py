import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    logger.info("Dev Profile Unifier starting up...")
    logger.info(f"Environment : {settings.environment}")

    # Log which env vars are present (masked values)
    env_keys = [
        "GITHUB_TOKEN",
        "STACKOVERFLOW_KEY",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
        "GEMINI_API_KEY",
        "ENVIRONMENT"
    ]
    logger.info("Checking configuration environment variables:")
    for key in env_keys:
        val = getattr(settings, key, None)
        if val:
            # Mask value
            val_str = str(val)
            masked = val_str[:4] + "***" + val_str[-4:] if len(val_str) > 8 else "***"
            logger.info(f" - {key}: {masked}")
        else:
            logger.info(f" - {key}: [Not Set]")

    # Pre-fetch the GitHub rate-limit
    if settings.github_token:
        try:
            gh = GitHubClient(settings)
            rl = await gh.get_rate_limit()
            core = (rl.get("resources") or {}).get("core") or rl.get("rate") or {}
            if core.get("remaining") is not None:
                metrics.update_github_rate_limit(
                    remaining=int(core["remaining"]),
                    limit=int(core.get("limit", 5000)),
                    reset_time=int(core.get("reset", 0)),
                )
                logger.info(
                    f"GitHub rate limit: {core['remaining']}/{core.get('limit', 5000)} remaining"
                )
        except Exception as exc:
            logger.warning(f"Could not prefetch GitHub rate limit on startup: {exc}")
    else:
        logger.warning("GITHUB_TOKEN not set — GitHub ingestion will be unauthenticated.")

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

# CORS middleware allowing all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
