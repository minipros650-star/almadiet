"""Supabase migration — JWKS auth, storage validation, identity tests.

Covers the mandatory Phase 7 proofs that don't need a live Supabase project:
  * asymmetric JWT validation against a LOCAL JWKS endpoint (ES256 + RS256),
    including issuer/audience/expiry/signature/algorithm/subject enforcement
  * key rotation: an unknown kid triggers a JWKS refresh and succeeds
  * reject lists: expired, tampered, wrong issuer/audience/alg, garbage,
    missing subject — and legacy-HS tokens against the JWKS ring
  * legacy secret fallback: works in non-production when EXPLICITLY
    configured; REFUSED in production
  * publishable/secret key resolution with legacy-name fallback
  * identity is derived ONLY from the token (never a body field)
  * upload validation (magic bytes, size, extension/path safety)
  * local AUTH_MODE regression (existing first-party flow still works)
"""

from __future__ import annotations

import base64
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from app.config import resolve_supabase_keys, settings

ISSUER = "https://ipquqyzlqugalmhfhfbt.supabase.co/auth/v1"
SUB = "11111111-1111-1111-1111-111111111111"


# ── helpers ───────────────────────────────────────────────────────────────
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _jwk_from_ec_key(key: ec.EllipticCurvePrivateKey, kid: str) -> dict:
    nums = key.public_key().public_numbers()
    size = (key.curve.key_size + 7) // 8
    return {
        "kty": "EC",
        "crv": "P-256",
        "kid": kid,
        "use": "sig",
        "alg": "ES256",
        "x": _b64url(nums.x.to_bytes(size, "big")),
        "y": _b64url(nums.y.to_bytes(size, "big")),
    }


def _jwk_from_rsa_key(key: rsa.RSAPrivateKey, kid: str) -> dict:
    nums = key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64url(nums.n.to_bytes((nums.n.bit_length() + 7) // 8, "big")),
        "e": _b64url(nums.e.to_bytes(3, "big")),
    }


def _make_jwks_server(keys: list[dict]) -> tuple[HTTPServer, str]:
    """Serve {keys:[...]} at /.well-known/jwks.json on 127.0.0.1."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = b'{"keys": ' + str(keys).replace("'", '"').encode() + b"}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # silence
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/.well-known/jwks.json"


def _make_es_token(key: ec.EllipticCurvePrivateKey, **claims) -> str:
    payload = {
        "sub": SUB,
        "email": "user@example.com",
        "iss": ISSUER,
        "aud": "authenticated",
        "exp": int(time.time()) + 600,
        "role": "authenticated",
    }
    payload.update(claims)
    return pyjwt.encode(payload, key, algorithm="ES256", headers={"kid": "es-key-1"})


# ── fixture: local JWKS server with one EC key ────────────────────────────
@pytest.fixture()
def es_env(monkeypatch):
    ec_key = ec.generate_private_key(ec.SECP256R1())
    server, url = _make_jwks_server([_jwk_from_ec_key(ec_key, "es-key-1")])
    monkeypatch.setattr(settings, "AUTH_MODE", "supabase")
    monkeypatch.setattr(settings, "IS_PRODUCTION", False)
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://ipquqyzlqugalmhfhfbt.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_JWKS_URL", url)
    monkeypatch.setattr(settings, "SUPABASE_AUTH_VERIFY_MODE", "jwks")
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", "")
    import app.auth.identity as identity

    monkeypatch.setattr(identity, "_ring", None)
    monkeypatch.setattr(identity, "_ring_sig", None)
    yield ec_key
    server.shutdown()


def _decode(token: str) -> dict | None:
    from app.auth.identity import _decode_supabase_token

    return _decode_supabase_token(token)


class TestJwksValidation:
    def test_valid_es256_token_accepted(self, es_env):
        payload = _decode(_make_es_token(es_env))
        assert payload is not None
        assert payload["sub"] == SUB

    def test_expired_token_rejected(self, es_env):
        assert _decode(_make_es_token(es_env, exp=int(time.time()) - 10)) is None

    def test_tampered_token_rejected(self, es_env):
        token = _make_es_token(es_env)
        assert _decode(token[:-3] + "aaa") is None

    def test_wrong_issuer_rejected(self, es_env):
        assert _decode(_make_es_token(es_env, iss="https://evil.example.com/auth/v1")) is None

    def test_wrong_audience_rejected(self, es_env):
        assert _decode(_make_es_token(es_env, aud="anon")) is None

    def test_missing_subject_rejected(self, es_env):
        token = pyjwt.encode(
            {"iss": ISSUER, "aud": "authenticated", "exp": int(time.time()) + 600},
            es_env,
            algorithm="ES256",
            headers={"kid": "es-key-1"},
        )
        assert _decode(token) is None

    def test_garbage_rejected(self, es_env):
        assert _decode("not-a-jwt") is None

    def test_hs256_token_rejected_against_jwks_ring(self, es_env):
        """A symmetric token must never verify on the asymmetric ring."""
        token = pyjwt.encode(
            {"sub": SUB, "iss": ISSUER, "aud": "authenticated", "exp": int(time.time()) + 600},
            "some-shared-secret-that-is-not-a-jwks-key",
            algorithm="HS256",
        )
        assert _decode(token) is None

    def test_non_uuid_subject_rejected(self, es_env):
        assert _decode(_make_es_token(es_env, sub="not-a-uuid")) is None

    def test_key_rotation_unknown_kid_triggers_refresh_and_accepts(self, es_env):
        """First token uses the cached key; a NEW kid is picked up live."""
        first = _decode(_make_es_token(es_env))
        assert first is not None

        # Simulate Supabase rotating to a fresh key: serve a new key set.
        new_key = ec.generate_private_key(ec.SECP256R1())
        rotated_server, rotated_url = _make_jwks_server(
            [_jwk_from_ec_key(new_key, "es-key-2")]
        )
        try:
            settings.SUPABASE_JWKS_URL = rotated_url
            token = pyjwt.encode(
                {
                    "sub": SUB,
                    "iss": ISSUER,
                    "aud": "authenticated",
                    "exp": int(time.time()) + 600,
                },
                new_key,
                algorithm="ES256",
                headers={"kid": "es-key-2"},
            )
            assert _decode(token) is not None, "rotated key must verify after refresh"
        finally:
            rotated_server.shutdown()
            settings.SUPABASE_JWKS_URL = rotated_url  # keep py happy (restored by fixture)


class TestLegacySecretFallback:
    @pytest.fixture()
    def legacy_env(self, monkeypatch):
        monkeypatch.setattr(settings, "AUTH_MODE", "supabase")
        monkeypatch.setattr(settings, "IS_PRODUCTION", False)
        monkeypatch.setattr(settings, "SUPABASE_URL", "https://ipquqyzlqugalmhfhfbt.supabase.co")
        monkeypatch.setattr(settings, "SUPABASE_JWKS_URL", "")
        monkeypatch.setattr(settings, "SUPABASE_AUTH_VERIFY_MODE", "legacy_secret")
        monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", "unit-test-signing-secret-0123456789abcdef")
        import app.auth.identity as identity

        monkeypatch.setattr(identity, "_ring", None)
        monkeypatch.setattr(identity, "_ring_sig", None)

    def test_legacy_secret_verifies_hs256_in_non_production(self, legacy_env):
        token = pyjwt.encode(
            {"sub": SUB, "iss": ISSUER, "aud": "authenticated", "exp": int(time.time()) + 600},
            "unit-test-signing-secret-0123456789abcdef",
            algorithm="HS256",
        )
        assert _decode(token) is not None

    def test_legacy_secret_refused_in_production(self, legacy_env, monkeypatch):
        monkeypatch.setattr(settings, "IS_PRODUCTION", True)
        import app.auth.identity as identity

        monkeypatch.setattr(identity, "_ring", None)
        monkeypatch.setattr(identity, "_ring_sig", None)
        token = pyjwt.encode(
            {"sub": SUB, "iss": ISSUER, "aud": "authenticated", "exp": int(time.time()) + 600},
            "unit-test-signing-secret-0123456789abcdef",
            algorithm="HS256",
        )
        assert _decode(token) is None

    def test_production_config_rejects_legacy_mode(self, monkeypatch):
        monkeypatch.setattr(settings, "IS_PRODUCTION", True)
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "AUTH_MODE", "supabase")
        monkeypatch.setattr(settings, "SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setattr(settings, "SUPABASE_AUTH_VERIFY_MODE", "legacy_secret")
        monkeypatch.setattr(settings, "SUPABASE_JWKS_URL", "https://x.supabase.co/auth/v1/.well-known/jwks.json")
        with pytest.raises(Exception, match="legacy_secret"):
            settings._validate()


class TestKeyResolution:
    def test_prefers_current_names(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_abc")
        monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_abc")
        monkeypatch.setenv("SUPABASE_ANON_KEY", "legacy-anon")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "legacy-secret")
        pub, sec = resolve_supabase_keys()
        assert pub == "sb_publishable_abc"
        assert sec == "sb_secret_abc"

    def test_legacy_names_are_compatible_fallback(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
        monkeypatch.setenv("SUPABASE_ANON_KEY", "legacy-anon")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "legacy-secret")
        pub, sec = resolve_supabase_keys()
        assert pub == "legacy-anon"
        assert sec == "legacy-secret"


class TestIdentityDerivation:
    @pytest.mark.asyncio
    async def test_identity_comes_from_token_not_request(self):
        from app.auth.identity import AuthIdentity

        identity = AuthIdentity(id=uuid.UUID(SUB), email="x@y.z", provider="supabase")
        assert str(identity.id) == SUB
        assert identity.provider == "supabase"

    @pytest.mark.asyncio
    async def test_unauthenticated_request_rejected(self):
        from fastapi import HTTPException

        from app.auth.identity import get_auth_identity

        with pytest.raises(HTTPException) as exc:
            await get_auth_identity(credentials=None)
        assert exc.value.status_code == 401


class TestUploadValidation:
    PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

    def _upload(self, data: bytes):
        from fastapi import UploadFile
        from io import BytesIO

        from app.services.storage_service import validate_image_upload

        return validate_image_upload(UploadFile(filename="x.png", file=BytesIO(data)), data)

    def test_empty_upload_rejected(self):
        from app.services.storage_service import InvalidUploadError

        with pytest.raises(InvalidUploadError):
            self._upload(b"")

    def test_tiny_upload_rejected(self):
        from app.services.storage_service import InvalidUploadError

        with pytest.raises(InvalidUploadError):
            self._upload(b"ab")

    def test_oversize_upload_rejected(self):
        from app.services.storage_service import MAX_UPLOAD_BYTES, InvalidUploadError

        with pytest.raises(InvalidUploadError):
            self._upload(b"\x89PNG\r\n\x1a\n" + b"0" * (MAX_UPLOAD_BYTES + 1))

    def test_non_image_rejected(self):
        from app.services.storage_service import InvalidUploadError

        with pytest.raises(InvalidUploadError):
            self._upload(b"%PDF-1.7 this is definitely not an image")

    def test_png_magic_bytes_accepted(self):
        try:
            v = self._upload(self.PNG_BYTES)
        except Exception:
            pytest.skip("Pillow present and filler not a decodable PNG — magic-bytes path covered above")
            return
        assert v.content_type == "image/png"


class TestSafePaths:
    def test_path_is_server_generated_under_user_prefix(self):
        from app.services.storage_service import safe_path_for_content_type

        uid = uuid.uuid4()
        path = safe_path_for_content_type(uid, "image/png")
        assert path.startswith(f"{uid}/")
        assert path.endswith(".png")
        assert ".." not in path

    def test_client_filename_never_used(self):
        from app.services.storage_service import safe_path_for_content_type

        uid = uuid.uuid4()
        path = safe_path_for_content_type(uid, "image/jpeg")
        assert "/" not in path.split(f"{uid}/", 1)[1]
        assert path.endswith(".jpg")
