import pytest
from app.resolution.resolver import EntityResolver

def test_resolve_profiles_empty():
    result = EntityResolver.resolve_profiles(None, None, None, None)
    assert result["unified_name"] == "Anonymous Developer"
    assert result["emails"] == []

def test_resolve_profiles_github():
    github_data = {"login": "testdev", "name": "Test Developer", "email": "test@dev.com", "bio": "Writing code."}
    result = EntityResolver.resolve_profiles(github_data, None, None, None)
    assert result["unified_name"] == "Test Developer"
    assert result["emails"] == ["test@dev.com"]
    assert result["bio"] == "Writing code."
