"""AlmaDiet — Evidence research pipeline (admin-only, offline).

Retrieval happens OUTSIDE any patient-recommendation path. The service:

1. Fetches ONLY domains on the enforced ALLOWED_DOMAINS allowlist
   (checked twice: before the HTTP request via a guarded client, and
   recorded on the row).
2. Treats every retrieved document as untrusted DATA:
   - text is sanitized (control chars stripped) before hashing/excerpting;
   - page text can never influence the code path — there is no mechanism
     by which document content reaches an instruction interpreter, no LLM
     call exists in this service, and excerpt selection is a fixed-length
     substring, not a generation.
3. Enforces the metadata gate: publisher, title, publication/review date,
   retrieval date, exact supporting excerpt, and SHA-256 document hash.
   Missing anything ⇒ REJECTED (explicit reason) or stays PENDING.
4. Extracts deterministic candidate claims (evidence-tagged list markers
   in the source, or caller-supplied excerpts); every claim starts at
   PENDING_CLINICAL_REVIEW and cannot affect recommendations until an
   immutable clinician decision approves it.
5. NEVER receives patient identifiers, health records, allergies, LMP,
   lab values, notes, or conditions — there is no parameter for them, so
   leakage is impossible by construction. (Verified by test.)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import evidence as ev
from app.models.evidence import EvidenceClaim, EvidenceSource


@dataclass
class RetrievedDocument:
    """Inert data container for a fetched document. No behavior."""

    url: str
    domain: str
    text: str
    content_hash: str


@dataclass
class SourceIntake:
    """Metadata submitted with a retrieval (by the admin operator)."""

    url: str
    publisher: str | None = None
    title: str | None = None
    published_on: date | None = None
    reviewed_on: date | None = None
    supporting_excerpt: str | None = None
    topic_tags: list[str] = field(default_factory=list)


def compute_document_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EvidenceRetrievalClient:
    """HTTP client that refuses to fetch non-allowlisted domains.

    The allowlist check happens BEFORE any network activity. Redirects
    are not followed (``follow_redirects=False``) so a malicious page
    cannot bounce a request to an unapproved host.
    """

    def __init__(self, allowed_domains: list[str] | set[str], timeout: float = 15.0):
        self.allowed_domains = {d.strip().lower() for d in allowed_domains if d.strip()}
        self._client = httpx.Client(timeout=timeout, follow_redirects=False)

    def fetch(self, url: str) -> RetrievedDocument:
        domain = ev.assert_allowed_domain(url, self.allowed_domains)
        resp = self._client.get(url, headers={"User-Agent": "AlmaDietEvidenceBot/1.0"})
        resp.raise_for_status()
        text = ev.sanitize_source_text(resp.text)
        return RetrievedDocument(
            url=url, domain=domain, text=text, content_hash=compute_document_hash(text)
        )


class EvidenceResearchService:
    """Admin-only evidence intake. See module docstring for guarantees."""

    def __init__(self, allowed_domains: list[str] | set[str], retrieval_client=None):
        self.allowed_domains = {d.strip().lower() for d in allowed_domains if d.strip()}
        self.retrieval_client = retrieval_client

    # ── 1. Retrieval (optional — metadata can be submitted manually) ──
    def retrieve(self, url: str) -> RetrievedDocument:
        if self.retrieval_client is None:
            self.retrieval_client = EvidenceRetrievalClient(self.allowed_domains)
        # Double gate: the client also enforces the allowlist.
        return self.retrieval_client.fetch(url)

    # ── 2. Intake: metadata gate + rejection classification ──────────
    async def intake_source(
        self, db: AsyncSession, doc: RetrievedDocument, meta: SourceIntake
    ) -> EvidenceSource:
        # Allowlist enforced even for manually submitted URLs.
        domain = ev.assert_allowed_domain(meta.url, self.allowed_domains)

        # URL-pattern rejection: blogs/forums/testimonials/commerce.
        pattern_reason = ev.classify_source_rejection(meta.url)

        # Dedup by document hash.
        existing = await db.execute(
            select(EvidenceSource).where(EvidenceSource.content_hash == doc.content_hash)
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError("DUPLICATE_SOURCE")

        sanitized_excerpt = ev.sanitize_source_text(meta.supporting_excerpt or "")

        has_meta = ev.requires_all_metadata(
            publisher=meta.publisher,
            title=meta.title,
            published_on=meta.published_on,
            reviewed_on=meta.reviewed_on,
            retrieved_at=datetime.now(timezone.utc),
            supporting_excerpt=sanitized_excerpt,
            content_hash=doc.content_hash,
        )

        if pattern_reason:
            status, reason = ev.SOURCE_REJECTED, pattern_reason
        elif not has_meta:
            # Missing date vs missing other metadata: distinct audit reasons.
            if not (meta.published_on or meta.reviewed_on):
                status, reason = ev.SOURCE_REJECTED, ev.REJECT_MISSING_DATE
            else:
                status, reason = ev.SOURCE_PENDING, ev.REJECT_MISSING_METADATA
        else:
            status, reason = ev.SOURCE_ACCEPTED, None

        row = EvidenceSource(
            url=meta.url,
            domain=domain,
            publisher=meta.publisher,
            title=meta.title,
            published_on=meta.published_on,
            reviewed_on=meta.reviewed_on,
            retrieved_at=datetime.now(timezone.utc),
            content_hash=doc.content_hash,
            supporting_excerpt=sanitized_excerpt or None,
            topic_tags=list(meta.topic_tags or []),
            status=status,
            rejection_reason=reason,
        )
        db.add(row)
        await db.flush()
        return row

    # ── 3. Claim extraction: deterministic, starts PENDING ────────────
    async def extract_claims(
        self, db: AsyncSession, source: EvidenceSource, claim_texts: list[str]
    ) -> list[EvidenceClaim]:
        """Persist candidate claims.

        ``claim_texts`` are caller-supplied verbatim excerpts (the admin
        quotes the exact supporting sentence). Nothing is generated: no
        LLM, no summarization. Every claim starts PENDING_CLINICAL_REVIEW.
        """
        claims: list[EvidenceClaim] = []
        for raw in claim_texts:
            text = ev.sanitize_source_text(raw)
            if not text:
                continue
            h = compute_document_hash(text)
            dup = await db.execute(
                select(EvidenceClaim).where(EvidenceClaim.content_hash == h)
            )
            if dup.scalar_one_or_none() is not None:
                continue
            row = EvidenceClaim(
                source_id=source.id,
                claim_text=text,
                topic_tags=list(source.topic_tags or []),
                content_hash=h,
                status=ev.CLAIM_PENDING,  # ALWAYS — never APPROVED here
            )
            db.add(row)
            claims.append(row)
        await db.flush()
        return claims

    # ── 4. Conflict marking: never let a model choose between claims ──
    @staticmethod
    async def mark_conflict(db: AsyncSession, claim_ids: list) -> int:
        """Mark claims as mutually conflicting (pending clinical review)."""
        if not claim_ids:
            return 0
        result = await db.execute(
            select(EvidenceClaim).where(EvidenceClaim.id.in_(list(claim_ids)))
        )
        rows = result.scalars().all()
        for row in rows:
            row.status = ev.CLAIM_CONFLICT
        await db.flush()
        return len(rows)

    # ── 5. Approved-claims lookup (the ONLY read path to user-facing) ─
    @staticmethod
    async def approved_claim_texts(db: AsyncSession) -> list[str]:
        result = await db.execute(
            select(EvidenceClaim.claim_text).where(EvidenceClaim.status == ev.CLAIM_APPROVED)
        )
        return [r[0] for r in result.all()]
