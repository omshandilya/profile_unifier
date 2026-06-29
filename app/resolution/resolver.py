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

        # Per-source signal lists — appended to as each signal fires
        per_source_signals: Dict[str, List[str]] = {
            "github": [],
            "stackoverflow": [],
            "devto": [],
            "hackernews": [],
        }

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

        # GitHub -> StackOverflow: link found in GitHub bio/blog
        gh_so_from_gh = (
            gh_user and so_id and (
                f"stackoverflow.com/users/{so_id}" in gh_bio.lower() or
                f"stackoverflow.com/users/{so_id}" in gh_blog.lower()
            )
        )
        # StackOverflow -> GitHub: SO website_url points at GitHub
        gh_so_from_so = (
            gh_user and so_id and
            f"github.com/{gh_user.lower()}" in so_web.lower()
        )
        if gh_so_from_gh or gh_so_from_so:
            cross_links.append("github_stackoverflow_link")
            if gh_so_from_gh:
                per_source_signals["github"].append("cross_platform_link")
            if gh_so_from_so:
                per_source_signals["stackoverflow"].append("cross_platform_link")

        # GitHub -> Dev.to: link in bio/blog, or devto github_username matches
        gh_dt_from_gh = (
            gh_user and devto_user and (
                f"dev.to/{devto_user.lower()}" in gh_bio.lower() or
                f"dev.to/{devto_user.lower()}" in gh_blog.lower()
            )
        )
        # Dev.to -> GitHub: devto github_username field or website points at GitHub
        gh_dt_from_dt = (
            gh_user and devto_user and (
                normalize_handle(devto_gh) == normalize_handle(gh_user) or
                f"github.com/{gh_user.lower()}" in devto_web.lower()
            )
        )
        if gh_dt_from_gh or gh_dt_from_dt:
            cross_links.append("github_devto_link")
            if gh_dt_from_gh:
                per_source_signals["github"].append("cross_platform_link")
            if gh_dt_from_dt:
                per_source_signals["devto"].append("cross_platform_link")

        # StackOverflow -> Dev.to
        so_dt_from_so = (
            so_id and devto_user and
            f"dev.to/{devto_user.lower()}" in so_web.lower()
        )
        so_dt_from_dt = (
            so_id and devto_user and
            f"stackoverflow.com/users/{so_id}" in devto_web.lower()
        )
        if so_dt_from_so or so_dt_from_dt:
            cross_links.append("stackoverflow_devto_link")
            if so_dt_from_so:
                per_source_signals["stackoverflow"].append("cross_platform_link")
            if so_dt_from_dt:
                per_source_signals["devto"].append("cross_platform_link")

        # Deduplicate per-source entries that may have fired twice for the same signal
        for src in per_source_signals:
            seen: List[str] = []
            for s in per_source_signals[src]:
                if s not in seen:
                    seen.append(s)
            per_source_signals[src] = seen

        sig1_contribution = 0.0
        if cross_links:
            sig1_contribution = min(0.45, len(cross_links) * 0.45)
            signals_fired.append(f"cross_platform_link ({', '.join(cross_links)})")
            self.explanation_log.append(
                f"Signal [cross_platform_link] fired (+{sig1_contribution:.2f}): found linkages: {', '.join(cross_links)}"
            )

        # ====================================================
        # SIGNAL 2 — email_match (weight 0.40)
        # Discover shared email addresses across platforms.
        # ====================================================
        email_sources: Dict[str, set] = {}

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

        matching_emails = [
            email for email, sources in email_sources.items() if len(sources) >= 2
        ]

        sig2_contribution = 0.0
        if matching_emails:
            sig2_contribution = 0.40
            masked_list = [mask_email(e) for e in matching_emails]
            signals_fired.append(f"email_match ({', '.join(masked_list)})")
            self.explanation_log.append(
                f"Signal [email_match] fired (+0.40): matched emails: {', '.join(masked_list)}"
            )
            # GitHub gets credit if any matched email came from a GitHub source
            for email in matching_emails:
                sources = email_sources.get(email, set())
                if sources & {"github_profile", "github_commits"}:
                    per_source_signals["github"].append("email_match")
                    break  # one credit per signal per source

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
                if h1 == h2 and h1 != "" and src1.split("_")[-1] != src2.split("_")[-1]:
                    matching_pairs.append((src1, src2, h1))

        sig3_contribution = 0.0
        if matching_pairs:
            sig3_contribution = min(0.30, len(matching_pairs) * 0.15)
            pair_descriptions = [f"{p[0]}=={p[1]} ({p[2]})" for p in matching_pairs]
            signals_fired.append(f"exact_handle_match ({', '.join(pair_descriptions)})")
            self.explanation_log.append(
                f"Signal [exact_handle_match] fired (+{sig3_contribution:.2f}): matching handles: {', '.join(pair_descriptions)}"
            )
            # Credit each platform source that appears in at least one matched pair
            _REAL_SOURCES = {"github", "stackoverflow", "devto", "hackernews"}
            for src1, src2, _ in matching_pairs:
                for side in (src1, src2):
                    real_src = side.replace("query_", "")
                    if real_src in _REAL_SOURCES:
                        if "exact_handle_match" not in per_source_signals[real_src]:
                            per_source_signals[real_src].append("exact_handle_match")

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
        name_matched_sources: Set[str] = set()
        _REAL_SOURCES = {"github", "stackoverflow", "devto", "hackernews"}

        for i in range(len(name_loc_sources)):
            for j in range(i + 1, len(name_loc_sources)):
                src1, n1, l1 = name_loc_sources[i]
                src2, n2, l2 = name_loc_sources[j]
                if n1 == n2 and n1 != "":
                    name_match_found = True
                    for s in (src1, src2):
                        if s in _REAL_SOURCES:
                            name_matched_sources.add(s)
                    if l1 == l2 and l1 != "":
                        location_match_found = True
                        fired_details.append(f"{src1}=={src2} (name: '{n1}', loc: '{l1}')")
                    else:
                        fired_details.append(f"{src1}=={src2} (name: '{n1}')")

        sig4_contribution = 0.0
        sig4_name = None
        if name_match_found:
            if location_match_found:
                sig4_contribution = 0.25
                sig4_name = "name_location_match"
                signals_fired.append(f"name_location_match ({', '.join(fired_details)})")
                self.explanation_log.append(
                    f"Signal [name_location_match] fired (+0.25): matched name & location: {', '.join(fired_details)}"
                )
            else:
                sig4_contribution = 0.10
                sig4_name = "name_match_only"
                signals_fired.append(f"name_match_only ({', '.join(fired_details)})")
                self.explanation_log.append(
                    f"Signal [name_match_only] fired (+0.10): matched name only: {', '.join(fired_details)}"
                )
            for src in name_matched_sources:
                if "name_location_match" not in per_source_signals[src] and "name_match_only" not in per_source_signals[src]:
                    per_source_signals[src].append(sig4_name)

        # ====================================================
        # SIGNAL 5 — tag_overlap (weight 0.10)
        # Verify language and keyword similarity.
        # ====================================================
        gh_langs = set(normalize_handle(l) for l in (github_data.get("languages", {}) or {}).keys() if l)

        so_tags: Set[str] = set()
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

        # Build active sets with their source names so we can credit per-source
        active_named_sets: List[tuple] = []
        if gh_tags:
            active_named_sets.append(("github", gh_tags))
        if so_tags:
            active_named_sets.append(("stackoverflow", so_tags))
        if devto_tags:
            active_named_sets.append(("devto", devto_tags))
        if hn_tags:
            active_named_sets.append(("hackernews", hn_tags))

        jaccard_score = 0.0
        if len(active_named_sets) >= 2:
            similarities = []
            for i in range(len(active_named_sets)):
                for j in range(i + 1, len(active_named_sets)):
                    set1 = active_named_sets[i][1]
                    set2 = active_named_sets[j][1]
                    intersection = set1.intersection(set2)
                    union = set1.union(set2)
                    sim = len(intersection) / len(union) if union else 0.0
                    similarities.append(sim)
            jaccard_score = sum(similarities) / len(similarities)

        sig5_contribution = jaccard_score * 0.10
        if sig5_contribution > 0:
            signals_fired.append(f"tag_overlap (Jaccard similarity: {jaccard_score:.2f})")
            self.explanation_log.append(
                f"Signal [tag_overlap] fired (+{sig5_contribution:.2f}): computed Jaccard similarity between active sets: {jaccard_score:.2f}"
            )
            # Every source that contributed a non-empty tag set gets credited
            for src_name, _ in active_named_sets:
                per_source_signals[src_name].append("tag_overlap")

        # ----------------------------------------------------
        # Confidence Score Caps and Resolution Status Decisions
        # ----------------------------------------------------
        total_confidence = min(
            1.0,
            sig1_contribution + sig2_contribution + sig3_contribution + sig4_contribution + sig5_contribution,
        )

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
        display_name = (
            gh_user_data.get("name") or gh_user_data.get("login") or
            so_user_data.get("display_name") or devto_user_data.get("name") or
            "Anonymous Developer"
        )
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
        merged_langs: Dict[str, int] = {}
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
        all_tags: set = set()
        for tag in (stackoverflow_data.get("top_tags", []) or []):
            if isinstance(tag, dict) and tag.get("tag_name"):
                all_tags.add(tag["tag_name"])
        for art in (devto_data.get("articles", []) or []):
            tag_list = art.get("tag_list")
            if isinstance(tag_list, list):
                for t in tag_list:
                    all_tags.add(str(t))
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
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # ----------------------------------------------------
        # Build per_source_confidence with score + own signals
        # ----------------------------------------------------
        _SOURCE_DATA = {
            "github": github_data.get("user"),
            "stackoverflow": stackoverflow_data.get("user"),
            "devto": devto_data.get("user"),
            "hackernews": hackernews_data.get("user"),
        }

        per_source_confidence: Dict[str, Any] = {}
        for src in ("github", "stackoverflow", "devto", "hackernews"):
            own_signals = per_source_signals[src]
            if _SOURCE_DATA[src]:
                # Score = 0.2 base + 0.16 per signal fired, capped at 1.0
                score = round(min(1.0, 0.2 + len(own_signals) * 0.16), 2)
            else:
                score = 0.0
            per_source_confidence[src] = {
                "confidence_score": score,
                "signals_fired": own_signals,
            }

        return ResolutionResult(
            canonical_profile=canonical_profile,
            confidence=total_confidence,
            status=resolution_status,
            signals_fired=signals_fired,
            resolution_method="rule_based",
            per_source_confidence=per_source_confidence,
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
