"""Local API authentication.

Binding to 127.0.0.1 is not enough: any web page you open can send requests to localhost,
and DNS rebinding defeats IP checks. So every request needs a secret token (kept in the
macOS Keychain), the Host header must be local, and browser writes must come from our origin.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time

from meow.config import Settings

log = logging.getLogger(__name__)

KEYRING_SERVICE = "MeowOS"
KEYRING_USER = "api-token"
LOGIN_CODE_MAX_AGE = 120  # seconds


def _keyring_get() -> str | None:
    try:
        import keyring

        value: str | None = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        return value
    except Exception as exc:  # no usable backend (CI, headless Linux)
        log.debug("keyring unavailable: %s", exc)
        return None


def _keyring_set(token: str) -> bool:
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, token)
        return True
    except Exception as exc:
        log.debug("keyring unavailable: %s", exc)
        return False


def token_source(settings: Settings) -> str:
    if os.environ.get("MEOW_API_TOKEN"):
        return "environment"
    if _keyring_get():
        return "keychain"
    if settings.token_file.exists():
        return "file"
    return "missing"


def load_or_create_token(settings: Settings) -> str:
    """Environment override, then Keychain, then a 0600 file as a last resort."""
    if env := os.environ.get("MEOW_API_TOKEN"):
        return env
    if stored := _keyring_get():
        return stored
    if settings.token_file.exists():
        return settings.token_file.read_text().strip()
    token = secrets.token_urlsafe(32)
    if not _keyring_set(token):
        settings.ensure_home()
        settings.token_file.touch(mode=0o600)
        settings.token_file.write_text(token)
        log.warning("Keychain unavailable; API token stored in %s", settings.token_file)
    return token


def tokens_match(expected: str, given: str | None) -> bool:
    return given is not None and hmac.compare_digest(expected.encode(), given.encode())


def session_value(token: str) -> str:
    """Browser cookie value: derived from the token so the token itself isn't stored there."""
    return hmac.new(token.encode(), b"session", hashlib.sha256).hexdigest()


def login_code(token: str, issued_at: int) -> str:
    """A short-lived code for the browser login link, so the token itself never hits a URL."""
    mac = hmac.new(token.encode(), f"login:{issued_at}".encode(), hashlib.sha256)
    return mac.hexdigest()[:32]


def verify_login_code(token: str, code: str, issued_at: int, now: float | None = None) -> bool:
    age = (now if now is not None else time.time()) - issued_at
    if not 0 <= age <= LOGIN_CODE_MAX_AGE:
        return False
    return hmac.compare_digest(login_code(token, issued_at), code)
