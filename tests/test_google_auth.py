from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from meow.config import Settings
from meow.integrations.google import auth
from meow.types import SourceKind

from support import MemoryTokenStore

GMAIL = auth.SCOPES_BY_SOURCE[SourceKind.GMAIL]
CLASSROOM = auth.SCOPES_BY_SOURCE[SourceKind.CLASSROOM]


def token(scopes: list[str], expiry: str = "2999-01-01T00:00:00Z") -> str:
    return json.dumps(
        {
            "token": "access",
            "refresh_token": "refresh",
            "client_id": "cid",
            "client_secret": "csecret",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": scopes,
            "expiry": expiry,
        }
    )


@pytest.fixture(autouse=True)
def no_keychain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never touch the real Keychain: every keyring call fails like a headless box."""
    import keyring

    def unavailable(*args: object, **kwargs: object) -> None:
        raise RuntimeError("no keyring backend in tests")

    for name in ("get_password", "set_password", "delete_password"):
        monkeypatch.setattr(keyring, name, unavailable)


def test_install_client_file(settings: Settings, tmp_path: Path) -> None:
    src = tmp_path / "credentials.json"
    src.write_text(json.dumps({"installed": {"client_id": "x", "client_secret": "y"}}))
    target = auth.install_client_file(settings, src)
    assert target == settings.google_client_file
    assert json.loads(target.read_text())["installed"]["client_id"] == "x"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_web_clients_are_refused_with_a_hint(settings: Settings, tmp_path: Path) -> None:
    src = tmp_path / "web.json"
    src.write_text(json.dumps({"web": {"client_id": "x"}}))
    with pytest.raises(auth.GoogleAuthError, match="Desktop app"):
        auth.install_client_file(settings, src)


def test_scopes_are_read_only_and_deduplicated() -> None:
    scopes = auth.scopes_for([SourceKind.GMAIL, SourceKind.CLASSROOM, SourceKind.GMAIL])
    assert scopes[:2] == auth.IDENTITY_SCOPES
    assert len(scopes) == len(set(scopes))
    writes = [
        s
        for s in scopes
        if s.startswith("https://www.googleapis.com/auth/")
        and "readonly" not in s
        and "userinfo" not in s
    ]
    assert writes == []


def test_granted_scopes_accepts_string_or_list() -> None:
    assert auth.granted_scopes({"scope": "openid a b"}) == {"openid", "a", "b"}
    assert auth.granted_scopes({"scope": ["a", "b"]}) == {"a", "b"}


def test_missing_token_needs_login() -> None:
    with pytest.raises(auth.ReauthRequired, match=r"meow google login me@x\.test"):
        auth.load_credentials(MemoryTokenStore(), "me@x.test", [SourceKind.GMAIL])


def test_token_without_a_sources_permission_needs_login() -> None:
    store = MemoryTokenStore({"me@x.test": token(GMAIL)})
    with pytest.raises(auth.ReauthRequired, match="classroom"):
        auth.load_credentials(store, "me@x.test", [SourceKind.GMAIL, SourceKind.CLASSROOM])


def test_valid_token_is_used_without_network() -> None:
    store = MemoryTokenStore({"me@x.test": token(GMAIL + CLASSROOM)})
    creds = auth.load_credentials(store, "me@x.test", [SourceKind.GMAIL, SourceKind.CLASSROOM])
    assert creds.valid and creds.token == "access"


def test_revoked_refresh_token_needs_login(monkeypatch: pytest.MonkeyPatch) -> None:
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials

    def refused(self: object, request: object) -> None:
        raise RefreshError("invalid_grant: Token has been expired or revoked.")

    monkeypatch.setattr(Credentials, "refresh", refused)
    store = MemoryTokenStore({"me@x.test": token(GMAIL, expiry="2020-01-01T00:00:00Z")})
    with pytest.raises(auth.ReauthRequired, match="expired or revoked"):
        auth.load_credentials(store, "me@x.test", [SourceKind.GMAIL])


def test_refreshed_token_is_saved_back(monkeypatch: pytest.MonkeyPatch) -> None:
    import datetime as dt

    from google.oauth2.credentials import Credentials

    def refreshed(self: Credentials, request: object) -> None:
        self.token = "fresh"
        self.expiry = dt.datetime(2999, 1, 1)  # noqa: DTZ001 (google-auth uses naive UTC)

    monkeypatch.setattr(Credentials, "refresh", refreshed)
    store = MemoryTokenStore({"me@x.test": token(GMAIL, expiry="2020-01-01T00:00:00Z")})
    auth.load_credentials(store, "me@x.test", [SourceKind.GMAIL])
    assert json.loads(store.tokens["me@x.test"])["token"] == "fresh"


def test_keychain_store_falls_back_to_a_private_file(settings: Settings) -> None:
    store = auth.KeychainTokenStore(settings)
    store.save("me@x.test", token(GMAIL))
    path = settings.home / "google" / "tokens" / "me@x.test.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert store.load("me@x.test") == token(GMAIL)
    store.delete("me@x.test")
    assert store.load("me@x.test") is None and not path.exists()
