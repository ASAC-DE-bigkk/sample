# auth 보안 — 위협 모델 & 대응 (웹/인증 신규 유형)

이 서비스는 로그인/회원가입 + 이메일 인증을 다룬다. 데이터 파이프라인 보안 모델
(`dags/domains/commerce/docs/security/security.md` — 시크릿 마스킹·주입·경로 등)에서
**다루지 않았던 웹/인증 특유의 취약점 유형**을 여기서 추가로 대비한다.

## 신규 유형 → 대응 (이 프로젝트에 조치 완료)

| # | 위협(신규 유형) | 대응 | 위치 |
|---|---|---|---|
| A1 | **비밀번호 평문/약한 저장** | `pbkdf2_sha256`(passlib) 해시. 평문·가역 저장 안 함 | [app/security.py](app/security.py) |
| A2 | **이메일 인증 토큰 위조/무만료/재사용** | 랜덤 토큰(secrets) + DB 에 **sha256만** 저장 + 만료(24h) + **단일사용**(used_at) | security.py·models.py·main.py |
| A3 | **세션 위·변조** | itsdangerous 서명 쿠키(만료) + **HttpOnly·SameSite=Lax·Secure(운영)** | security.py·main.py |
| A4 | **CSRF** | 서명 CSRF 토큰 double-submit(쿠키+폼) 상수시간 비교 | security.py·main.py·templates |
| A5 | **브루트포스/자격증명 스터핑** | 로그인·회원가입 슬라이딩윈도우 레이트리밋 | security.py |
| A6 | **계정 열거(account enumeration)** | 회원가입·로그인·인증 실패를 **제네릭 응답**(존재 여부 미노출) | main.py |
| A7 | **XSS** | Jinja2 autoescape(기본 on) + CSP `default-src 'self'` | templates·main.py |
| A8 | **Clickjacking** | `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'` | main.py |
| A9 | **MIME 스니핑** | `X-Content-Type-Options: nosniff` | main.py |
| A10 | **SQL Injection** | SQLAlchemy ORM(파라미터화). 문자열 SQL 미사용 | db.py·main.py |
| A11 | **약한 비밀번호** | 정책(10자+·영문/숫자) 검증 | security.py |
| A12 | **시크릿 노출** | SECRET_KEY·SMTP_PASSWORD env only, 로그 금지, `.env` gitignore | config.py·email.py·.gitignore |
| A13 | **스키마/문서 노출** | `/docs`·`/redoc`·OpenAPI 비활성 | main.py |

## 남은 운영 주의(값/환경 의존)

- **운영은 `AUTH_COOKIE_SECURE=1`(HTTPS)** + 강한 `AUTH_SECRET_KEY` 필수(기본값은 dev 전용).
- 레이트리밋은 인메모리(단일 프로세스) — 다중 인스턴스는 공용 저장소(예: Redis)로 확장 권장.
- 이메일 발송은 SMTP 값 있으면 실발송, 없으면 콘솔/로그(토큰 노출은 dev 한정). 운영은 SMTP 필수.
- 비밀번호 재설정·2FA·계정 잠금은 후속(현재 범위: 가입·인증·로그인).

## 파이프라인 보안 모델과의 관계

시크릿을 로그·저장물로 흘리지 않는 원칙은 파이프라인과 동일하게 적용(SMTP 비번·SECRET_KEY 미로그).
파이프라인의 **이식형 보안 서브시스템**(`include/security/`)의 `redact()`/정적감사 개념을 이 서비스의
로깅에도 적용 가능(추후 통합). 웹/인증 신규 유형(A1~A13)은 본 문서가 정본이다.

## 검증

`PYTHONPATH=auth pytest auth/tests -q` — **10 PASS**: 가입→인증→로그인→보호페이지, 인증 전
로그인 차단, 오답 제네릭, 중복가입 열거방지, 토큰 단일사용, 위조토큰 거부, CSRF 필수, 약한 비번
거부, **비밀번호 해시 저장(평문 아님)**, 보안 헤더.
