"""Accounts, sessions and role checks.

Passwords: scrypt (stdlib) with a per-user salt. Sessions: random token in an
HttpOnly, SameSite=Strict cookie; only its SHA-256 is stored, with a TTL.
"""

import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

SESSION_COOKIE = "ml_session"
ROLES = ("consumer", "analyst", "admin")
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}

router = APIRouter(prefix="/auth", tags=["auth"])


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=32, **_SCRYPT)
    enc = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${enc(salt)}${enc(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt_b64), dklen=len(expected), n=int(n), r=int(r), p=int(p)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def _token_id(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _accounts(request: Request):
    return request.app.state.mongo[request.app.state.settings.mongo_db_accounts]


class _Throttle:
    """At most `limit` failed sign-ins per client and username per window."""

    def __init__(self, limit: int = 10, window_s: int = 300):
        self.limit, self.window = limit, window_s
        self.failures: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> None:
        q = self.failures[key]
        while q and q[0] < time.monotonic() - self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "Too many failed sign-in attempts. Wait a few minutes and try again.")

    def fail(self, key: str) -> None:
        self.failures[key].append(time.monotonic())


throttle = _Throttle()


def current_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    accounts = _accounts(request)
    session = accounts.sessions.find_one({"_id": _token_id(token)})
    if not session or session["expires_at"] <= datetime.now(timezone.utc):
        return None
    user = accounts.users.find_one({"_id": session["user_id"]}, {"password_hash": 0})
    return user


def require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Sign in to continue.")
    return user


def require_admin(user: dict = Depends(require_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "This needs an administrator account.")
    return user


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def _public(user: dict) -> dict:
    return {"username": user["username"], "role": user["role"]}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response) -> dict:
    username = body.username.strip().lower()
    key = f"{request.client.host if request.client else '?'}|{username}"
    throttle.check(key)
    accounts = _accounts(request)
    user = accounts.users.find_one({"_id": username})
    valid = verify_password(body.password, user["password_hash"] if user else _DUMMY_HASH)
    if not user or not valid:
        throttle.fail(key)
        raise HTTPException(401, "Username or password is incorrect.")
    settings = request.app.state.settings
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    accounts.sessions.insert_one(
        {"_id": _token_id(token), "user_id": user["_id"], "created_at": now, "expires_at": now + timedelta(hours=settings.session_hours)}
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        path="/",
    )
    return _public(user)


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        _accounts(request).sessions.delete_one({"_id": _token_id(token)})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"signed_out": True}


@router.get("/me")
def me(user: dict = Depends(require_user)) -> dict:
    return _public(user)
