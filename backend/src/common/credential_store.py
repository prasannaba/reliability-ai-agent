"""Backend-only credential manager for LLM API keys.

Security goals:
- API keys are NEVER stored in ``backend/.llm_config.json`` (which holds only
  non-secret settings: provider, baseUrl, model, temperature, systemPrompt).
- API keys are NEVER returned by any GET endpoint (only ``hasApiKey: bool``).
- API keys are NEVER written to ``localStorage``/``sessionStorage`` — the
  frontend keeps a pasted key in React memory only and POSTs it once.
- At rest the key lives in ``backend/.llm_secret[.user].enc``
  (Fernet-encrypted, file mode 0600) with the encryption key in
  ``backend/.credential.key`` (0600) or ``CREDENTIAL_KEY`` env.

Single-user vs multi-user:
- Today the app is single-user: everything uses ``user="local"``, which maps
  to the original ``.llm_secret.enc`` path (unchanged on disk).
- For cloud multi-user, keys are namespaced per user id
  (``.llm_secret.<sha256(user)[:16]>.enc`` locally, or
  ``llm-api-key-<hex>`` in Azure Key Vault). User ids are always hashed
  before touching the filesystem/secret names — never use raw identity
  strings as file names.
- ``SECRET_BACKEND=local`` (default) or ``azure-keyvault``. The Azure backend
  needs the ``cloud`` dependency group (``uv sync --group cloud``), the
  ``AZURE_KEY_VAULT_URL`` env var, and a managed identity / credential chain
  on the host. The server holds the identity; the browser never sees secrets.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import stat
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_KEY_PATH = _BACKEND_DIR / ".credential.key"
_LOCAL_USER = "local"


def _user_suffix(user: str) -> str:
    """Stable, filesystem-safe namespace. 'local' keeps the legacy path."""
    if not user or user == _LOCAL_USER:
        return ""
    digest = hashlib.sha256(user.encode("utf-8")).hexdigest()[:16]
    return f".{digest}"


def _secret_path_for(user: str) -> Path:
    # NOTE: goes through the `_SECRET_PATH` module global (not _BACKEND_DIR
    # directly) so tests can redirect storage by monkeypatching it.
    if not user or user == _LOCAL_USER:
        return _SECRET_PATH
    return _SECRET_PATH.parent / f".llm_secret{_user_suffix(user)}.enc"


# Legacy module-level alias kept for tests/tools that patch it.
_SECRET_PATH = _BACKEND_DIR / ".llm_secret.enc"

try:  # Optional but recommended: `uv sync` installs it (see pyproject).
    from cryptography.fernet import Fernet, InvalidToken

    _HAS_FERNET = True
except ImportError:  # pragma: no cover - exercised when dep missing
    Fernet = None  # type: ignore[assignment]
    InvalidToken = Exception  # type: ignore[assignment,misc]
    _HAS_FERNET = False


def _chmod_owner_only(path: Path) -> None:
    """Best-effort 0600. On Windows this is a no-op for ACLs (user profile dir
    is already user-private); on POSIX it removes group/other read bits."""
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _load_or_create_raw_key() -> bytes:
    """32 raw bytes for Fernet. Precedence: CREDENTIAL_KEY env > key file."""
    env_key = (os.getenv("CREDENTIAL_KEY") or "").strip()
    if env_key:
        try:
            return base64.urlsafe_b64decode(env_key.encode("utf-8"))
        except Exception as exc:
            raise ValueError("CREDENTIAL_KEY is not valid base64 (expected Fernet key)") from exc
    if _KEY_PATH.exists():
        raw = _KEY_PATH.read_bytes().strip()
        try:
            decoded = base64.urlsafe_b64decode(raw)
        except Exception as exc:
            raise ValueError("Credential key file is corrupt; delete .credential.key to rotate") from exc
        if len(decoded) != 32:
            raise ValueError("Credential key file is corrupt; delete .credential.key to rotate")
        _chmod_owner_only(_KEY_PATH)
        return decoded
    raw_key = os.urandom(32)
    _KEY_PATH.write_bytes(base64.urlsafe_b64encode(raw_key))
    _chmod_owner_only(_KEY_PATH)
    return raw_key


def _fernet() -> Fernet:
    if not _HAS_FERNET or Fernet is None:
        raise RuntimeError("cryptography package not installed")
    return Fernet(base64.urlsafe_b64encode(_load_or_create_raw_key()))


class SecretBackend(Protocol):
    """Pluggable per-user secret storage. Browser never touches this."""

    def get(self, user: str) -> str: ...
    def set(self, user: str, value: str) -> None: ...
    def delete(self, user: str) -> None: ...


class LocalFileSecretBackend:
    """Fernet-encrypted files, one per user-hash. Default; works everywhere."""

    def set(self, user: str, value: str) -> None:
        path = _secret_path_for(user)
        secret = value.strip().encode("utf-8")
        if _HAS_FERNET:
            path.write_bytes(_fernet().encrypt(secret))
        else:  # Fallback: 0600 file, no JSON wrapper. Warn loudly.
            logger.warning(
                "cryptography not installed: API key stored in 0600 file without "
                "encryption. Run `uv sync` to enable Fernet encryption."
            )
            path.write_bytes(secret)
        _chmod_owner_only(path)

    def get(self, user: str) -> str:
        try:
            blob = _secret_path_for(user).read_bytes()
        except OSError:
            return ""
        if not blob:
            return ""
        if _HAS_FERNET:
            try:
                return _fernet().decrypt(blob).decode("utf-8")
            except InvalidToken:
                logger.error(
                    "Stored API key cannot be decrypted (wrong CREDENTIAL_KEY?). Treat as unset."
                )
                return ""
            except Exception:  # noqa: BLE001 - corrupt file must not crash boot
                logger.exception("Failed to read stored API key")
                return ""
        return blob.decode("utf-8", errors="replace").strip()

    def delete(self, user: str) -> None:
        try:
            _secret_path_for(user).unlink()
        except OSError:
            pass


class AzureKeyVaultSecretBackend:
    """Per-user secrets in Azure Key Vault (cloud multi-user).

    Requires ``AZURE_KEY_VAULT_URL`` and the ``cloud`` dependency group
    (``azure-identity`` + ``azure-keyvault-secrets``). Auth uses
    ``DefaultAzureCredential`` (managed identity on Azure hosts).
    """

    def __init__(self, vault_url: str | None = None) -> None:
        self.vault_url = (vault_url or os.getenv("AZURE_KEY_VAULT_URL") or "").strip().rstrip("/")
        if not self.vault_url:
            raise RuntimeError("SECRET_BACKEND=azure-keyvault requires AZURE_KEY_VAULT_URL")
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
        except ImportError as exc:
            raise RuntimeError(
                "Azure backend needs the 'cloud' group: uv sync --group cloud"
            ) from exc
        self._client = SecretClient(self.vault_url, DefaultAzureCredential())

    @staticmethod
    def _name(user: str) -> str:
        # Key Vault names: alphanumerics + hyphens only; hex digest qualifies.
        return f"llm-api-key-{hashlib.sha256(user.encode('utf-8')).hexdigest()[:32]}"

    def get(self, user: str) -> str:
        try:
            return self._client.get_secret(self._name(user)).value or ""
        except Exception:  # noqa: BLE001 - missing/disabled secret => unset
            return ""

    def set(self, user: str, value: str) -> None:
        self._client.set_secret(self._name(user), value.strip())

    def delete(self, user: str) -> None:
        try:
            poller = self._client.begin_delete_secret(self._name(user))
            poller.wait()
        except Exception:  # noqa: BLE001 - already gone => gone
            pass


_backend: SecretBackend | None = None


def get_backend() -> SecretBackend:
    """Factory: SECRET_BACKEND=local (default) | azure-keyvault."""
    global _backend
    if _backend is not None:
        return _backend
    kind = (os.getenv("SECRET_BACKEND") or "local").strip().lower()
    if kind == "azure-keyvault":
        _backend = AzureKeyVaultSecretBackend()
    elif kind == "local":
        _backend = LocalFileSecretBackend()
    else:
        raise RuntimeError(f"Unknown SECRET_BACKEND: {kind!r} (expected 'local' or 'azure-keyvault')")
    return _backend


def reset_backend_cache() -> None:
    """Forget the cached backend (tests / SECRET_BACKEND rotation)."""
    global _backend
    _backend = None


def set_api_key(value: str, user: str = _LOCAL_USER) -> None:
    """Encrypt + persist for `user`. Empty/blank deletes instead (revoke)."""
    if not value or not value.strip():
        delete_api_key(user)
        return
    get_backend().set(user, value)


def get_api_key(user: str = _LOCAL_USER) -> str:
    """Return decrypted key or "" when unset/corrupt (never raises for I/O)."""
    try:
        return get_backend().get(user) or ""
    except Exception:  # noqa: BLE001 - a broken backend must not crash chat
        logger.exception("Secret backend read failed")
        return ""


def has_api_key(user: str = _LOCAL_USER) -> bool:
    return bool(get_api_key(user))


def delete_api_key(user: str = _LOCAL_USER) -> None:
    try:
        get_backend().delete(user)
    except Exception:  # noqa: BLE001 - delete is best-effort
        logger.exception("Secret backend delete failed")


def migrate_legacy_key(legacy_value: str | None, user: str = _LOCAL_USER) -> bool:
    """Move a key found in old .llm_config.json into the store. Returns True if moved."""
    if not legacy_value or not legacy_value.strip():
        return False
    if has_api_key(user):
        return True  # store already wins; caller should still strip legacy copy
    set_api_key(legacy_value, user)
    return True
