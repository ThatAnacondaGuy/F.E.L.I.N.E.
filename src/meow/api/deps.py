"""Request-scoped dependencies: database session, profile, clock, authentication."""

from __future__ import annotations

import hmac
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from meow.config import Profile
from meow.llm.ollama import JSONChat
from meow.security import session_value, tokens_match

COOKIE_NAME = "meow_session"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as db:
        try:
            yield db
        except Exception:
            db.rollback()
            raise


def get_profile(request: Request) -> Profile:
    profile: Profile = request.app.state.settings.profile
    return profile


def get_now(request: Request) -> datetime:
    clock: Callable[[], datetime] = request.app.state.clock
    return clock()


def get_llm(request: Request) -> JSONChat:
    factory: Callable[[], JSONChat] = request.app.state.llm_factory
    return factory()


def _request_origin(request: Request) -> str | None:
    if origin := request.headers.get("origin"):
        return origin
    if referer := request.headers.get("referer"):
        parts = urlsplit(referer)
        return f"{parts.scheme}://{parts.netloc}"
    return None


def require_auth(request: Request) -> str:
    """Accept the bearer token (CLI, desktop cat) or the browser session cookie.

    Cookie-authenticated writes must also come from our own origin, which stops other
    sites from submitting forms to Meow even if the browser attaches the cookie.
    """
    token: str = request.app.state.token
    header = request.headers.get("authorization", "")
    if header.startswith("Bearer ") and tokens_match(token, header.removeprefix("Bearer ")):
        return "bearer"
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie and hmac.compare_digest(cookie, session_value(token)):
        if request.method not in SAFE_METHODS:
            origin = _request_origin(request)
            if origin not in request.app.state.allowed_origins:
                raise HTTPException(status_code=403, detail="Cross-site request blocked")
        return "cookie"
    raise HTTPException(status_code=401, detail="Not authenticated")


DB = Annotated[Session, Depends(get_db)]
ProfileDep = Annotated[Profile, Depends(get_profile)]
Now = Annotated[datetime, Depends(get_now)]
LLM = Annotated[JSONChat, Depends(get_llm)]
