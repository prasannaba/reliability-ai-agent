"""P0 security: backend credential manager + write-auth + input validation."""

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.append(str(Path(__file__).resolve().parents[1]))

import src.common.credential_store as store
import src.host.app as main
from src.host.app import (
    LlmConfigUpdate,
    llm_api_key,
    llm_config_snapshot,
    require_write_auth,
    validate_base_url,
)


@pytest.fixture
def isolated_store(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_KEY_PATH", tmp_path / ".credential.key")
    monkeypatch.setattr(store, "_SECRET_PATH", tmp_path / ".llm_secret.enc")
    monkeypatch.delenv("CREDENTIAL_KEY", raising=False)
    yield tmp_path


def test_credential_roundtrip(isolated_store):
    assert store.has_api_key() is False
    store.set_api_key("sk-test-123")
    assert store.has_api_key() is True
    assert store.get_api_key() == "sk-test-123"
    # Secret file must not be plaintext JSON and must be owner-only.
    raw = (isolated_store / ".llm_secret.enc").read_bytes()
    assert b"sk-test-123" not in raw or not store._HAS_FERNET
    store.delete_api_key()
    assert store.has_api_key() is False
    assert store.get_api_key() == ""


def test_empty_set_revokes(isolated_store):
    store.set_api_key("sk-test-123")
    store.set_api_key("   ")
    assert store.has_api_key() is False


def test_llm_api_key_prefers_store_over_env(monkeypatch, isolated_store):
    monkeypatch.setenv("LLM_API_KEY", "env-key")
    monkeypatch.setattr(main, "_LLM_CONFIG_OVERRIDE", {})
    store.set_api_key("stored-key")
    assert llm_api_key() == "stored-key"
    store.delete_api_key()
    assert llm_api_key() == "env-key"


def test_snapshot_never_contains_secret(monkeypatch, isolated_store):
    monkeypatch.setattr(main, "_LLM_CONFIG_OVERRIDE", {"provider": "custom", "baseUrl": "http://x"})
    store.set_api_key("sk-secret")
    snapshot = llm_config_snapshot()
    assert snapshot["hasApiKey"] is True
    assert "sk-secret" not in str(snapshot)
    assert "apiKey" not in snapshot


def test_config_update_rejects_oversize_key():
    with pytest.raises(ValidationError):
        LlmConfigUpdate(apiKey="x" * 4097)
    with pytest.raises(ValidationError):
        LlmConfigUpdate(baseUrl="http://x/" + "y" * 2048)
    with pytest.raises(ValidationError):
        LlmConfigUpdate(systemPrompt="z" * 4001)


def test_validate_base_url_rejects_bad_schemes_and_metadata():
    with pytest.raises(HTTPException):
        validate_base_url("file:///etc/passwd")
    with pytest.raises(HTTPException):
        validate_base_url("http://169.254.169.254/latest/meta-data/")
    assert validate_base_url("https://api.openai.com/v1/") == "https://api.openai.com/v1"


def test_write_auth_open_without_token(monkeypatch):
    monkeypatch.delenv("APP_TOKEN", raising=False)
    require_write_auth(None)  # must not raise


def test_write_auth_enforced_with_token(monkeypatch):
    from fastapi.security import HTTPAuthorizationCredentials

    monkeypatch.setenv("APP_TOKEN", "s3cret")
    with pytest.raises(HTTPException) as exc:
        require_write_auth(None)
    assert exc.value.status_code == 401
    require_write_auth(HTTPAuthorizationCredentials(scheme="Bearer", credentials="s3cret"))
    with pytest.raises(HTTPException):
        require_write_auth(HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong"))
