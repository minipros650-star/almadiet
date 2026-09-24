"""AlmaDiet — Evidence Router (/api/v1/evidence).

Admin/reviewer-only. Every endpoint requires:
  * the ``ENABLE_EVIDENCE_PIPELINE`` feature flag (default OFF), and
  * a database-granted content staff role (see app/auth/content_authz.py).

There is deliberately NO endpoint that turns evidence into user-facing
recommendations: approved claims are consumed internally by the
explanation builder only. Patient data has no parameter on any route.
"""

from __future__ import annotations

from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.content_authz import require_reviewer
from app.config import settings
from app.database import get_db
from app.domain import evidence as ev
from app.models.evidence import (
    ClinicalReviewDecision,
    EvidenceClaim,
    EvidenceSource,
)
from app.services.evidence_research_service import (
    EvidenceResearchService,
    RetrievedDocument,
    SourceIntake,
    compute_document_hash,
)

router = APIRouter(prefix="/api/v1/evidence", tags=["Evidence Pipeline (admin)"])


def require_evidence_pipeline():
    if not settings.ENABLE_EVIDENCE_PIPELINE:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Evidence pipeline is disabled (ENABLE_EVIDENCE_PIPELINE=false)",
        )


# require_reviewer (imported above) is the reviewer gate for these routes:
# a database-granted content role, resolved from the validated token.


class SourceIntakeRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=1000)
    publisher: str | None = Field(None, max_length=255)
    title: str | None = Field(None, max_length=500)
    published_on: date_type | None = None
    reviewed_on: date_type | None = None
    supporting_excerpt: str | None = Field(None, max_length=5000)
    topic_tags: list[str] = Field(default_factory=list, max_length=20)
    # Optional pasted document text (used for hashing when retrieval is off).
    document_text: str | None = Field(None, max_length=200_000)
    fetch: bool = Field(False, description="Live-retrieve the URL (flag-gated client)")


class ClaimsExtractRequest(BaseModel):
    claim_texts: list[str] = Field(..., min_length=1, max_length=50)


class ClaimDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(APPROVED|REJECTED)$")
    rationale: str | None = Field(None, max_length=2000)


class ConflictRequest(BaseModel):
    claim_ids: list[str] = Field(..., min_length=2, max_length=20)


@router.post("/sources", status_code=201, dependencies=[Depends(require_evidence_pipeline)])
async def intake_source(
    data: SourceIntakeRequest,
    db: AsyncSession = Depends(get_db),
    reviewer: object = Depends(require_reviewer),
):
    """Intake one allowlisted source. Rejection is the default outcome."""
    service = EvidenceResearchService(settings.ALLOWED_DOMAINS)
    # Allowlist check FIRST — before any fetch attempt.
    ev.assert_allowed_domain(data.url, settings.ALLOWED_DOMAINS)
    if data.fetch:
        doc = service.retrieve(data.url)
    elif data.document_text:
        text = ev.sanitize_source_text(data.document_text)
        doc = RetrievedDocument(
            url=data.url,
            domain=ev.assert_allowed_domain(data.url, settings.ALLOWED_DOMAINS),
            text=text,
            content_hash=compute_document_hash(text),
        )
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Provide document_text or fetch=true")

    meta = SourceIntake(
        url=data.url,
        publisher=data.publisher,
        title=data.title,
        published_on=data.published_on,
        reviewed_on=data.reviewed_on,
        supporting_excerpt=data.supporting_excerpt,
        topic_tags=data.topic_tags,
    )
    try:
        row = await service.intake_source(db, doc, meta)
    except ValueError as e:
        if str(e) == "DUPLICATE_SOURCE":
            raise HTTPException(status.HTTP_409_CONFLICT, detail="DUPLICATE_SOURCE")
        raise
    return {
        "id": str(row.id),
        "status": row.status,
        "rejection_reason": row.rejection_reason,
        "content_hash": row.content_hash,
    }


@router.post("/sources/{source_id}/claims", status_code=201, dependencies=[Depends(require_evidence_pipeline)])
async def extract_claims(
    source_id: str,
    data: ClaimsExtractRequest,
    db: AsyncSession = Depends(get_db),
    reviewer: object = Depends(require_reviewer),
):
    row = await db.get(EvidenceSource, source_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Source not found")
    if row.status == ev.SOURCE_REJECTED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Source was rejected")
    service = EvidenceResearchService(settings.ALLOWED_DOMAINS)
    claims = await service.extract_claims(db, row, data.claim_texts)
    return {"count": len(claims), "statuses": [c.status for c in claims]}


@router.post("/claims/conflict", status_code=200, dependencies=[Depends(require_evidence_pipeline)])
async def mark_conflict(
    data: ConflictRequest,
    db: AsyncSession = Depends(get_db),
    reviewer: object = Depends(require_reviewer),
):
    """Flag conflicting claims — clinicians resolve conflicts, never the model."""
    count = await EvidenceResearchService.mark_conflict(db, data.claim_ids)
    return {"marked": count}


@router.post("/claims/{claim_id}/decide", status_code=200, dependencies=[Depends(require_evidence_pipeline)])
async def decide_claim(
    claim_id: str,
    data: ClaimDecisionRequest,
    db: AsyncSession = Depends(get_db),
    reviewer: object = Depends(require_reviewer),
):
    """Record an immutable clinical decision (insert-only; supersede via new row)."""
    claim = await db.get(EvidenceClaim, claim_id)
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Claim not found")
    if claim.status == ev.CLAIM_CONFLICT and data.decision == "APPROVED":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Conflicting claims require explicit conflict resolution first",
        )
    decision = ClinicalReviewDecision(
        claim_id=claim.id,
        decision=data.decision,
        reviewed_by=getattr(getattr(reviewer, "user", None), "email", None) or reviewer.label,
        rationale=data.rationale,
    )
    db.add(decision)
    await db.flush()
    claim.status = ev.CLAIM_APPROVED if data.decision == "APPROVED" else ev.CLAIM_REJECTED
    await db.flush()
    return {"claim_id": str(claim.id), "status": claim.status, "decision_id": str(decision.id)}


@router.get("/claims", status_code=200, dependencies=[Depends(require_evidence_pipeline)])
async def list_claims(
    claim_status: str | None = None,
    db: AsyncSession = Depends(get_db),
    reviewer: object = Depends(require_reviewer),
):
    stmt = select(EvidenceClaim).order_by(EvidenceClaim.created_at.desc()).limit(100)
    if claim_status:
        stmt = stmt.where(EvidenceClaim.status == claim_status)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "count": len(rows),
        "claims": [
            {"id": str(c.id), "status": c.status, "claim_text": c.claim_text[:200]} for c in rows
        ],
    }
