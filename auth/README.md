# auth — 로그인/회원가입 + 이메일 인증 서비스

FastAPI + 서버렌더 템플릿 + SQLite(기본)/Postgres. 회원가입 → **이메일 인증** → 로그인(세션) →
보호 페이지. 보안 대응은 [SECURITY.md](SECURITY.md)(웹/인증 신규 취약점 유형 정본).

- **위치**: 레포 최상위 `auth/`(독립 서비스). 이 폴더 안에서 자립.
- **스택**: FastAPI · SQLAlchemy 2.0 · passlib(pbkdf2) · itsdangerous · Jinja2.
- **이메일**: SMTP 값 있으면 실발송, 없으면 콘솔/로그로 인증 링크 출력(dev, 값 없이도 동작).

## 실행

```bash
cp auth/.env.example auth/.env         # AUTH_SECRET_KEY 등 확인(운영은 강한 값 + COOKIE_SECURE=1)
python -m pip install -r auth/requirements.txt
cd auth && uvicorn app.main:app --reload      # http://localhost:8000
```

라우트: `/signup` · `/verify?token=…` · `/login` · `/logout` · `/dashboard`(보호) · `/healthz`.
dev(SMTP 미설정)에서는 회원가입 후 **콘솔 로그의 인증 링크**로 `/verify` 진행.

## 데이터 모델

- `users`(id·email·**password_hash**·is_verified·created_at)
- `email_verifications`(user_id·**token_hash=sha256(token)**·expires_at·used_at) — 토큰 원문 미저장, 단일사용/만료.

## 환경변수

[.env.example](.env.example) 참조. 시크릿(`AUTH_SECRET_KEY`·`SMTP_PASSWORD`)은 `.env`(gitignore),
커밋·로그 금지. **필요 값(추후 입력)**: SMTP_HOST/PORT/USER/PASSWORD/FROM(실메일 발송 시).

## 테스트

```bash
PYTHONPATH=auth pytest auth/tests -q          # 10 PASS (흐름 + 보안 케이스)
```

## 후속(범위 밖)

비밀번호 재설정 · 2FA · 계정 잠금 · 레이트리밋 공용 저장소(Redis) · 알림 연동(다음 브랜치).
