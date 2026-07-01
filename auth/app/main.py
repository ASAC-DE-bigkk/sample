"""FastAPI 인증 앱 — 회원가입 → 이메일 인증 → 로그인(세션) → 보호 페이지.

보안: bcrypt 비번, 서명 세션 쿠키(HttpOnly/SameSite/Secure), CSRF(double-submit),
레이트리밋, 계정열거 방지(제네릭 응답), 보안 헤더, Jinja2 autoescape, DB 파라미터화.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

# 공통 알림(backend+pipeline 공용) — 경로 밖이면 비활성(no-op). 값 없으면 no-op.
try:
    from notifications import from_env as _notifier_from_env
    from notifications import notify_exception as _notify_exception
except Exception:  # notifications 미가용
    _notifier_from_env = None
    _notify_exception = None

from . import security as sec
from .config import get_settings
from .db import get_db, init_db
from .email import send_verification_email
from .models import EmailVerification, User

app = FastAPI(title="auth", docs_url=None, redoc_url=None)  # 스키마 노출 최소화
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
SESSION_COOKIE = "session"
CSRF_COOKIE = "csrftoken"


@app.on_event("startup")
def _startup() -> None:
    init_db()
    app.state.notifier = _notifier_from_env() if _notifier_from_env else None


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    # 예외를 공통 알림으로(있으면). 클라이언트엔 스택 미노출(제네릭 500).
    notifier = getattr(app.state, "notifier", None)
    if notifier is not None and _notify_exception is not None:
        _notify_exception(notifier, exc, where=f"auth:{request.url.path}",
                          context={"method": request.method})
    return PlainTextResponse("Internal Server Error", status_code=500)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = "default-src 'self'; form-action 'self'; frame-ancestors 'none'"
    return resp


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _client_key(request: Request, scope: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{scope}:{ip}"


def _set_cookies(resp, *, session: str | None = None, csrf: str | None = None) -> None:
    s = get_settings()
    common = dict(httponly=True, samesite="lax", secure=s.cookie_secure)
    if session is not None:
        resp.set_cookie(SESSION_COOKIE, session, max_age=s.session_max_age, **common)
    if csrf is not None:
        resp.set_cookie(CSRF_COOKIE, csrf, max_age=3600, **common)


def current_user(request: Request, db: Session) -> User | None:
    uid = sec.read_session(request.cookies.get(SESSION_COOKIE))
    if not uid:
        return None
    return db.get(User, uid)


def _render_form(request: Request, template: str, **ctx) -> HTMLResponse:
    csrf = sec.make_csrf()
    resp = templates.TemplateResponse(template, {"request": request, "csrf_token": csrf, **ctx})
    _set_cookies(resp, csrf=csrf)
    return resp


def _check_csrf(request: Request, csrf_token: str) -> bool:
    return sec.csrf_ok(request.cookies.get(CSRF_COOKIE), csrf_token)


# ── 라우트 ───────────────────────────────────────────────────────────────────────
@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    return RedirectResponse("/dashboard" if current_user(request, db) else "/login", status_code=303)


@app.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request):
    return _render_form(request, "signup.html")


@app.post("/signup", response_class=HTMLResponse)
def signup(request: Request, db: Session = Depends(get_db),
           email: str = Form(...), password: str = Form(...), csrf_token: str = Form(...)):
    if not _check_csrf(request, csrf_token):
        return _render_form(request, "signup.html", error="세션이 만료되었습니다. 다시 시도하세요.")
    if sec.rate_limited(_client_key(request, "signup")):
        return _render_form(request, "signup.html", error="요청이 너무 많습니다. 잠시 후 다시 시도하세요.")
    email = email.strip().lower()
    if not sec.email_ok(email) or not sec.password_ok(password):
        return _render_form(request, "signup.html",
                            error="이메일 형식 또는 비밀번호 정책(10자+, 영문/숫자 포함)을 확인하세요.")
    existing = db.scalar(select(User).where(User.email == email))
    if existing is None:
        user = User(email=email, password_hash=sec.hash_password(password), is_verified=False)
        db.add(user); db.flush()
        _issue_verification(db, user)
    # 계정 열거 방지 — 존재 여부와 무관하게 동일 응답.
    db.commit()
    return templates.TemplateResponse("message.html", {"request": request,
        "title": "인증 메일 발송", "message": "가입을 진행했다면 인증 메일을 보냈습니다. 메일함을 확인하세요."})


def _issue_verification(db: Session, user: User) -> str:
    raw, thash = sec.new_verification_token()
    expires = _now() + _dt.timedelta(seconds=get_settings().verify_token_max_age)
    db.add(EmailVerification(user_id=user.id, token_hash=thash, expires_at=expires))
    verify_url = f"{get_settings().base_url}/verify?token={raw}"
    send_verification_email(user.email, verify_url)
    return raw


@app.get("/verify", response_class=HTMLResponse)
def verify(request: Request, token: str = "", db: Session = Depends(get_db)):
    rec = db.scalar(select(EmailVerification).where(
        EmailVerification.token_hash == sec.token_hash(token))) if token else None
    ok = False
    if rec and rec.used_at is None and _as_utc(rec.expires_at) > _now():
        rec.used_at = _now()
        user = db.get(User, rec.user_id)
        if user:
            user.is_verified = True
            ok = True
        db.commit()
    return templates.TemplateResponse("message.html", {"request": request,
        "title": "이메일 인증", "message": "인증이 완료되었습니다. 로그인하세요." if ok
        else "링크가 유효하지 않거나 만료/사용되었습니다.", "login_link": ok})


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return _render_form(request, "login.html")


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, db: Session = Depends(get_db),
          email: str = Form(...), password: str = Form(...), csrf_token: str = Form(...)):
    if not _check_csrf(request, csrf_token):
        return _render_form(request, "login.html", error="세션이 만료되었습니다. 다시 시도하세요.")
    if sec.rate_limited(_client_key(request, "login")):
        return _render_form(request, "login.html", error="시도가 너무 많습니다. 잠시 후 다시 시도하세요.")
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    # 제네릭 실패 메시지 — 이메일 존재/비번오류/미인증 구분 노출 안 함(열거 방지).
    if user is None or not sec.verify_password(password, user.password_hash) or not user.is_verified:
        return _render_form(request, "login.html", error="이메일 인증이 필요하거나 자격 증명이 올바르지 않습니다.")
    resp = RedirectResponse("/dashboard", status_code=303)
    _set_cookies(resp, session=sec.make_session(user.id))
    return resp


@app.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    resp = RedirectResponse("/login", status_code=303)
    if _check_csrf(request, csrf_token):
        resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return _render_form(request, "dashboard.html", email=user.email)


def _as_utc(dt: _dt.datetime) -> _dt.datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=_dt.timezone.utc)
