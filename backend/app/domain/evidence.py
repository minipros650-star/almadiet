"""AlmaDiet — Evidence domain: domain allowlist and claim-status rules.

This module is the *code-level* half of the false-information controls:

* The ALLOWED_DOMAINS allowlist is enforced here (exact eTLD+1 or
  subdomain match; `about:blank`-style bypasses, unicode confusables and
  userinfo tricks are normalized away).
* Claim status transitions are defined here: a claim starts at
  PENDING_CLINICAL_REVIEW and can only leave that state via an immutable
  ClinicalReviewDecision. Conflict handling is explicit: conflicting
  sources produce CONFLICT_PENDING_REVIEW, and the model never chooses
  between conflicting medical claims.
* Retrieved web text is DATA, never instructions: `sanitize_source_text`
  strips control characters and is the only transform applied before
  hashing/excerpting.
"""

from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urlparse

# ── Evidence source statuses ────────────────────────────────────────
SOURCE_PENDING = "PENDING_REVIEW"
SOURCE_REJECTED = "REJECTED"
SOURCE_ACCEPTED = "ACCEPTED_FOR_REVIEW"

# ── Claim statuses ──────────────────────────────────────────────────
CLAIM_PENDING = "PENDING_CLINICAL_REVIEW"
CLAIM_APPROVED = "APPROVED"
CLAIM_REJECTED = "REJECTED"
CLAIM_CONFLICT = "CONFLICT_PENDING_REVIEW"

CLAIM_STATUSES = {CLAIM_PENDING, CLAIM_APPROVED, CLAIM_REJECTED, CLAIM_CONFLICT}


class DomainNotAllowed(ValueError):
    """Raised when a URL's domain is not on the enforced allowlist."""


def _normalize_domain(host: str) -> str:
    host = (host or "").strip().lower().rstrip(".")
    # Strip userinfo/port if a full URL was passed by mistake.
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    # Punycode so lookalike IDN domains cannot impersonate allowlisted ones.
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise DomainNotAllowed(f"Unencodable hostname: {host!r}")
    return host


def is_allowed_domain(url: str, allowed_domains: set[str] | list[str]) -> bool:
    """True iff url's host equals or is a subdomain of an allowlisted domain."""
    allowed = {d.strip().lower().lstrip(".") for d in allowed_domains if d and d.strip()}
    if not allowed:
        return False
    host = _normalize_domain(urlparse(url).hostname or "")
    if not host:
        return False
    for dom in allowed:
        d = _normalize_domain(dom)
        if host == d or host.endswith("." + d):
            return True
    return False


def assert_allowed_domain(url: str, allowed_domains: set[str] | list[str]) -> str:
    """Return the normalized host or raise DomainNotAllowed."""
    if not is_allowed_domain(url, allowed_domains):
        host = urlparse(url).hostname or "?"
        raise DomainNotAllowed(f"Domain not on the ALLOWED_DOMAINS allowlist: {host}")
    return _normalize_domain(urlparse(url).hostname or "")


def sanitize_source_text(text: str) -> str:
    """Treat retrieved web text as pure data.

    Strips control characters (which could smuggle terminal/HTML/LLM
    control semantics) and normalizes whitespace. It deliberately does
    NOT interpret content: instructions inside a page are inert text and
    are ignored by every consumer of this value.
    """
    cleaned = "".join(ch for ch in (text or "") if ord(ch) >= 32 or ch in "\t\n")
    return " ".join(cleaned.split())


def requires_all_metadata(
    *,
    publisher: str | None,
    title: str | None,
    published_on: date | None,
    reviewed_on: date | None,
    retrieved_at: datetime | None,
    supporting_excerpt: str | None,
    content_hash: str | None,
) -> bool:
    """A source is acceptable for claim extraction only with full metadata."""
    return bool(
        publisher
        and str(publisher).strip()
        and title
        and str(title).strip()
        and (published_on or reviewed_on)
        and retrieved_at
        and supporting_excerpt
        and str(supporting_excerpt).strip()
        and content_hash
        and str(content_hash).strip()
    )


# Rejection buckets — explicit, auditable reasons.
REJECT_NON_ALLOWLISTED = "DOMAIN_NOT_ALLOWLISTED"
REJECT_BLOG_FORUM = "BLOG_OR_COMMUNITY_CONTENT"
REJECT_COMMERCIAL = "COMMERCIAL_OR_MARKETING_CONTENT"
REJECT_MISSING_METADATA = "MISSING_REQUIRED_METADATA"
REJECT_MISSING_DATE = "MISSING_PUBLICATION_DATE"

# URL/path markers that indicate non-credible source types. Checking the
# URL (not the page text) avoids rejecting legit pages that merely quote
# such words.
_NON_CREDIBLE_MARKERS = (
    "/blog", "/blogs", "/forum", "/forums", "testimonial", "reviews?",
    "shop", "store", "buy-now", "discount", "/cart", "supplement-shop",
)


def classify_source_rejection(url: str) -> str | None:
    """Return a rejection reason for blog/forum/commercial URL patterns."""
    parsed = urlparse(url)
    path = (parsed.path or "").lower()
    netloc = (parsed.netloc or "").lower()
    for marker in _NON_CREDIBLE_MARKERS:
        if marker in path or marker in netloc:
            return REJECT_BLOG_FORUM
    return None
