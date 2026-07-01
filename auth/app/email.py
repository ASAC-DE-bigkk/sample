"""이메일 발송 — SMTP 값 있으면 실제 발송, 없으면 콘솔/로그로 인증 링크 출력(dev).

시크릿(SMTP_PASSWORD)은 로그에 남기지 않는다. dev 콘솔 모드는 OUTBOX 에도 적재(테스트/확인용).
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from .config import get_settings

log = logging.getLogger("auth.email")

# dev/테스트용 — 콘솔 모드에서 보낸 메일 (to, subject, verify_url) 보관.
OUTBOX: list[tuple[str, str, str]] = []


def send_verification_email(to: str, verify_url: str) -> None:
    subject = "[auth] 이메일 인증을 완료해 주세요"
    body = (f"아래 링크로 이메일 인증을 완료하세요(24시간 유효, 1회용):\n\n{verify_url}\n\n"
            f"본인이 요청하지 않았다면 무시하세요.")
    s = get_settings()
    if not s.smtp_enabled:
        # 콘솔/로그 모드 — 값 없이도 흐름 검증 가능.
        OUTBOX.append((to, subject, verify_url))
        log.info("[email:console] to=%s verify_url=%s", to, verify_url)
        return
    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        if s.smtp_starttls:
            smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)   # 비밀번호는 로그 금지
        smtp.send_message(msg)
    log.info("[email:smtp] sent verification to %s", to)
