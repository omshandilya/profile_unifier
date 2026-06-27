import pytest
from app.resolution.resolver import EntityResolver, ResolutionResult

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

def test_entity_resolver_signals():
    query = {
        "name": "Octo Cat",
        "github": "octocat",
        "emailhint": "octo@github.com"
    }
    
    # Setup data to trigger email match, exact handle match, and name location match
    github_data = {
        "user": {
            "login": "octocat",
            "name": "Octo Cat",
            "email": "octo@github.com",
            "location": "San Francisco, CA",
            "bio": "GitHub mascot. check stackoverflow.com/users/12345"
        },
        "languages": {"Python": 1000}
    }
    
    stackoverflow_data = {
        "user": {
            "user_id": 12345,
            "display_name": "Octo Cat",
            "location": "San Francisco",
            "website_url": "github.com/octocat"
        },
        "top_tags": [{"tag_name": "python", "answer_count": 5}]
    }
    
    devto_data = {
        "user": {
            "username": "octo_cat",
            "name": "Octo Cat",
            "github_username": "octocat"
        },
        "tags": {"python": 2}
    }
    
    resolver = EntityResolver(query)
    res = resolver.resolve(github_data, stackoverflow_data, devto_data, {})
    
    # Assert confidence logic
    assert res.confidence > 0.50
    assert "cross_platform_link (github_stackoverflow_link)" in res.signals_fired or "cross_platform_link (github_stackoverflow_link, github_devto_link)" in res.signals_fired
    assert "email_match (o***o@github.com)" in res.signals_fired
    assert res.canonical_profile["display_name"] == "Octo Cat"
    assert res.canonical_profile["primary_email"] == "o***o@github.com"
    assert "python" in res.canonical_profile["merged_tags"]
    
    # Check explain output
    explanation = resolver.explain()
    assert "Signal [email_match]" in explanation
    assert "Total confidence score:" in explanation
