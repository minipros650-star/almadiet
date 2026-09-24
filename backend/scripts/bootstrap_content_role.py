"""AlmaDiet — grant or revoke content governance roles (operator command).

Review and publication authority is data: a row in ``content_role_grants``.
There is deliberately no HTTP surface for granting it, so privilege escalation
has no request path. This script is the documented bootstrap and administration
procedure.

The target user must already exist in ``users`` — i.e. they must have signed in
at least once, because the local row is provisioned from the validated Supabase
token on first sight. Grant by the email that row carries.

    python -m scripts.bootstrap_content_role list
    python -m scripts.bootstrap_content_role grant  --email clinician@example.org --role REVIEWER
    python -m scripts.bootstrap_content_role grant  --email lead@example.org      --role PUBLISHER --note "clinical lead"
    python -m scripts.bootstrap_content_role revoke --email clinician@example.org --role REVIEWER

A production database requires an explicit confirmation, because this command
changes who may publish medical content:

    CONTENT_ROLE_BOOTSTRAP_CONFIRM=I-ACCEPT-AUTHORITY-CHANGE \
        python -m scripts.bootstrap_content_role grant --email ... --role PUBLISHER
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import normalize_database_url, settings  # noqa: E402
from app.database import async_session_maker  # noqa: E402

PRODUCTION_PROJECT_REFS = ("ipquqyzlqugalmhfhfbt",)
PRODUCTION_CONFIRMATION = "I-ACCEPT-AUTHORITY-CHANGE"


class AuthorityChangeRefused(RuntimeError):
    """Raised when a role change would touch production without confirmation."""


def assert_target_allows_role_change(database_url: str, confirmation: str | None) -> None:
    """Fail closed unless a production authority change was explicitly accepted."""
    url = (database_url or "").lower()
    if not url:
        raise AuthorityChangeRefused("DATABASE_URL is not set — refusing to guess a target.")
    if any(ref in url for ref in PRODUCTION_PROJECT_REFS):
        if confirmation != PRODUCTION_CONFIRMATION:
            raise AuthorityChangeRefused(
                "Refusing to change content governance authority on the PRODUCTION "
                f"database. Re-run with CONTENT_ROLE_BOOTSTRAP_CONFIRM={PRODUCTION_CONFIRMATION} "
                "if the change is approved."
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage content governance roles.")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("grant", "revoke"):
        cmd = sub.add_parser(name, help=f"{name} a content role")
        cmd.add_argument("--email", required=True, help="email of an existing users row")
        cmd.add_argument("--role", required=True, choices=["REVIEWER", "PUBLISHER"])
        cmd.add_argument("--note", default=None, help="optional justification (grant only)")

    sub.add_parser("list", help="list role grants")
    return parser


async def _run(args: argparse.Namespace) -> int:
    from sqlalchemy import select

    from app.domain.content_roles import ContentRole
    from app.models.content_role import ContentRoleGrant
    from app.models.user import User
    from app.services import content_review_service

    async with async_session_maker() as db:
        if args.command == "list":
            rows = (
                await db.execute(select(ContentRoleGrant).order_by(ContentRoleGrant.granted_at))
            ).scalars().all()
            if not rows:
                print("No content role grants exist.")
                return 0
            for row in rows:
                state = "revoked" if row.revoked_at else "active"
                print(f"  {row.role:<10} user={row.user_id} {state} note={row.note or '-'}")
            return 0

        email = args.email.strip().lower()
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            print(
                f"No users row for {email}. The account must sign in once before a role "
                "can be granted (the row is provisioned from the validated token).",
                file=sys.stderr,
            )
            return 2

        role = ContentRole(args.role)
        if args.command == "grant":
            await content_review_service.grant_role(
                db,
                user_id=user.id,
                role=role,
                granted_by_label="scripts/bootstrap_content_role.py",
                note=args.note,
            )
            await db.commit()
            print(f"Granted {role.value} to {email} (user_id={user.id}).")
            return 0

        revoked = await content_review_service.revoke_role(db, user_id=user.id, role=role)
        await db.commit()
        print(
            f"Revoked {role.value} from {email}." if revoked
            else f"{email} did not hold an active {role.value} grant."
        )
        return 0 if revoked else 1


def main() -> int:
    args = _parser().parse_args()

    if os.getenv("DATABASE_URL"):
        settings.DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", ""))
        import importlib

        import app.database as database_module

        importlib.reload(database_module)
        global async_session_maker
        async_session_maker = database_module.async_session_maker

    if args.command != "list":
        try:
            assert_target_allows_role_change(
                settings.DATABASE_URL, os.getenv("CONTENT_ROLE_BOOTSTRAP_CONFIRM")
            )
        except AuthorityChangeRefused as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 3

    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
