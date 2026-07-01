"""auth ↔ 공통 알림 연동 — 미처리 예외가 알림으로 전달되는지(경로 밖이면 skip).

    PYTHONPATH=.:auth pytest auth/tests/test_notify_integration.py -q
"""
import pytest
from fastapi.testclient import TestClient

pytest.importorskip("notifications")   # 루트가 경로에 없으면 skip

from app.db import get_db
from app.main import app
from notifications import Notifier


class _Capture(Notifier):
    def __init__(self): self.calls = []
    def send(self, *, subject, message, level="error", context=None):
        self.calls.append((subject, message, context)); return True


def test_unhandled_exception_triggers_notifier():
    cap = _Capture()
    def _boom():
        raise RuntimeError("db down secret token=abcdef123456")
    app.dependency_overrides[get_db] = _boom
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.notifier = cap                 # startup 이후 주입
            r = client.get("/dashboard")
        assert r.status_code == 500 and "Internal Server Error" in r.text
        assert len(cap.calls) == 1
        subject, message, ctx = cap.calls[0]
        assert "auth:/dashboard" in subject and ctx["method"] == "GET"
    finally:
        app.dependency_overrides.clear()
