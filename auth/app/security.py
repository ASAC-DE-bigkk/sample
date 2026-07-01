"""보안 유틸 — 비밀번호 해시·인증토큰·세션·CSRF·레이트리밋·입력검증.

방어하는 취약점(웹/인증 신규 유형 — docs/security 참조):
  - 비밀번호 평문/약한 해시 → bcrypt(passlib)
  - 이메일 인증 토큰 위조/재사용/무만료 → 랜덤 토큰 + DB 에 sha256+만료+단일사용
  - 세션 위변조 → itsdangerous 서명 쿠키(만료) + HttpOnly/SameSite/Secure
  - CSRF → 서명 CSRF 토큰(쿠키+폼 double-submit) 상수시간 비교
  - 브루트포스 → 간단 슬라이딩윈도우 레이트리밋
  - 계정 열거 → 호출측 제네릭 응답(여기선 판정 유틸만)
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext

from .config import get_settings

# pbkdf2_sha256: 순수 passlib+hashlib(외부 C 확장 불필요) — 이식성 높고 강한 KDF.
_pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── 비밀번호 ────────────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd.verify(password, password_hash)
    except ValueError:
        return False


def password_ok(password: str) -> bool:
    s = get_settings()
    return (len(password) >= s.password_min_len
            and any(c.isalpha() for c in password)
            and any(c.isdigit() for c in password))


def email_ok(email: str) -> bool:
    return bool(email) and len(email) <= 320 and bool(_EMAIL_RE.match(email))


# ── 이메일 인증 토큰(랜덤 + DB 해시 저장) ──────────────────────────────────────
def new_verification_token() -> tuple[str, str]:
    """(raw_token, token_hash). raw 는 이메일로만, DB 엔 hash 만 저장."""
    raw = secrets.token_urlsafe(32)
    return raw, token_hash(raw)


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ── 세션(서명 쿠키) ─────────────────────────────────────────────────────────────
def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt=salt)


def make_session(user_id: str) -> str:
    return _serializer("session").dumps({"uid": user_id})


def read_session(token: str | None) -> str | None:
    if not token:
        return None
    try:
        data = _serializer("session").loads(token, max_age=get_settings().session_max_age)
        return data.get("uid")
    except (BadSignature, SignatureExpired):
        return None


# ── CSRF(서명 토큰, double-submit) ──────────────────────────────────────────────
def make_csrf() -> str:
    return _serializer("csrf").dumps(secrets.token_urlsafe(16))


def csrf_ok(cookie_val: str | None, form_val: str | None) -> bool:
    if not cookie_val or not form_val:
        return False
    if not hmac.compare_digest(cookie_val, form_val):   # double-submit 일치
        return False
    try:
        _serializer("csrf").loads(cookie_val, max_age=3600)   # 서명·만료 검증
        return True
    except (BadSignature, SignatureExpired):
        return False


# ── 레이트리밋(인메모리 슬라이딩윈도우) ─────────────────────────────────────────
_hits: dict[str, deque] = defaultdict(deque)


def rate_limited(key: str) -> bool:
    s = get_settings()
    now = time.time()
    dq = _hits[key]
    while dq and dq[0] < now - s.rate_limit_window:
        dq.popleft()
    if len(dq) >= s.rate_limit_max:
        return True
    dq.append(now)
    return False
