"""공통 notifications 오프라인 테스트.  PYTHONPATH=. pytest notifications/tests -q"""
from notifications import notify


def _cap():
    sent = []
    def poster(url, payload, headers): sent.append((url, payload)); return 200
    return sent, poster


def test_slack_discord_telegram_shapes():
    sent, p = _cap()
    notify.SlackNotifier("https://hooks.slack.com/x", p).send(subject="s", message="m")
    notify.DiscordNotifier("https://discord.com/api/webhooks/x", p).send(subject="s", message="y" * 5000)
    notify.TelegramNotifier("TKN", "42", p).send(subject="s", message="m")
    assert "text" in sent[0][1]
    assert "content" in sent[1][1] and len(sent[1][1]["content"]) <= 1900
    assert "/botTKN/sendMessage" in sent[2][0] and sent[2][1]["chat_id"] == "42"


def test_from_env_noop_and_fanout():
    assert isinstance(notify.from_env({}), notify.NoopNotifier)
    sent, p = _cap()
    n = notify.from_env({"NOTIFY_CHANNELS": "slack,telegram",
                         "SLACK_WEBHOOK_URL": "https://hooks.slack.com/x",
                         "TELEGRAM_BOT_TOKEN": "T", "TELEGRAM_CHAT_ID": "9"}, poster=p)
    n.send(subject="s", message="m")
    assert len(sent) == 2


def test_redaction_before_send():
    sent, p = _cap()
    notify.SlackNotifier("https://hooks.slack.com/x", p).send(
        subject="fail", message="token=abcdef123456 password=hunter2 ok")
    text = sent[0][1]["text"]
    assert "abcdef123456" not in text and "hunter2" not in text and "***REDACTED***" in text


def test_channel_failure_isolated():
    ok = []
    class Bad(notify.Notifier):
        def send(self, **_): raise RuntimeError("down")
    class Good(notify.Notifier):
        def send(self, **_): ok.append(1); return True
    notify.MultiNotifier([Bad(), Good()]).send(subject="s", message="m")
    assert ok == [1]
