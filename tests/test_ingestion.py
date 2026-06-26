import pytest
from app.ingestion.github import GitHubClient
from app.ingestion.stackoverflow import StackOverflowClient
from app.ingestion.devto import DevToClient
from app.ingestion.hackernews import HackerNewsClient

@pytest.mark.asyncio
async def test_clients_instantiation():
    gh = GitHubClient()
    so = StackOverflowClient()
    devto = DevToClient()
    hn = HackerNewsClient()
    
    assert gh.base_url == "https://api.github.com"
    assert so.base_url == "https://api.stackexchange.com/2.3"
    assert devto.base_url == "https://dev.to/api"
    assert hn.base_url == "https://hn.algolia.com/api/v1"
