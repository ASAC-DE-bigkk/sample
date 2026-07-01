# notifications — 공통 알림 (backend + pipeline)

예외·문제 발생 시 로그/요약을 **Slack/Telegram/Discord** 로 보내는 공통 인터페이스. backend(auth)
와 pipeline(loader/dbt) 이 함께 쓴다. stdlib 만 — 어디서든 `from notifications import ...`.

## 매체별 전달 / '채널' 개념 차이

| 매체 | 전달 | 채널 | 필요 값 |
|---|---|---|---|
| Slack | Webhook POST `{"text"}` | 웹훅에 고정 | `SLACK_WEBHOOK_URL` |
| Discord | Webhook POST `{"content"}`(2000자 절삭) | 웹훅에 고정 | `DISCORD_WEBHOOK_URL` |
| Telegram | Bot API `/bot<TOKEN>/sendMessage` `{"chat_id","text"}` | chat_id 로 지정 | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` |

## 설정 (추후 값 입력)

```bash
NOTIFY_CHANNELS=slack,telegram,discord   # 켤 채널(쉼표). 비우면 no-op
SLACK_WEBHOOK_URL=...
DISCORD_WEBHOOK_URL=...
TELEGRAM_BOT_TOKEN=...   # @BotFather
TELEGRAM_CHAT_ID=...
```

값은 **시크릿** — 커밋/로그 금지. 메시지는 전송 전 `redact()` 로 토큰/비번/키를 마스킹한다.

## 사용

```python
from notifications import from_env, notify_exception
notifier = from_env()                        # 미설정이면 no-op
try:
    ...
except Exception as exc:
    notify_exception(notifier, exc, where="auth:/login", context={"method": "POST"})
```

- **auth 연동**: `auth/app/main.py` 의 전역 예외 핸들러가 미처리 500 을 이 알림으로 전송(스택은 클라이언트에 미노출).
- **pipeline 연동**: `dbt/domains/commerce/loader/` 는 동형 어댑터로 데이터셋 단위 실패를 알림(참고).

## 검증

- `PYTHONPATH=. pytest notifications/tests -q` — 4 PASS(매체 payload/채널·팬아웃·**마스킹**·실패격리).
- `PYTHONPATH=.:auth pytest auth/tests -q` — 11 PASS(포함: 미처리 예외 → 알림 연동).
