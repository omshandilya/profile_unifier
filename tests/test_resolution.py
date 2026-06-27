import pytest
from app.resolution.resolver import EntityResolver


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — high confidence: cross-platform link + name+location match
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_high_confidence():
    """
    GitHub bio explicitly links to dev.to/testuser (cross_platform_link fires),
    the name "Alice Johnson" and location "Berlin" appear on both GitHub and
    Stack Overflow (name_location_match fires). Also include emailhint to trigger
    email_match. Together these should push confidence to >= 0.85 and status to "resolved".
    """
    query = {
        "name": "Alice Johnson",
        "github": "alicejohnson",
        "devto": "testuser",
        "emailhint": "alice@johnson.com"
    }

    github_data = {
        "user": {
            "login": "alicejohnson",
            "name": "Alice Johnson",
            "location": "Berlin, Germany",
            "bio": "Open-source enthusiast. Also writing at dev.to/testuser",
            "blog": "",
            "email": "alice@johnson.com",
        },
        "languages": {"Python": 8000, "Go": 3000},
        "commits": [],
    }

    stackoverflow_data = {
        "user": {
            "user_id": 99001,
            "display_name": "Alice Johnson",
            "location": "Berlin",
            "website_url": "",
        },
        "top_tags": [{"tag_name": "python", "answer_count": 10}],
    }

    devto_data = {
        "user": {
            "username": "testuser",
            "name": "Alice Johnson",
            "github_username": "alicejohnson",
        },
        "tags": {"python": 3},
        "articles": [],
    }

    resolver = EntityResolver(query)
    res = resolver.resolve(github_data, stackoverflow_data, devto_data, {})

    assert res.confidence >= 0.85, f"Expected >= 0.85, got {res.confidence}"
    assert res.status == "resolved"
    assert any("cross_platform_link" in s for s in res.signals_fired), (
        f"cross_platform_link not in signals_fired: {res.signals_fired}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — ambiguous: name match only, different locations, no other signals
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_ambiguous():
    """
    "David Chen" appears on both GitHub and Stack Overflow but the locations
    differ. We trigger email match (0.40) and name match (0.10) to reach exactly
    0.50, which falls into the ambiguous status (0.50 <= c < 0.85).
    """
    query = {
        "name": "David Chen",
        "github": "davidchen",
        "stackoverflow": "99002",
        "emailhint": "david@chen.com"
    }

    github_data = {
        "user": {
            "login": "davidchen",
            "name": "David Chen",
            "location": "San Francisco, CA",
            "bio": "",
            "blog": "",
            "email": "david@chen.com",
        },
        "languages": {},
        "commits": [],
    }

    stackoverflow_data = {
        "user": {
            "user_id": 99002,
            "display_name": "David Chen",
            "location": "New York",   # different city → no location match
            "website_url": "",
        },
        "top_tags": [],
    }

    resolver = EntityResolver(query)
    res = resolver.resolve(github_data, stackoverflow_data, {}, {})

    assert 0.50 <= res.confidence < 0.85, (
        f"Expected ambiguous band (0.50-0.84), got {res.confidence}"
    )
    assert res.status == "ambiguous"


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — unresolved: completely different names, zero overlapping signals
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_unresolved():
    """
    GitHub user "alice123" and SO user "Bob Martinez" share no name, handle,
    location, email, link, or tag overlap.  Confidence must stay below 0.50.
    """
    query = {"name": "alice123", "github": "alice123", "stackoverflow": "99003"}

    github_data = {
        "user": {
            "login": "alice123",
            "name": "alice123",
            "location": "Tokyo",
            "bio": "",
            "blog": "",
            "email": None,
        },
        "languages": {"Haskell": 500},
        "commits": [],
    }

    stackoverflow_data = {
        "user": {
            "user_id": 99003,
            "display_name": "Bob Martinez",
            "location": "Buenos Aires",
            "website_url": "",
        },
        "top_tags": [{"tag_name": "java", "answer_count": 5}],
    }

    resolver = EntityResolver(query)
    res = resolver.resolve(github_data, stackoverflow_data, {}, {})

    assert res.confidence < 0.50, (
        f"Expected confidence < 0.50, got {res.confidence}"
    )
    assert res.status == "unresolved"


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — exact handle normalization: "john-doe" vs "johndoe"
# ─────────────────────────────────────────────────────────────────────────────

def test_exact_handle_normalization():
    """
    GitHub username "john-doe" and HackerNews username "johndoe" should match
    after normalization (strip hyphens/underscores/dots, lowercase).
    The exact_handle_match signal must appear in signals_fired.
    """
    query = {"name": "John Doe", "github": "john-doe", "hackernews": "johndoe"}

    github_data = {
        "user": {
            "login": "john-doe",
            "name": "John Doe",
            "location": None,
            "bio": "",
            "blog": "",
            "email": None,
        },
        "languages": {},
        "commits": [],
    }

    hackernews_data = {
        "user": {
            "username": "johndoe",
        },
        "submissions": [],
        "comments": [],
    }

    resolver = EntityResolver(query)
    res = resolver.resolve(github_data, {}, {}, hackernews_data)

    assert any("exact_handle_match" in s for s in res.signals_fired), (
        f"exact_handle_match not fired; signals: {res.signals_fired}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — tag overlap Jaccard contribution
# ─────────────────────────────────────────────────────────────────────────────

def test_tag_overlap_jaccard():
    """
    GitHub languages Python + Rust overlap perfectly with SO top tags python +
    rust.  Jaccard similarity = 1.0 → signal contribution = 0.10.
    Confidence must be > 0 and the tag_overlap signal must fire.
    """
    query = {"name": "Dev User", "github": "devuser"}

    github_data = {
        "user": {"login": "devuser", "name": "Dev User", "bio": "", "blog": "", "location": None, "email": None},
        "languages": {"Python": 1000, "Rust": 500},
        "commits": [],
    }

    stackoverflow_data = {
        "user": {
            "user_id": 99004,
            "display_name": "Dev User",
            "location": None,
            "website_url": "",
        },
        "top_tags": [
            {"tag_name": "python", "answer_count": 8},
            {"tag_name": "rust",   "answer_count": 4},
        ],
    }

    resolver = EntityResolver(query)
    res = resolver.resolve(github_data, stackoverflow_data, {}, {})

    assert any("tag_overlap" in s for s in res.signals_fired), (
        f"tag_overlap not fired; signals: {res.signals_fired}"
    )
    assert res.confidence > 0
