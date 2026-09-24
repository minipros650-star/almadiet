"""AlmaDiet — File upload/download router (/api/v1/files).

Private files live in the ``user-private`` bucket; ownership is enforced by
combining the validated token's user id (server-derived path prefix) with
Supabase Storage RLS. Downloads return short-lived signed URLs — never
permanent ones. Metadata is stored in ``user_files`` (Postgres).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.user_file import UserFile
from app.services import storage_service

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload an image to the caller's private bucket.

    The storage path is generated from the validated token's user id — a
    caller can never place a file under another user's prefix.
    """
    data = await file.read()
    meta = await storage_service.upload_user_file(current_user.id, file, data)

    row = UserFile(
        user_id=current_user.id,
        bucket=meta["bucket"],
        object_path=meta["object_path"],
        content_type=meta["content_type"],
        size_bytes=meta["size_bytes"],
    )
    db.add(row)
    await db.flush()
    return {
        "id": str(row.id),
        "bucket": row.bucket,
        "object_path": row.object_path,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
    }


@router.get("/{file_id}/url")
async def get_file_url(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Short-lived signed URL for one of the caller's own private files."""
    try:
        fid = uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    result = await db.execute(
        select(UserFile).where(UserFile.id == fid, UserFile.user_id == current_user.id)
    )
    row = result.scalar_one_or_none()
    if row is None or row.bucket != settings.USER_PRIVATE_BUCKET:
        # 404 (not 403) — do not reveal other users' file ids exist.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return {
        "url": storage_service.signed_url_for_private_object(row.object_path),
        "expires_in": storage_service.SIGNED_URL_EXPIRES_SECONDS,
        "content_type": row.content_type,
    }


@router.get("")
async def list_my_files(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserFile)
        .where(UserFile.user_id == current_user.id)
        .order_by(UserFile.created_at.desc())
        .limit(100)
    )
    return [
        {
            "id": str(r.id),
            "bucket": r.bucket,
            "object_path": r.object_path,
            "content_type": r.content_type,
            "size_bytes": r.size_bytes,
        }
        for r in result.scalars()
    ]
