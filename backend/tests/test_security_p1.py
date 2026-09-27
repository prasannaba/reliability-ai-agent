"""P1 security: SSRF allowlist, rate limits, per-user secrets, proxy identity."""

import base64
import json
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

import src.common.credential_store as store
import src.host.app as main
from src.common.rate_limit import RateLimiter, RateLimitMiddleware
from src.host.app import (
    _assert_fetch_allowed,
    current_user,
    resolve_user_id,
    validate_base_url,
)


@pytest.fixture
def isolated_store(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_SECRET_PATH", tmp_path / ".llm_secret.enc")
    monkeypatch.setattr(store, "_KEY_PATH", tmp_path / ".credential.key")
    monkeypatch.delenv("CREDENTIAL_KEY", raising=False)
    monkeypatch.delenv("SECRET_BACKEND", raising=False)
    store.reset_backend_cache()
    yield tmp_path
    store.reset_backend_cache()


@pytest.fixture
def private_allowed(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_LLM", "true")
    yield


@pytest.fixture
def private_denied(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_LLM", "false")
    yield


# --- SSRF allowlist ---


def test_rejects_non_http_scheme(private_allowed):
    with pytest.raises(HTTPException) as exc:
        validate_base_url("file:///etc/passwd")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException):
        validate_base_url("gopher://example.com/")


def test_metadata_ip_always_blocked(private_allowed):
    with pytest.raises(HTTPException):
        validate_base_url("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(HTTPException):
        validate_base_url("http://100.100.100.200/")


def test_metadata_hostname_always_blocked(private_allowed):
    with pytest.raises(HTTPException):
        validate_base_url("https://metadata.google.internal/v1")


def test_loopback_allowed_by_default_and_blocked_when_opted_out(private_allowed):
    assert validate_base_url("http://127.0.0.1:11434") == "http://127.0.0.1:11434"


def test_loopback_blocked_when_private_denied(private_denied):
    with pytest.raises(HTTPException) as exc:
        validate_base_url("http://127.0.0.1:11434")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException):
        validate_base_url("http://192.168.1.10:11434")


def test_public_ip_allowed_in_both_modes(private_allowed):
    assert validate_base_url("https://93.184.216.34/v1/") == "https://93.184.216.34/v1"


def test_public_ip_allowed_when_private_denied(private_denied):
    assert validate_base_url("https://93.184.216.34/v1/") == "https://93.184.216.34/v1"


def _fake_getaddrinfo(ips):
    def _fake(host, port, family=0, type=0, proto=0, flags=0):
        return [(family, type, proto, "", (ip, 0)) for ip in ips]

    return _fake


def test_hostname_resolving_private_blocked_when_denied(monkeypatch, private_denied):
    monkeypatch.setattr(main.socket, "getaddrinfo", _fake_getaddrinfo(["10.9.9.9"]))
    with pytest.raises(HTTPException):
        validate_base_url("http://internal.example/")


def test_hostname_resolving_public_allowed_when_denied(monkeypatch, private_denied):
    monkeypatch.setattr(main.socket, "getaddrinfo", _fake_getaddrinfo(["93.184.216.34"]))
    assert validate_base_url("http://example.com/") == "http://example.com"


def test_mixed_dns_answers_fail_closed(monkeypatch, private_denied):
    # DNS rebinding shape: one public + one private answer => deny.
    monkeypatch.setattr(
        main.socket, "getaddrinfo", _fake_getaddrinfo(["93.184.216.34", "192.168.0.5"])
    )
    with pytest.raises(HTTPException):
        validate_base_url("http://example.com/")


def test_unresolvable_host_fails_closed(monkeypatch, private_allowed):
    def _boom(*args, **kwargs):
        raise OSError("no dns")

    monkeypatch.setattr(main.socket, "getaddrinfo", _boom)
    with pytest.raises(HTTPException):
        validate_base_url("http://does-not-exist.invalid/")


def test_fetch_guard_blocks_metadata_and_scheme():
    with pytest.raises(RuntimeError):
        _assert_fetch_allowed("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(RuntimeError):
        _assert_fetch_allowed("file:///etc/passwd")
    _assert_fetch_allowed("http://127.0.0.1:11434/api/tags")  # local fetch ok


# --- Rate limiter ---


def test_sliding_window_allows_then_denies():
    now = [1000.0]
    limiter = RateLimiter(3, window_seconds=60.0, clock=lambda: now[0])
    assert limiter.check("k")[0] is True
    assert limiter.check("k")[0] is True
    assert limiter.check("k")[0] is True
    allowed, retry = limiter.check("k")
    assert allowed is False and retry > 0
    now[0] += 61.0  # window slides past
    assert limiter.check("k")[0] is True


def test_middleware_returns_429_with_retry_after():
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    inner = FastAPI()

    @inner.get("/api/ping")
    async def ping():
        return JSONResponse({"ok": True})

    @inner.post("/api/llm/test")
    async def probe():
        return JSONResponse({"ok": True})

    app = RateLimitMiddleware(inner, api=RateLimiter(2), sensitive=RateLimiter(100))
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/ping").status_code == 200
    assert client.get("/api/ping").status_code == 200
    denied = client.get("/api/ping")
    assert denied.status_code == 429
    assert denied.headers.get("retry-after") is not None
    # Sensitive scope is independent and stricter than the general one.
    app2 = RateLimitMiddleware(inner, api=RateLimiter(100), sensitive=RateLimiter(1))
    client2 = TestClient(app2, raise_server_exceptions=False)
    assert client2.post("/api/llm/test").status_code == 200
    assert client2.post("/api/llm/test").status_code == 429


# --- Per-user credential scoping ---


def test_users_are_isolated(isolated_store):
    store.set_api_key("key-alice", user="alice")
    store.set_api_key("key-bob", user="bob")
    assert store.get_api_key("alice") == "key-alice"
    assert store.get_api_key("bob") == "key-bob"
    assert store.get_api_key("local") == ""  # untouched
    store.delete_api_key("alice")
    assert store.get_api_key("alice") == ""
    assert store.get_api_key("bob") == "key-bob"


def test_user_files_never_contain_raw_identity(isolated_store):
    store.set_api_key("key-alice", user="alice@example.com")
    names = [p.name for p in isolated_store.iterdir()]
    assert not any("alice" in n for n in names)
    assert any(n.startswith(".llm_secret.") and n.endswith(".enc") for n in names)
    # Legacy single-user path is unchanged.
    store.set_api_key("key-local")
    assert (isolated_store / ".llm_secret.enc").exists()


def test_unknown_secret_backend_rejected(monkeypatch, isolated_store):
    monkeypatch.setenv("SECRET_BACKEND", "vault-3000")
    with pytest.raises(RuntimeError):
        store.get_backend()


def test_azure_backend_secret_naming_without_client():
    name = store.AzureKeyVaultSecretBackend._name("alice@example.com")
    assert name.startswith("llm-api-key-") and "alice" not in name
    with pytest.raises(RuntimeError):
        store.AzureKeyVaultSecretBackend(vault_url="")  # missing URL, no client built


def test_llm_api_key_resolves_request_user(monkeypatch, isolated_store):
    monkeypatch.setattr(main, "_LLM_CONFIG_OVERRIDE", {})
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    store.set_api_key("key-alice", user="alice")
    token = current_user.set("alice")
    try:
        assert main.llm_api_key() == "key-alice"
        assert main.llm_has_api_key() is True
    finally:
        current_user.reset(token)
    assert main.llm_api_key() == "dummy"  # default "local" has no key


# --- Proxy-header identity (cloud) ---


def _scope_request(headers: dict[str, str], peer: str):
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/llm/config",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 50000),
    }
    return Request(scope)


def test_single_mode_ignores_spoofed_header(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "single")
    req = _scope_request({"X-User-Id": "mallory"}, "203.0.113.7")
    assert resolve_user_id(req) == "local"


def test_proxy_header_accepted_from_loopback(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "proxy-header")
    monkeypatch.setenv("TRUST_PROXY_USER_HEADER", "X-User-Id")
    req = _scope_request({"X-User-Id": "alice@contoso.com"}, "127.0.0.1")
    uid = resolve_user_id(req)
    assert uid.startswith("proxy:") and "alice" not in uid
    # Stable across requests.
    assert resolve_user_id(req) == uid


def test_proxy_header_ignored_from_remote_peer(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "proxy-header")
    monkeypatch.setenv("TRUST_PROXY_USER_HEADER", "X-User-Id")
    req = _scope_request({"X-User-Id": "mallory"}, "203.0.113.7")
    assert resolve_user_id(req) == "local"


def test_easy_auth_principal_parsed(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "proxy-header")
    monkeypatch.delenv("TRUST_PROXY_USER_HEADER", raising=False)
    principal = {
        "userId": "alice@contoso.com",
        "claims": [{"typ": "http://schemas.microsoft.com/identity/claims/objectidentifier", "val": "oid-123"}],
    }
    raw = base64.b64encode(json.dumps(principal).encode()).decode()
    req = _scope_request({"X-MS-Client-Principal": raw}, "127.0.0.1")
    uid = resolve_user_id(req)
    assert uid.startswith("proxy:") and "oid-123" not in uid and "alice" not in uid
