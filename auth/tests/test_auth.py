"""auth 통합 테스트 — 회원가입→인증→로그인→보호페이지 + 보안 케이스(오프라인, SQLite temp).

    PYTHONPATH=auth pytest auth/tests -q
이메일은 콘솔 모드(OUTBOX)로 캡처. 값(SMTP) 없이도 전체 흐름 검증.
"""
import os
import re
import tempfile

os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key")
os.environ["AUTH_DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/auth_test.db"
os.environ["AUTH_BASE_URL"] = "http://testserver"

import pytest
from fastapi.testclient import TestClient

from app.email import OUTBOX
from app.main import app


@pytest.fixture()
def client():
    OUTBOX.clear()
    with TestClient(app) as c:      # context manager → startup(init_db) 실행
        yield c


def _csrf(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m, "csrf token not found in form"
    return m.group(1)


def _signup(client, email, password="Passw0rd123"):
    tok = _csrf(client.get("/signup").text)
    return client.post("/signup", data={"email": email, "password": password, "csrf_token": tok})


def _verify_url_token(url: str) -> str:
    return url.split("token=", 1)[1]


def test_healthz(client):
    assert client.get("/healthz").json()["status"] == "ok"


def test_security_headers(client):
    h = client.get("/login").headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in h["Content-Security-Policy"]


def test_full_signup_verify_login_flow(client):
    r = _signup(client, "a@example.com")
    assert r.status_code == 200 and "인증 메일" in r.text
    assert len(OUTBOX) == 1
    to, _subj, url = OUTBOX[0]
    assert to == "a@example.com"

    # 인증 전 로그인 차단(제네릭)
    tok = _csrf(client.get("/login").text)
    r = client.post("/login", data={"email": "a@example.com", "password": "Passw0rd123",
                                     "csrf_token": tok}, follow_redirects=False)
    assert r.status_code == 200 and "올바르지 않습니다" in r.text

    # 이메일 인증
    r = client.get("/verify", params={"token": _verify_url_token(url)})
    assert "완료되었습니다" in r.text

    # 로그인 성공 → 세션 쿠키 + 대시보드
    tok = _csrf(client.get("/login").text)
    r = client.post("/login", data={"email": "a@example.com", "password": "Passw0rd123",
                                     "csrf_token": tok}, follow_redirects=False)
    assert r.status_code == 303 and "session" in r.cookies
    assert "로그인됨" in client.get("/dashboard").text


def test_wrong_password_generic(client):
    _signup(client, "b@example.com")
    client.get("/verify", params={"token": _verify_url_token(OUTBOX[0][2])})
    tok = _csrf(client.get("/login").text)
    r = client.post("/login", data={"email": "b@example.com", "password": "WRONGpass9",
                                     "csrf_token": tok})
    assert "올바르지 않습니다" in r.text


def test_duplicate_signup_no_enumeration(client):
    _signup(client, "c@example.com")
    assert len(OUTBOX) == 1
    r = _signup(client, "c@example.com")           # 중복 — 동일 응답, 새 토큰 미발급
    assert r.status_code == 200 and "인증 메일" in r.text
    assert len(OUTBOX) == 1


def test_verification_token_single_use(client):
    _signup(client, "d@example.com")
    t = _verify_url_token(OUTBOX[0][2])
    assert "완료되었습니다" in client.get("/verify", params={"token": t}).text
    assert "유효하지 않" in client.get("/verify", params={"token": t}).text  # 재사용 불가


def test_bad_token_rejected(client):
    assert "유효하지 않" in client.get("/verify", params={"token": "nope"}).text


def test_csrf_required(client):
    client.get("/signup")                          # csrf 쿠키 셋
    r = client.post("/signup", data={"email": "e@example.com", "password": "Passw0rd123",
                                     "csrf_token": "forged"})
    assert "세션이 만료" in r.text


def test_weak_password_rejected(client):
    r = _signup(client, "f@example.com", password="short")
    assert "정책" in r.text and len(OUTBOX) == 0


def test_password_is_hashed_not_plaintext(client):
    _signup(client, "g@example.com", password="Passw0rd123")
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == "g@example.com"))
    assert u and u.password_hash != "Passw0rd123" and u.password_hash.startswith("$pbkdf2-sha256$")
