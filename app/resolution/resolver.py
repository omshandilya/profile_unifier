import string
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Set
from datetime import datetime, timezone
import uuid

@dataclass
class ResolutionResult:
    canonical_profile: dict
    confidence: float
    status: str  # resolved / ambiguous / unresolved
    signals_fired: list[str]
    resolution_method: str = "rule_based"
    per_source_confidence: dict = field(default_factory=dict)


def normalize_handle(handle: str) -> str:
    if not handle:
        return ""
    h = str(handle).lower()
    for char in ["-", "_", "."]:
        h = h.replace(char, "")
    return h.strip()


def normalize_name(name: str) -> str:
    if not name:
        return ""
    n = str(name).lower()
    n = n.translate(str.maketrans("", "", string.punctuation))
    tokens = sorted(n.split())
    return " ".join(tokens).strip()


def normalize_location(location: str) -> str:
    if not location:
        return ""
    loc = str(location).lower().split(",")[0]
    return loc.strip()


def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return email
    parts = email.split("@")
    local = parts[0]
    domain = parts[1]
    if len(local) <= 2:
        masked_local = local[0] + "***" + local[-1] if len(local) == 2 else local + "***"
    else:
        masked_local = local[0] + "***" + local[-1]
    return f"{masked_local}@{domain}"


def extract_hn_topics(comments: list[dict]) -> set[str]:
    topics = set()
    for comment in comments:
        title = comment.get("story_title")
        if title:
            words = title.lower().replace("-", " ").replace("_", " ").split()
            for word in words:
                clean_word = "".join(c for c in word if c.isalnum())
                if len(clean_word) > 2:
                    topics.add(clean_word)
    return topics


class EntityResolver:
    def __init__(self, search_query: dict):
        # search_query shape: {"name": str, "github": str|None,
        #                       "stackoverflow": str|None, "devto": str|None,
        #                       "hackernews": str|None, "emailhint": str|None}
        self.search_query = search_query
        self.explanation_log = []

    def explain(self) -> str:
        """
        Returns a human-readable explanation of which signals fired and why.
        """
        return "\n".join(self.explanation_log)

    def resolve(
        self,
        github_data: dict,
        stackoverflow_data: dict,
        devto_data: dict,
        hackernews_data: dict
    ) -> ResolutionResult:
        signals_fired = []
        self.explanation_log = []
        
        # Ensure inputs are dicts
        github_data = github_data or {}
        stackoverflow_data = stackoverflow_data or {}
        devto_data = devto_data or {}
        hackernews_data = hackernews_data or {}

        # ----------------------------------------------------
        # Extract base handles and source identifiers
        # ----------------------------------------------------
        gh_user = (github_data.get("user", {}) or {}).get("login") or self.search_query.get("github")
        so_id = str((stackoverflow_data.get("user", {}) or {}).get("user_id") or "") or str(self.search_query.get("stackoverflow") or "")
        if so_id.endswith(".0"):
            so_id = so_id[:-2]
        devto_user = (devto_data.get("user", {}) or {}).get("username") or self.search_query.get("devto")
        hn_user = (hackernews_data.get("user", {}) or {}).get("username") or self.search_query.get("hackernews")

        # ====================================================
        # SIGNAL 1 — cross_platform_link (weight 0.45)
        # Scan bio and web URLs to discover matching linkages.
        # ====================================================
        gh_user_data = github_data.get("user", {}) or {}
        gh_bio = gh_user_data.get("bio") or ""
        gh_blog = gh_user_data.get("blog") or ""

        devto_user_data = devto_data.get("user", {}) or {}
        devto_gh = devto_user_data.get("github_username") or ""
        devto_web = devto_user_data.get("website_url") or ""

        so_user_data = stackoverflow_data.get("user", {}) or {}
        so_web = so_user_data.get("website_url") or ""

        cross_links = []
        # 1. GitHub <-> StackOverflow
        if (gh_user and so_id) and (
            f"stackoverflow.com/users/{so_id}" in gh_bio.lower() or 
            f"stackoverflow.com/users/{so_id}" in gh_blog.lower() or
            f"github.com/{gh_user.lower()}" in so_web.lower()
        ):
            cross_links.append("github_stackoverflow_link")

        # 2. GitHub <-> Dev.to
        if (gh_user and devto_user) and (
            f"dev.to/{devto_user.lower()}" in gh_bio.lower() or 
            f"dev.to/{devto_user.lower()}" in gh_blog.lower() or
            normalize_handle(devto_gh) == normalize_handle(gh_user) or
            f"github.com/{gh_user.lower()}" in devto_web.lower()
        ):
            cross_links.append("github_devto_link")

        # 3. StackOverflow <-> Dev.to
        if (so_id and devto_user) and (
            f"dev.to/{devto_user.lower()}" in so_web.lower() or
            f"stackoverflow.com/users/{so_id}" in devto_web.lower()
        ):
            cross_links.append("stackoverflow_devto_link")

        sig1_contribution = 0.0
        if cross_links:
            sig1_contribution = min(0.45, len(cross_links) * 0.45)
            signals_fired.append(f"cross_platform_link ({', '.join(cross_links)})")
            self.explanation_log.append(f"Signal [cross_platform_link] fired (+{sig1_contribution:.2f}): found linkages: {', '.join(cross_links)}")

        # ====================================================
        # SIGNAL 2 — email_match (weight 0.40)
        # Discover shared email addresses across platforms.
        # ====================================================
        email_sources = {}
        # GitHub user profile
        gh_profile_email = gh_user_data.get("email")
        if gh_profile_email:
            email_sources.setdefault(gh_profile_email.strip().lower(), set()).add("github_profile")

        # GitHub commits
        gh_commits = github_data.get("commits", []) or []
        for commit in gh_commits:
            author_email = None
            if isinstance(commit, dict):
                commit_info = commit.get("commit")
                if isinstance(commit_info, dict):
                    author = commit_info.get("author")
                    if isinstance(author, dict):
                        author_email = author.get("email")
                if not author_email:
                    author = commit.get("author")
                    if isinstance(author, dict):
                        author_email = author.get("email")
            if author_email:
                email_sources.setdefault(author_email.strip().lower(), set()).add("github_commits")

        # Search Query emailhint
        email_hint = self.search_query.get("emailhint")
        if email_hint:
            email_sources.setdefault(email_hint.strip().lower(), set()).add("emailhint")

        matching_emails = []
        for email, sources in email_sources.items():
            if len(sources) >= 2:
                matching_emails.append(email)

        sig2_contribution = 0.0
        if matching_emails:
            sig2_contribution = 0.40
            masked_list = [mask_email(e) for e in matching_emails]
            signals_fired.append(f"email_match ({', '.join(masked_list)})")
            self.explanation_log.append(f"Signal [email_match] fired (+0.40): matched emails: {', '.join(masked_list)}")

        # ====================================================
        # SIGNAL 3 — exact_handle_match (weight 0.30)
        # Check matching handles across platforms.
        # ====================================================
        handles_to_compare = []
        if gh_user:
            handles_to_compare.append(("github", normalize_handle(gh_user)))
        if devto_user:
            handles_to_compare.append(("devto", normalize_handle(devto_user)))
        if hn_user:
            handles_to_compare.append(("hackernews", normalize_handle(hn_user)))
            
        if self.search_query.get("github"):
            handles_to_compare.append(("query_github", normalize_handle(self.search_query.get("github"))))
        if self.search_query.get("devto"):
            handles_to_compare.append(("query_devto", normalize_handle(self.search_query.get("devto"))))
        if self.search_query.get("hackernews"):
            handles_to_compare.append(("query_hackernews", normalize_handle(self.search_query.get("hackernews"))))

        matching_pairs = []
        for i in range(len(handles_to_compare)):
            for j in range(i + 1, len(handles_to_compare)):
                src1, h1 = handles_to_compare[i]
                src2, h2 = handles_to_compare[j]
                # Avoid matching from the same source context (like github response vs query github)
                if h1 == h2 and h1 != "" and src1.split("_")[-1] != src2.split("_")[-1]:
                    matching_pairs.append((src1, src2, h1))

        sig3_contribution = 0.0
        if matching_pairs:
            sig3_contribution = min(0.30, len(matching_pairs) * 0.15)
            pair_descriptions = [f"{p[0]}=={p[1]} ({p[2]})" for p in matching_pairs]
            signals_fired.append(f"exact_handle_match ({', '.join(pair_descriptions)})")
            self.explanation_log.append(f"Signal [exact_handle_match] fired (+{sig3_contribution:.2f}): matching handles: {', '.join(pair_descriptions)}")

        # ====================================================
        # SIGNAL 4 — name_location_match (weight 0.25)
        # Match names and location strings.
        # ====================================================
        name_loc_sources = []
        if gh_user_data.get("name"):
            name_loc_sources.append(("github", normalize_name(gh_user_data["name"]), normalize_location(gh_user_data.get("location"))))
        elif gh_user:
            name_loc_sources.append(("github", normalize_name(gh_user), normalize_location(gh_user_data.get("location"))))

        if so_user_data.get("display_name"):
            name_loc_sources.append(("stackoverflow", normalize_name(so_user_data["display_name"]), normalize_location(so_user_data.get("location"))))

        if devto_user_data.get("name"):
            name_loc_sources.append(("devto", normalize_name(devto_user_data["name"]), normalize_location(devto_user_data.get("location"))))

        q_name = self.search_query.get("name")
        if q_name:
            name_loc_sources.append(("query", normalize_name(q_name), ""))

        name_match_found = False
        location_match_found = False
        fired_details = []

        for i in range(len(name_loc_sources)):
            for j in range(i + 1, len(name_loc_sources)):
                src1, n1, l1 = name_loc_sources[i]
                src2, n2, l2 = name_loc_sources[j]
                if n1 == n2 and n1 != "":
                    name_match_found = True
                    if l1 == l2 and l1 != "":
                        location_match_found = True
                        fired_details.append(f"{src1}=={src2} (name: '{n1}', loc: '{l1}')")
                    else:
                        fired_details.append(f"{src1}=={src2} (name: '{n1}')")

        sig4_contribution = 0.0
        if name_match_found:
            if location_match_found:
                sig4_contribution = 0.25
                signals_fired.append(f"name_location_match ({', '.join(fired_details)})")
                self.explanation_log.append(f"Signal [name_location_match] fired (+0.25): matched name & location: {', '.join(fired_details)}")
            else:
                sig4_contribution = 0.10
                signals_fired.append(f"name_match_only ({', '.join(fired_details)})")
                self.explanation_log.append(f"Signal [name_match_only] fired (+0.10): matched name only: {', '.join(fired_details)}")

        # ====================================================
        # SIGNAL 5 — tag_overlap (weight 0.10)
        # Verify language and keyword similarity.
        # ====================================================
        gh_langs = set(normalize_handle(l) for l in (github_data.get("languages", {}) or {}).keys() if l)
        
        so_tags = set()
        for tag in (stackoverflow_data.get("top_tags", []) or []):
            if isinstance(tag, dict) and tag.get("tag_name"):
                so_tags.add(normalize_handle(tag.get("tag_name")))
                
        devto_tags = set(normalize_handle(t) for t in (devto_data.get("tags", {}) or {}).keys() if t)
        
        hn_tags = extract_hn_topics(hackernews_data.get("comments", []) or [])
        hn_tags = set(normalize_handle(t) for t in hn_tags if t)

        gh_tags = gh_langs
        gh_tags.discard("")
        so_tags.discard("")
        devto_tags.discard("")
        hn_tags.discard("")

        active_sets = []
        if gh_tags:
            active_sets.append(gh_tags)
        if so_tags:
            active_sets.append(so_tags)
        if devto_tags:
            active_sets.append(devto_tags)
        if hn_tags:
            active_sets.append(hn_tags)

        jaccard_score = 0.0
        if len(active_sets) >= 2:
            similarities = []
            for i in range(len(active_sets)):
                for j in range(i + 1, len(active_sets)):
                    set1 = active_sets[i]
                    set2 = active_sets[j]
                    intersection = set1.intersection(set2)
                    union = set1.union(set2)
                    sim = len(intersection) / len(union) if union else 0.0
                    similarities.append(sim)
            jaccard_score = sum(similarities) / len(similarities)

        sig5_contribution = jaccard_score * 0.10
        if sig5_contribution > 0:
            signals_fired.append(f"tag_overlap (Jaccard similarity: {jaccard_score:.2f})")
            self.explanation_log.append(f"Signal [tag_overlap] fired (+{sig5_contribution:.2f}): computed Jaccard similarity between active sets: {jaccard_score:.2f}")

        # ----------------------------------------------------
        # Confidence Score Caps and Resolution Status Decisions
        # ----------------------------------------------------
        total_confidence = min(1.0, sig1_contribution + sig2_contribution + sig3_contribution + sig4_contribution + sig5_contribution)
        
        if total_confidence >= 0.85:
            resolution_status = "resolved"
        elif 0.50 <= total_confidence < 0.85:
            resolution_status = "ambiguous"
        else:
            resolution_status = "unresolved"

        self.explanation_log.append(f"Total confidence score: {total_confidence:.2f} -> Status: {resolution_status}")

        # ----------------------------------------------------
        # Merge Profile Data (Priority: GitHub -> SO -> DevTo)
        # ----------------------------------------------------
        display_name = gh_user_data.get("name") or gh_user_data.get("login") or so_user_data.get("display_name") or devto_user_data.get("name") or "Anonymous Developer"
        location = gh_user_data.get("location") or so_user_data.get("location") or devto_user_data.get("location")
        bio = gh_user_data.get("bio") or so_user_data.get("about_me") or devto_user_data.get("summary")

        primary_email = None
        if matching_emails:
            primary_email = mask_email(matching_emails[0])
        elif gh_profile_email:
            primary_email = mask_email(gh_profile_email)
        elif email_hint:
            primary_email = mask_email(email_hint)

        # Merge languages by summing counts
        merged_langs = {}
        for lang, count in (github_data.get("languages", {}) or {}).items():
            merged_langs[lang] = merged_langs.get(lang, 0) + count
        for tag, count in (devto_data.get("tags", {}) or {}).items():
            matched_key = tag
            for k in merged_langs.keys():
                if k.lower() == tag.lower():
                    matched_key = k
                    break
            merged_langs[matched_key] = merged_langs.get(matched_key, 0) + count

        # Merge tags (SO top tags, DevTo article tags, HN comments topics)
        all_tags = set()
        for tag in (stackoverflow_data.get("top_tags", []) or []):
            if isinstance(tag, dict) and tag.get("tag_name"):
                all_tags.add(tag["tag_name"])
        # Dev.to article tags
        for art in (devto_data.get("articles", []) or []):
            tag_list = art.get("tag_list")
            if isinstance(tag_list, list):
                for t in tag_list:
                    all_tags.add(str(t))
        # HN Comment topics
        for comment_tag in hn_tags:
            all_tags.add(comment_tag)

        # Construct Canonical Profile Dictionary
        canonical_profile = {
            "profile_id": str(uuid.uuid4()),
            "display_name": display_name,
            "location": location,
            "bio": bio,
            "primary_email": primary_email,
            "merged_languages": merged_langs,
            "merged_tags": sorted(list(all_tags)),
            "resolution_confidence": total_confidence,
            "resolution_status": resolution_status,
            "llm_summary": None,
            "llm_tokens_used": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        # Calculate per-source confidence levels dynamically between 0.0 and 1.0
        per_source = {
            "github": 0.0,
            "stackoverflow": 0.0,
            "devto": 0.0,
            "hackernews": 0.0
        }

        # github
        if github_data.get("user"):
            contrib = 0
            if any(x in ["github_stackoverflow_link", "github_devto_link"] for x in cross_links):
                contrib += 1
            # Email sources check
            gh_emails = email_sources.get(gh_profile_email.strip().lower() if gh_profile_email else "")
            if gh_emails and len(gh_emails) >= 2:
                contrib += 1
            if any(p[0] in ["github", "query_github"] or p[1] in ["github", "query_github"] for p in matching_pairs):
                contrib += 1
            if any("github" in d for d in fired_details):
                contrib += 1
            if gh_tags and jaccard_score > 0:
                contrib += 1
            per_source["github"] = round(0.2 + contrib * 0.16, 2)

        # stackoverflow
        if stackoverflow_data.get("user"):
            contrib = 0
            if any(x in ["github_stackoverflow_link", "stackoverflow_devto_link"] for x in cross_links):
                contrib += 1
            if any(p[0] in ["stackoverflow", "query_stackoverflow"] or p[1] in ["stackoverflow", "query_stackoverflow"] for p in matching_pairs):
                contrib += 1
            if any("stackoverflow" in d for d in fired_details):
                contrib += 1
            if so_tags and jaccard_score > 0:
                contrib += 1
            per_source["stackoverflow"] = round(0.2 + contrib * 0.16, 2)

        # devto
        if devto_data.get("user"):
            contrib = 0
            if any(x in ["github_devto_link", "stackoverflow_devto_link"] for x in cross_links):
                contrib += 1
            if any(p[0] in ["devto", "query_devto"] or p[1] in ["devto", "query_devto"] for p in matching_pairs):
                contrib += 1
            if any("devto" in d for d in fired_details):
                contrib += 1
            if devto_tags and jaccard_score > 0:
                contrib += 1
            per_source["devto"] = round(0.2 + contrib * 0.16, 2)

        # hackernews
        if hackernews_data.get("user"):
            contrib = 0
            if any(p[0] in ["hackernews", "query_hackernews"] or p[1] in ["hackernews", "query_hackernews"] for p in matching_pairs):
                contrib += 1
            if hn_tags and jaccard_score > 0:
                contrib += 1
            per_source["hackernews"] = round(0.2 + contrib * 0.16, 2)

        return ResolutionResult(
            canonical_profile=canonical_profile,
            confidence=total_confidence,
            status=resolution_status,
            signals_fired=signals_fired,
            resolution_method="rule_based",
            per_source_confidence=per_source
        )

    @staticmethod
    def resolve_profiles(
        github: Optional[dict],
        stackoverflow: Optional[dict],
        devto: Optional[dict],
        hackernews: Optional[dict]
    ) -> dict:
        """
        Backward-compatibility helper method for resolving profile dicts.
        """
        gh = {"user": github} if github else {}
        so = {"user": stackoverflow} if stackoverflow else {}
        dt = {"user": devto} if devto else {}
        hn = {"user": hackernews} if hackernews else {}
        
        resolver = EntityResolver({"name": "Anonymous"})
        res = resolver.resolve(gh, so, dt, hn)
        cp = res.canonical_profile
        
        # Use unmasked emails for legacy compatibility
        legacy_emails = []
        gh_profile_email = (github or {}).get("email")
        if gh_profile_email:
            legacy_emails.append(gh_profile_email)
            
        return {
            "profile_id": cp.get("profile_id", ""),
            "unified_name": cp.get("display_name") or "Anonymous Developer",
            "bio": cp.get("bio"),
            "emails": legacy_emails,
            "github_data": github,
            "stackoverflow_data": stackoverflow,
            "devto_data": devto,
            "hackernews_data": hackernews,
            "resolved_at": cp.get("created_at", "")
        }
