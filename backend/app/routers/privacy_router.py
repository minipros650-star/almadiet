"""AlmaDiet — Privacy Router (/api/v1/privacy)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.errors import ErrorCode, envelope
from app.services import audit_service, privacy_service

router = APIRouter(prefix="/api/v1/privacy", tags=["Privacy"])


@router.get("/export")
async def export_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    bundle = await privacy_service.export_user_data(db, current_user.id)
    bundle["exported_at"] = datetime.now(timezone.utc).isoformat()
    await audit_service.record_event(db, audit_service.EventCodes.DATA_EXPORTED, current_user.id, {})
    return JSONResponse(
        content=bundle,
        headers={
            "Content-Disposition": 'attachment; filename="almadiet-data-export.json"',
        },
    )


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await privacy_service.delete_account(db, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=envelope(ErrorCode.NOT_FOUND, "Account not found"),
        )
    return None
