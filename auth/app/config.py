"""설정 — 전부 환경변수. 시크릿(AUTH_SECRET_KEY, SMTP_PASSWORD)은 로그 금지."""
from __future__ import annotations

import os
from functools import lru_cache


class Settings:
    def __init__(self) -> None:
        self.secret_key = os.environ.get("AUTH_SECRET_KEY", "dev-insecure-change-me")
        self.database_url = os.environ.get("AUTH_DATABASE_URL", "sqlite:///./auth.db")
        self.base_url = os.environ.get("AUTH_BASE_URL", "http://localhost:8000").rstrip("/")
        # 토큰/세션 수명(초)
        self.verify_token_max_age = int(os.environ.get("AUTH_VERIFY_TOKEN_MAX_AGE", "86400"))  # 24h
        self.session_max_age = int(os.environ.get("AUTH_SESSION_MAX_AGE", "3600"))             # 1h
        # 쿠키 보안 — 운영은 반드시 secure=1(HTTPS)
        self.cookie_secure = os.environ.get("AUTH_COOKIE_SECURE", "0") == "1"
        # 비밀번호 정책
        self.password_min_len = int(os.environ.get("AUTH_PASSWORD_MIN_LEN", "10"))
        # 레이트리밋(로그인/회원가입 브루트포스 완화)
        self.rate_limit_max = int(os.environ.get("AUTH_RATE_LIMIT_MAX", "10"))
        self.rate_limit_window = int(os.environ.get("AUTH_RATE_LIMIT_WINDOW", "60"))
        # SMTP(선택) — 값 있으면 실제 발송, 없으면 콘솔/로그로 토큰 출력
        self.smtp_host = os.environ.get("SMTP_HOST", "")
        self.smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_user = os.environ.get("SMTP_USER", "")
        self.smtp_password = os.environ.get("SMTP_PASSWORD", "")
        self.smtp_from = os.environ.get("SMTP_FROM", "no-reply@auth.local")
        self.smtp_starttls = os.environ.get("SMTP_STARTTLS", "1") == "1"

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host)


@lru_cache
def get_settings() -> Settings:
    return Settings()
