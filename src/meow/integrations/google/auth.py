"""Google sign-in for a desktop app: read-only scopes, tokens kept in the macOS Keychain.

While the Google Cloud project's consent screen is in "Testing", Google expires refresh
tokens after 7 days. When that happens the account is flagged ``needs_reauth`` and Meow
asks you to run ``meow google login`` again rather than failing quietly.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Protocol

from meow.config import Settings
from meow.types import SourceKind

log = logging.getLogger(__name__)

KEYRING_SERVICE = "MeowOS-google"
IDENTITY_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email"]
SCOPES_BY_SOURCE: dict[SourceKind, list[str]] = {
    SourceKind.GMAIL: ["https://www.googleapis.com/auth/gmail.readonly"],
    SourceKind.CALENDAR: ["https://www.googleapis.com/auth/calendar.readonly"],
    SourceKind.CLASSROOM: [
        "https://www.googleapis.com/auth/classroom.courses.readonly",
        "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
        "https://www.googleapis.com/auth/classroom.announcements.readonly",
    ],
}
GOOGLE_SOURCES = tuple(SCOPES_BY_SOURCE)


class GoogleAuthError(RuntimeError):
    pass


class ReauthRequired(GoogleAuthError):
    """The stored token was revoked or expired; the user must sign in again."""


def scopes_for(sources: Iterable[SourceKind]) -> list[str]:
    scopes = list(IDENTITY_SCOPES)
    for source in sources:
        scopes += [s for s in SCOPES_BY_SOURCE[source] if s not in scopes]
    return scopes


# ── the OAuth client file ────────────────────────────────────────────────


def install_client_file(settings: Settings, source: Path) -> Path:
    """Copy the downloaded OAuth client JSON into Meow's data dir (readable only by you)."""
    try:
        data = json.loads(source.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise GoogleAuthError(f"can't read {source}: {exc}") from exc
    if "installed" not in data:
        kind = next(iter(data), "unknown")
        raise GoogleAuthError(
            f"{source} is a '{kind}' client. Create an OAuth client of type 'Desktop app'."
        )
    target = settings.google_client_file
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copyfile(source, target)
    target.chmod(0o600)
    return target


# ── token storage ────────────────────────────────────────────────────────


class TokenStore(Protocol):
    def load(self, email: str) -> str | None: ...
    def save(self, email: str, token_json: str) -> None: ...
    def delete(self, email: str) -> None: ...


class KeychainTokenStore:
    """macOS Keychain via ``keyring``; falls back to 0600 files if no keyring backend exists."""

    def __init__(self, settings: Settings) -> None:
        self.fallback_dir = settings.home / "google" / "tokens"

    def _file(self, email: str) -> Path:
        return self.fallback_dir / f"{email}.json"

    def load(self, email: str) -> str | None:
        try:
            import keyring

            value: str | None = keyring.get_password(KEYRING_SERVICE, email)
            if value:
                return value
        except Exception as exc:
            log.debug("keyring unavailable: %s", exc)
        path = self._file(email)
        return path.read_text() if path.exists() else None

    def save(self, email: str, token_json: str) -> None:
        try:
            import keyring

            keyring.set_password(KEYRING_SERVICE, email, token_json)
            return
        except Exception as exc:
            log.warning("Keychain unavailable (%s); storing the token in a private file", exc)
        self.fallback_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self._file(email)
        path.touch(mode=0o600)
        path.write_text(token_json)

    def delete(self, email: str) -> None:
        try:
            import keyring

            keyring.delete_password(KEYRING_SERVICE, email)
        except Exception as exc:
            log.debug("keyring delete skipped: %s", exc)
        self._file(email).unlink(missing_ok=True)


# ── credentials ──────────────────────────────────────────────────────────


def load_credentials(store: TokenStore, email: str, sources: Iterable[SourceKind]) -> Any:
    """Return valid Credentials for ``email``, refreshing (and re-saving) if needed."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    raw = store.load(email)
    if not raw:
        raise ReauthRequired(f"{email} isn't signed in. Run: meow google login {email}")
    creds = Credentials.from_authorized_user_info(json.loads(raw))
    lacking = [s.value for s in sources if not set(SCOPES_BY_SOURCE[s]) <= set(creds.scopes or ())]
    if lacking:
        raise ReauthRequired(
            f"{email} hasn't granted access to {', '.join(lacking)}. Run: meow google login {email}"
        )
    if not creds.valid:
        if not creds.refresh_token:
            raise ReauthRequired(f"{email} has no refresh token. Run: meow google login {email}")
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            raise ReauthRequired(
                f"Google ended the session for {email} ({exc}). Run: meow google login {email}"
            ) from exc
        store.save(email, creds.to_json())
    return creds


def _email_from_id_token(id_token: str | None) -> str | None:
    if not id_token:
        return None
    from google.auth import jwt

    try:
        # Received directly from Google's token endpoint over TLS, so no signature check needed.
        claims = jwt.decode(id_token, verify=False)
    except ValueError:
        return None
    email = claims.get("email")
    return str(email).lower() if email else None


def run_login_flow(
    settings: Settings, email: str, sources: Sequence[SourceKind], store: TokenStore
) -> Any:
    """Open the browser consent screen for ``email`` and store the resulting token."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    client = settings.google_client_file
    if not client.exists():
        raise GoogleAuthError(
            "No OAuth client installed. Run: meow google setup ~/Downloads/credentials.json"
        )
    # Google's consent screen lets you untick individual permissions. oauthlib treats that as an
    # exception by default; relax it and check what was actually granted ourselves.
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"  # noqa: S105 (a flag, not a secret)
    flow = InstalledAppFlow.from_client_secrets_file(str(client), scopes=scopes_for(sources))
    creds = flow.run_local_server(
        host="localhost",
        port=0,
        open_browser=True,
        login_hint=email,
        prompt="consent",
        access_type="offline",
        authorization_prompt_message="Opening Google sign-in for {url}",
        success_message="Meow OS is connected. You can close this tab.",
    )
    signed_in = _email_from_id_token(getattr(creds, "id_token", None))
    if signed_in and signed_in != email.lower():
        raise GoogleAuthError(
            f"You signed in as {signed_in}, not {email}. Run the login again and pick {email}."
        )
    if not creds.refresh_token:
        raise GoogleAuthError("Google didn't return a refresh token; run the login again.")
    granted = granted_scopes(flow.oauth2session.token)
    denied = [s.value for s in sources if not set(SCOPES_BY_SOURCE[s]) <= granted]
    if denied:
        raise GoogleAuthError(
            f"Permission wasn't granted for: {', '.join(denied)}. Run the login again and tick "
            "every box, or leave those out with --sources."
        )
    from google.oauth2.credentials import Credentials

    info = json.loads(creds.to_json())
    info["scopes"] = sorted(granted)
    store.save(email, Credentials.from_authorized_user_info(info).to_json())
    return creds


def granted_scopes(token: dict[str, Any]) -> set[str]:
    """Scopes Google actually granted, as reported in the token response."""
    scope = token.get("scope", "")
    return set(scope.split() if isinstance(scope, str) else scope)
