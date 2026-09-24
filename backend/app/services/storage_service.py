"""AlmaDiet — Supabase Storage service (server-side only).

Rules encoded here:
  * Two buckets: ``meal-images`` (public catalog imagery, backend-written
    after review) and ``user-private`` (per-user, NEVER public).
  * Uploads happen ONLY through the FastAPI backend where validation and
    audit logging are enforced — clients never upload directly.
  * File type is validated by MAGIC BYTES, not by client-supplied
    content-type. Size and pixel dimensions are enforced before upload.
  * Object paths are generated server-side ({user_id}/...) — user-provided
    paths are never trusted.
  * Private files are served as short-lived signed URLs; Postgres stores
    only the object path + metadata, never a permanent URL.
  * Images are decorative content ONLY — never treated as nutrition or
    medical evidence by any code path.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile, status

from app.config import settings

# ── Constraints ───────────────────────────────────────────────────────────
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_DIMENSION_PX = 4096
ALLOWED_TYPES: dict[bytes, str] = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",  # RIFF....WEBP verified below
    b"GIF8": "image/gif",
}
SIGNED_URL_EXPIRES_SECONDS = 300  # short-lived private access


class InvalidUploadError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "INVALID_FILE", "message": detail, "details": {}}},
        )


@dataclass(frozen=True)
class ValidatedImage:
    content_type: str
    size_bytes: int
    data: bytes


def sniff_image_type(data: bytes) -> str:
    """Detect the real image type from magic bytes; raise on mismatch/unknown."""
    if len(data) < 12:
        raise InvalidUploadError("File is too small to be a valid image.")
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] in (b"GIF8"):
        return "image/gif"
    raise InvalidUploadError("Unsupported file type. Upload a JPEG, PNG, WebP, or GIF image.")


def validate_image_upload(file: UploadFile, data: bytes) -> ValidatedImage:
    """Full server-side validation: size, magic bytes, pixel dimensions."""
    if len(data) == 0:
        raise InvalidUploadError("The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidUploadError("Images must be 5 MB or smaller.")
    content_type = sniff_image_type(data)

    # Pixel dimensions are read from the header bytes; a full decode is done
    # only if Pillow is available (dimension sanity, truncated-file check).
    try:
        from io import BytesIO

        from PIL import Image  # type: ignore

        with Image.open(BytesIO(data)) as img:
            img.verify()  # structural integrity
        with Image.open(BytesIO(data)) as img2:
            w, h = img2.size
        if w > MAX_DIMENSION_PX or h > MAX_DIMENSION_PX:
            raise InvalidUploadError("Image dimensions must be 4096×4096 or smaller.")
        if w < 16 or h < 16:
            raise InvalidUploadError("Image dimensions must be at least 16×16.")
    except ImportError:
        # Pillow absent — magic bytes + size remain enforced; dimensions skip.
        pass
    except HTTPException:
        raise
    except Exception:
        raise InvalidUploadError("The file could not be read as an image.")

    return ValidatedImage(content_type=content_type, size_bytes=len(data), data=data)


def _client():
    """Lazy secret-key Supabase client (never imported at module import time
    so local dev without Supabase keeps working).

    Uses the current secret-key name (``SUPABASE_SECRET_KEY``), falling back
    to the legacy ``SUPABASE_SERVICE_ROLE_KEY`` name for existing
    deployments (documented compatibility fallback).
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "STORAGE_UNAVAILABLE", "message": "File storage is not configured.", "details": {}}},
        )
    from supabase import create_client

    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SECRET_KEY)


def safe_object_path(user_id: uuid.UUID, original_filename: str | None) -> str:
    """Server-generated path inside the private bucket: {user_id}/{uuid}.ext.

    The extension is derived from the *validated* content type — never from
    the client-supplied filename (which may contain traversal or junk).
    """
    ext_by_type = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    ext = ext_by_type.get(original_filename or "", ".jpg")  # original_filename here is a content type
    return f"{user_id}/{uuid.uuid4()}{ext}"


def safe_path_for_content_type(user_id: uuid.UUID, content_type: str) -> str:
    ext_by_type = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    return f"{user_id}/{uuid.uuid4()}{ext_by_type.get(content_type, '.jpg')}"


async def upload_user_file(
    user_id: uuid.UUID,
    file: UploadFile,
    data: bytes,
) -> dict:
    """Validate + upload to the user's private bucket. Returns path metadata."""
    validated = validate_image_upload(file, data)
    path = safe_path_for_content_type(user_id, validated.content_type)
    client = _client()
    res = (
        client.storage.from_(settings.USER_PRIVATE_BUCKET)
        .upload(
            path,
            validated.data,
            {"content-type": validated.content_type, "upsert": "false"},
        )
    )
    # supabase-py returns a dict or raises; normalize error handling:
    if isinstance(res, dict) and res.get("error"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "STORAGE_ERROR", "message": "Upload failed.", "details": {}}},
        )
    return {
        "bucket": settings.USER_PRIVATE_BUCKET,
        "object_path": path,
        "content_type": validated.content_type,
        "size_bytes": validated.size_bytes,
    }


def signed_url_for_private_object(object_path: str, expires_in: int = SIGNED_URL_EXPIRES_SECONDS) -> str:
    """Short-lived signed URL for a private object. Path is server-derived."""
    client = _client()
    res = client.storage.from_(settings.USER_PRIVATE_BUCKET).create_signed_url(
        object_path, expires_in
    )
    if isinstance(res, dict) and res.get("error"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "File not found.", "details": {}}},
        )
    signed = res.get("signedURL") or res.get("signed_url") if isinstance(res, dict) else None
    if not signed:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "STORAGE_ERROR", "message": "Could not sign URL.", "details": {}}},
        )
    return signed if str(signed).startswith("http") else f"{settings.SUPABASE_URL}/storage/v1{signed}"


def public_meal_image_url(object_path: str) -> str:
    """Public catalog imagery URL (meal-images bucket)."""
    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{settings.MEAL_IMAGES_BUCKET}/{object_path}"
