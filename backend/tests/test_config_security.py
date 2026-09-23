"""CRITICAL TESTS 14 & 15 — production config rejects wildcard CORS and
fails startup when required secrets are missing."""

from __future__ import annotations

import pytest

import app.config as config_module


def _make_settings(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return config_module.Settings()


def test_production_requires_jwt_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com")
    with pytest.raises(config_module.ConfigError, match="JWT_SECRET_KEY"):
        _make_settings(monkeypatch)


def test_production_rejects_known_default_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", "almadiet-super-secret-key-change-in-production")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com")
    with pytest.raises(config_module.ConfigError, match="insecure"):
        _make_settings(monkeypatch)


def test_production_rejects_wildcard_cors(monkeypatch):
    """TEST 14."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    with pytest.raises(config_module.ConfigError, match="Wildcard CORS"):
        _make_settings(monkeypatch)


def test_production_rejects_debug(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    with pytest.raises(config_module.ConfigError, match="DEBUG"):
        _make_settings(monkeypatch)


def test_production_valid_config_passes(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", "y" * 48)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com,https://admin.example.com")
    s = _make_settings(monkeypatch)
    assert s.ALLOWED_ORIGINS == ["https://app.example.com", "https://admin.example.com"]


def test_development_generates_ephemeral_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    s = _make_settings(monkeypatch)
    assert len(s.JWT_SECRET_KEY) >= 32
