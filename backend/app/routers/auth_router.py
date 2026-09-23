"""AlmaDiet — Auth Router (/api/v1/auth)."""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import (
    create_access_token,
    get_current_user,
    issue_refresh_token,
    revoke_all_user_tokens,
    revoke_token,
    rotate_refresh_token,
)
from app.config import settings
from app.core.rate_limit import login_rate_limiter, register_rate_limiter
from app.database import get_db
from app.models.user import User
from app.schemas.errors import ErrorCode, envelope
from app.schemas.user import (
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdate,
)
from app.services import audit_service
from app.services.user_service import authenticate_user, register_user, update_user

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

GENERIC_LOGIN_ERROR = "Invalid email or password"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()[:32]


def _token_pair(user: User, access: str, refresh: str) -> TokenPair:
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister,
    request: Request,
    db: AsyncSession = Depends(get_db),
    response: Response = None,  # type: ignore[assignment]
):
    ip = _client_ip(request)
    if not register_rate_limiter.allow(f"register:{ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=envelope(ErrorCode.RATE_LIMITED, "Too many attempts. Try again later."),
        )
    try:
        user = await register_user(db, data)
    except ValueError as e:
        code = ErrorCode.CONFLICT if "already" in str(e).lower() else ErrorCode.INVALID_INPUT
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT if code == ErrorCode.CONFLICT else status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=envelope(code, str(e)),
        )

    access = create_access_token(user.id)
    refresh = await issue_refresh_token(db, user.id)
    await audit_service.record_event(
        db, audit_service.EventCodes.REGISTERED, user.id, {"ip_hash": _hash_ip(ip)}
    )
    return _token_pair(user, access, refresh)


@router.post("/login", response_model=TokenPair)
async def login(
    data: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = _client_ip(request)
    if not login_rate_limiter.allow(f"login:{ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=envelope(ErrorCode.RATE_LIMITED, "Too many login attempts. Try again later."),
        )

    user, auth_status = await authenticate_user(db, data.email, data.password)

    if auth_status == "locked":
        await audit_service.record_event(
            db, audit_service.EventCodes.LOGIN_LOCKOUT, user.id if user else None, {}
        )
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=envelope(ErrorCode.LOCKED, "Account temporarily locked. Try again in 15 minutes."),
        )

    if user is None or auth_status != "ok":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=envelope(ErrorCode.UNAUTHORIZED, GENERIC_LOGIN_ERROR),
        )

    access = create_access_token(user.id)
    refresh = await issue_refresh_token(db, user.id)
    await audit_service.record_event(
        db, audit_service.EventCodes.LOGIN_SUCCESS, user.id, {"ip_hash": _hash_ip(ip)}
    )
    return _token_pair(user, access, refresh)


@router.post("/refresh", response_model=TokenPair)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    result = await rotate_refresh_token(db, data.refresh_token)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=envelope(ErrorCode.UNAUTHORIZED, "Session expired. Please sign in again."),
        )
    user, new_refresh = result
    await audit_service.record_event(db, audit_service.EventCodes.TOKEN_REFRESHED, user.id, {})
    access = create_access_token(user.id)
    return _token_pair(user, access, new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: LogoutRequest, db: AsyncSession = Depends(get_db)):
    await revoke_token(db, data.refresh_token)
    return None


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await revoke_all_user_tokens(db, current_user.id)
    await audit_service.record_event(
        db, audit_service.EventCodes.LOGOUT_ALL, current_user.id, {"sessions": count}
    )
    return None


@router.get("/me", response_model=UserResponse)
async def get_profile(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await update_user(db, current_user.id, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=envelope(ErrorCode.INVALID_INPUT, str(e)),
        )
    changed = list(data.model_dump(exclude_unset=True).keys())
    await audit_service.record_event(
        db, audit_service.EventCodes.PROFILE_UPDATED, current_user.id, {"fields": changed}
    )
    return UserResponse.model_validate(user)


# Back-compat alias: PUT kept for older clients during migration window.
@router.put("/me", response_model=UserResponse, include_in_schema=False)
async def update_profile_put(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await update_profile(data, current_user, db)
