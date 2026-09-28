from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from meow.api.app import SyncDeps, create_app
from meow.api.deps import COOKIE_NAME
from meow.config import Settings
from meow.security import login_code

from support import (
    LAB_EMAIL,
    FakeAPIs,
    FakeGmail,
    FakeLLM,
    MemoryTokenStore,
    RecordingNotifier,
    extracted,
    fake_credentials,
    gmail_msg,
    ist,
)

TOKEN = "test-token"
BASE = "http://127.0.0.1:8765"
ORIGIN = {"Origin": BASE}
AUTH = {"Authorization": f"Bearer {TOKEN}"}
NOW = ist(2026, 9, 28, 16, 0)
INBOX = FakeGmail([gmail_msg("m1", "CN Lab 4", LAB_EMAIL, ist(2026, 9, 28, 9, 0))])
NOTIFIER = RecordingNotifier()
SYNC_DEPS = SyncDeps(apis=FakeAPIs(gmail=INBOX), store=MemoryTokenStore(), load=fake_credentials)


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM({"tasks": [extracted()]})


@pytest.fixture
def client(settings: Settings, llm: FakeLLM) -> Iterator[TestClient]:
    app = create_app(
        settings,
        clock=lambda: NOW,
        llm_factory=lambda: llm,
        sync_deps=SYNC_DEPS,
        background=False,
        notifier=NOTIFIER,
    )
    with TestClient(app, base_url=BASE) as c:
        yield c


def browser_login(client: TestClient) -> None:
    ts = int(time.time())
    r = client.get(f"/login?code={login_code(TOKEN, ts)}&ts={ts}", follow_redirects=False)
    assert r.status_code == 303
    assert COOKIE_NAME in r.cookies


# ── security ─────────────────────────────────────────────────────────────


def test_health_is_public_but_everything_else_needs_the_token(client: TestClient) -> None:
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/tasks").status_code == 401
    assert client.get("/api/tasks", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/tasks", headers=AUTH).status_code == 200


def test_foreign_host_header_is_rejected(client: TestClient) -> None:
    # DNS rebinding: evil.example resolves to 127.0.0.1, but the Host header gives it away.
    r = client.get("/api/health", headers={"Host": "evil.example:8765"})
    assert r.status_code == 400


def test_web_pages_are_locked_without_login(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 401 and "meow open" in r.text


def test_login_link_expires_and_cannot_be_forged(client: TestClient) -> None:
    old = int(time.time()) - 600
    assert client.get(f"/login?code={login_code(TOKEN, old)}&ts={old}").status_code == 401
    now = int(time.time())
    assert client.get(f"/login?code={'0' * 32}&ts={now}").status_code == 401


def test_session_cookie_is_httponly_and_strict(client: TestClient) -> None:
    ts = int(time.time())
    r = client.get(f"/login?code={login_code(TOKEN, ts)}&ts={ts}", follow_redirects=False)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert TOKEN not in r.headers["set-cookie"]  # derived value, not the token itself


def test_cross_site_form_post_is_blocked(client: TestClient) -> None:
    browser_login(client)
    r = client.post("/tasks", data={"title": "evil"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/tasks", data={"title": "no origin at all"})
    assert r.status_code == 403
    assert client.get("/api/tasks", headers=AUTH).json() == []


def test_security_headers(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


# ── flows ────────────────────────────────────────────────────────────────


def test_capture_approve_plan_flow_over_json(client: TestClient) -> None:
    r = client.post("/api/capture", json={"text": LAB_EMAIL, "title": "CN Lab 4"}, headers=AUTH)
    assert r.status_code == 200, r.text
    (proposal,) = r.json()["proposals"]
    assert proposal["evidence"].startswith("Submit lab assignment 4")

    r = client.post(f"/api/proposals/{proposal['id']}/approve", json={}, headers=AUTH)
    assert r.json()["status"] == "approved"

    (task,) = client.get("/api/tasks", headers=AUTH).json()
    assert task["title"] == "Submit CN lab assignment 4"
    assert task["score"]["reasons"]

    plan = client.get("/api/plan", headers=AUTH).json()
    assert plan["sessions"][0]["title"] == "Submit CN lab assignment 4"

    blocks = client.post("/api/plan/propose", headers=AUTH).json()
    assert blocks and blocks[0]["kind"] == "schedule_focus_block"

    actions = [e["action"] for e in client.get("/api/audit", headers=AUTH).json()]
    assert "proposal.approved" in actions and "task.created" in actions


def test_extraction_failure_is_a_502_with_a_reason(settings: Settings) -> None:
    from meow.llm.ollama import LLMError

    def boom(_: str) -> object:
        raise LLMError("Model 'qwen3:8b' is not installed. Run: ollama pull qwen3:8b")

    app = create_app(
        settings,
        clock=lambda: NOW,
        llm_factory=lambda: FakeLLM(boom),
        background=False,
        notifier=NOTIFIER,
    )
    with TestClient(app, base_url=BASE) as c:
        r = c.post("/api/capture", json={"text": LAB_EMAIL}, headers=AUTH)
    assert r.status_code == 502 and "ollama pull" in r.json()["detail"]


def test_promotion_is_refused_without_a_record(client: TestClient) -> None:
    r = client.post("/api/autonomy/create_task/promote", headers=AUTH)
    assert r.status_code == 409


def test_web_ui_end_to_end(client: TestClient) -> None:
    browser_login(client)
    r = client.post("/capture", data={"text": LAB_EMAIL}, headers=ORIGIN, follow_redirects=True)
    assert "Filed 1 proposal" in r.text
    assert "Submit lab assignment 4 by Friday" in r.text  # evidence shown

    proposal_id = client.get("/api/proposals", headers=AUTH).json()[0]["id"]
    r = client.post(
        f"/inbox/{proposal_id}/approve",
        data={
            "title": "Submit CN lab 4",
            "due": "2026-10-02T23:59",
            "minutes": "90",
            "importance": "high",
        },
        headers=ORIGIN,
        follow_redirects=True,
    )
    assert "Approved." in r.text

    page = client.get("/")
    assert page.status_code == 200
    assert "Submit CN lab 4" in page.text
    for path in ("/inbox", "/tasks", "/autonomy", "/activity"):
        assert client.get(path).status_code == 200, path


def test_html_is_escaped(client: TestClient) -> None:
    browser_login(client)
    client.post("/tasks", data={"title": "<script>alert(1)</script>"}, headers=ORIGIN)
    page = client.get("/tasks").text
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


# ── sync ─────────────────────────────────────────────────────────────────


def connect_account(client: TestClient) -> None:
    from meow.services import accounts
    from meow.types import SourceKind

    with client.app.state.session_factory() as db:  # type: ignore[attr-defined]
        accounts.connect(db, "me@gmail.test", [SourceKind.GMAIL])


def test_sync_over_json(client: TestClient) -> None:
    connect_account(client)
    run = client.post("/api/sync", headers=AUTH).json()
    assert run["results"] == [
        {
            "account": "me@gmail.test",
            "source": "gmail",
            "new_items": 1,
            "proposals": 0,
            "pushed": 0,
            "removed": 0,
            "error": None,
        }
    ]
    assert run["extracted"] == 1 and run["extraction_proposals"] == 1
    (acct,) = client.get("/api/sync", headers=AUTH).json()
    assert acct["email"] == "me@gmail.test" and acct["sync"][0]["last_error"] is None


def test_today_shows_sync_status_and_sync_now_works(client: TestClient) -> None:
    browser_login(client)
    assert "No Google account connected" in client.get("/").text
    connect_account(client)
    assert "Sync now" in client.get("/").text
    r = client.post("/sync", headers=ORIGIN, follow_redirects=True)
    assert "Synced: 1 new item(s), 1 new proposal(s)." in r.text


def test_expired_google_sign_in_is_shown_on_today(client: TestClient) -> None:
    from meow.services import accounts

    browser_login(client)
    connect_account(client)
    with client.app.state.session_factory() as db:  # type: ignore[attr-defined]
        acct = accounts.get(db, "me@gmail.test")
        accounts.mark_needs_reauth(db, acct, "expired")
        db.commit()
    page = client.get("/").text
    assert "Google signed Meow out of" in page and "meow google login me@gmail.test" in page
