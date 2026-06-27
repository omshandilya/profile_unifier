import pytest
import respx
import httpx
from app.config import settings
from app.ingestion.github import GitHubClient
from app.ingestion.stackoverflow import StackOverflowClient
from app.ingestion.devto import DevToClient
from app.ingestion.hackernews import HackerNewsClient

FAKE_USER = {
    "login": "torvalds",
    "id": 1024025,
    "name": "Linus Torvalds",
    "location": "Portland, OR",
    "bio": "Just a random hacker.",
    "email": None,
    "public_repos": 6,
}


# ─────────────────────────────────────────────────────────────────────────────
# Client instantiation tests
# ─────────────────────────────────────────────────────────────────────────────

def test_clients_instantiation():
    gh = GitHubClient(settings)
    so = StackOverflowClient(settings)
    devto = DevToClient(settings)
    hn = HackerNewsClient(settings)

    assert gh.base_url == "https://api.github.com"
    assert so.base_url == "https://api.stackexchange.com/2.3"
    assert devto.base_url == "https://dev.to/api"
    assert hn.base_url == "https://hn.algolia.com/api/v1"


def test_devto_tag_extraction():
    articles = [
        {"tag_list": ["python", "fastapi"]},
        {"tag_list": ["python", "webdev"]},
        {"tag_list": "webdev, test"},
    ]
    extracted = DevToClient.extract_tags(articles)
    assert extracted == {"python": 2, "fastapi": 1, "webdev": 2, "test": 1}


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — mock a real 200 response from GitHub
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_github_client_returns_user():
    """
    Mock the GitHub /users/torvalds endpoint to return FAKE_USER.
    GitHubClient.get_user should return that dict unchanged.
    """
    respx.get("https://api.github.com/users/torvalds").mock(
        return_value=httpx.Response(200, json=FAKE_USER)
    )

    client = GitHubClient(settings)
    result = await client.get_user("torvalds")

    assert result["login"] == "torvalds"
    assert result["name"] == "Linus Torvalds"
    assert result["id"] == 1024025


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — 404 must return empty dict, not raise
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_github_404_returns_empty():
    """
    Mock the GitHub /users/doesnotexist endpoint to return 404.
    GitHubClient.get_user must return {} without raising an exception.
    """
    respx.get("https://api.github.com/users/doesnotexist").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )

    client = GitHubClient(settings)
    result = await client.get_user("doesnotexist")

    assert result == {}
