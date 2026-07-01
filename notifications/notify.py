"""공통 알림 인터페이스 — backend(auth) + pipeline 공용. Slack/Telegram/Discord.

매체별 전달/‘채널’ 차이(웹훅=채널 고정 vs Telegram=chat_id)를 어댑터가 흡수. 값 없으면 no-op.
알림 메시지의 시크릿은 전송 전 마스킹(_redact) — 토큰/비번/키가 외부 채널로 새지 않게. stdlib 만.

설정(env): NOTIFY_CHANNELS=slack,telegram,discord
  slack   : SLACK_WEBHOOK_URL
  discord : DISCORD_WEBHOOK_URL
  telegram: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
필요 값은 README.md 참조(추후 입력). 자세한 매체별 개념: 이 파일 상단 표 및 pipeline docs/notifications.md.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from abc import ABC, abstractmethod
from typing import Callable

log = logging.getLogger("notifications")

Poster = Callable[[str, dict, dict], int]
PLACEHOLDER = "***REDACTED***"

# 전송 전 마스킹 패턴(경량) — Bearer / 이름있는 시크릿 할당·쿼리 / AWS 키.
_REDACT = [
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?\S+"), r"\1" + PLACEHOLDER),
    (re.compile(r"(?i)((?:api[_-]?key|access[_-]?key[_-]?id|secret[_-]?access[_-]?key|secret|"
                r"password|passwd|pwd|token|credential)\s*[=:]\s*[\"']?)([^\s\"'&;]+)"),
     r"\1" + PLACEHOLDER),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), PLACEHOLDER),
]


def redact(text: str) -> str:
    out = text or ""
    for rx, repl in _REDACT:
        out = rx.sub(repl, out)
    return out


def _http_post(url: str, payload: dict, headers: dict) -> int:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=10) as r:   # 고정 알림 엔드포인트
        return r.status


def _fmt(subject: str, message: str, level: str, context: dict | None) -> str:
    ctx = ("\n" + " · ".join(f"{k}={v}" for k, v in (context or {}).items())) if context else ""
    return redact(f"[{level.upper()}] {subject}{ctx}\n{message}")


class Notifier(ABC):
    @abstractmethod
    def send(self, *, subject: str, message: str, level: str = "error",
             context: dict | None = None) -> bool: ...


class NoopNotifier(Notifier):
    def send(self, *, subject, message, level="error", context=None) -> bool:
        log.info("[notify:noop] level=%s subject=%s (미설정)", level, subject)
        return False


class SlackNotifier(Notifier):
    def __init__(self, url: str, poster: Poster = _http_post): self.url, self._p = url, poster
    def send(self, *, subject, message, level="error", context=None) -> bool:
        self._p(self.url, {"text": _fmt(subject, message, level, context)}, {}); return True


class DiscordNotifier(Notifier):
    def __init__(self, url: str, poster: Poster = _http_post): self.url, self._p = url, poster
    def send(self, *, subject, message, level="error", context=None) -> bool:
        self._p(self.url, {"content": _fmt(subject, message, level, context)[:1900]}, {}); return True


class TelegramNotifier(Notifier):
    def __init__(self, token: str, chat_id: str, poster: Poster = _http_post):
        self.token, self.chat_id, self._p = token, chat_id, poster
    def send(self, *, subject, message, level="error", context=None) -> bool:
        self._p(f"https://api.telegram.org/bot{self.token}/sendMessage",
                {"chat_id": self.chat_id, "text": _fmt(subject, message, level, context)}, {})
        return True


class MultiNotifier(Notifier):
    def __init__(self, notifiers: list[Notifier]): self._ns = notifiers
    def send(self, *, subject, message, level="error", context=None) -> bool:
        ok = False
        for n in self._ns:
            try:
                ok = n.send(subject=subject, message=message, level=level, context=context) or ok
            except Exception:
                log.exception("[notify] 채널 전송 실패(무시): %s", type(n).__name__)
        return ok


def from_env(env: dict | None = None, *, poster: Poster = _http_post) -> Notifier:
    e = os.environ if env is None else env
    chans = [c.strip().lower() for c in (e.get("NOTIFY_CHANNELS", "") or "").split(",") if c.strip()]
    built: list[Notifier] = []
    if "slack" in chans and e.get("SLACK_WEBHOOK_URL"):
        built.append(SlackNotifier(e["SLACK_WEBHOOK_URL"], poster))
    if "discord" in chans and e.get("DISCORD_WEBHOOK_URL"):
        built.append(DiscordNotifier(e["DISCORD_WEBHOOK_URL"], poster))
    if "telegram" in chans and e.get("TELEGRAM_BOT_TOKEN") and e.get("TELEGRAM_CHAT_ID"):
        built.append(TelegramNotifier(e["TELEGRAM_BOT_TOKEN"], e["TELEGRAM_CHAT_ID"], poster))
    return MultiNotifier(built) if built else NoopNotifier()


def notify_exception(notifier: Notifier, exc: BaseException, *, where: str,
                     context: dict | None = None) -> None:
    try:
        notifier.send(subject=f"예외: {where}", message=f"{type(exc).__name__}: {exc}",
                      level="error", context=context)
    except Exception:
        log.exception("[notify] notify_exception 실패(무시): %s", where)
