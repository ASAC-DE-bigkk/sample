# Setup Values Guide

이 문서는 Airflow + Trino + dbt + Cloudflare R2 Data Catalog/Iceberg 환경을 띄우기 전에 준비해야 하는 값과 생성 방법을 정리한다.

기준 설계:

- R2 bucket: `seoul`
- Trino catalog: `iceberg`
- 도메인 schema 예시: `weather`
- smoke 전용 schema: `ops_smoke`
- Airflow web UI host port: `30585`
- shared Cloudflare/R2/Data Catalog 환경은 prod용으로만 사용
- 멘티에게 prod Cloudflare credential을 배포하지 않음

실제 secret 값은 저장소에 커밋하지 않는다. repo에는 `.env.example`만 두고, 실제 값은 `.env` 또는 배포 환경 secret으로 관리한다.

## 0. 현재 진행 상태

기준일: 2026-06-27

Cloudflare/R2 준비 상태:

- Wrangler 로그인 완료: OAuth 로그인으로 로컬 Wrangler 명령 실행 가능
- Cloudflare account id 확인 완료: `416e8fd0b74dcf8b9170b651f0b790ce`
- R2 bucket 확인 완료: `seoul`
- R2 Data Catalog 상태 확인 완료: `active`
- R2 Data Catalog URI 확인 완료: `https://catalog.cloudflarestorage.com/416e8fd0b74dcf8b9170b651f0b790ce/seoul`
- R2 Data Catalog warehouse 확인 완료: `416e8fd0b74dcf8b9170b651f0b790ce_seoul`
- R2 Data Catalog auth check 완료: `./scripts/check-r2-catalog-auth.sh`가 HTTP `200` 반환

`.env` 준비 상태:

- R2/Data Catalog runtime 필수값 입력 완료
- runtime token이 `seoul` Data Catalog warehouse에 접근 가능한 상태로 확인 완료
- Cloudflare account, R2 endpoint, bucket/catalog/schema 고정값 입력 완료
- Airflow local runtime 필수값 입력 완료
- Airflow admin password, Fernet key, API/JWT secret key 생성 및 입력 완료
- Postgres password 생성 및 입력 완료
- `CLOUDFLARE_API_TOKEN`은 로컬 `wrangler login`을 사용하므로 일단 비워둔다.
- `WRANGLER_R2_SQL_AUTH_TOKEN`은 Wrangler R2 SQL 직접 점검시에만 필요하므로 일단 비워둔다.

구현/검증 상태:

- `.env.example`, `.gitignore`, `.dockerignore` 작성 완료
- Docker Compose 작성 완료
- Trino Iceberg REST catalog 설정 작성 완료
- Airflow `3.2.2` 기반 로컬 실행 구성 완료
- dbt `1.10.22`, dbt-trino `1.10.2` smoke project 작성 완료
- end-to-end smoke DAG 성공 확인 완료

## 1. 필요한 값 요약

### Cloudflare/R2 필수값

| 값 | 예시 | 어디에 쓰나 | 만드는 방법 |
| --- | --- | --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | `0123abcd...` | R2 endpoint 구성 | Cloudflare dashboard 또는 `wrangler whoami`에서 확인 |
| `CLOUDFLARE_API_TOKEN` | secret | Wrangler bootstrap 자동화 | Cloudflare API token 생성. 대화형 `wrangler login`만 쓰면 생략 가능 |
| `R2_BUCKET_NAME` | `seoul` | bootstrap script, README | 이미 결정된 bucket 이름 |
| `R2_ENDPOINT` | `https://<account_id>.r2.cloudflarestorage.com` | Trino S3 호환 R2 접근 | account id로 직접 구성 |
| `R2_ACCESS_KEY_ID` | secret id | Trino가 R2 object를 읽고 쓰는 S3 access key | R2 API token 생성 후 복사 |
| `R2_SECRET_ACCESS_KEY` | secret | Trino가 R2 object를 읽고 쓰는 S3 secret key | R2 API token 생성 후 복사. 생성 직후만 볼 수 있음 |
| `R2_DATA_CATALOG_TOKEN` | secret | Trino Iceberg REST catalog OAuth2 token | R2 API token 생성 후 token value 복사 |
| `R2_DATA_CATALOG_URI` | `https://...` | Trino Iceberg REST catalog URI | `r2 bucket catalog enable seoul` 결과 또는 dashboard에서 복사 |
| `R2_DATA_CATALOG_WAREHOUSE` | `...` | Trino Iceberg REST catalog warehouse | `r2 bucket catalog enable seoul` 결과 또는 dashboard에서 복사 |

### 로컬 Airflow/Docker 필수값

| 값 | 추천값/생성법 | 어디에 쓰나 |
| --- | --- | --- |
| `AIRFLOW_UID` | `id -u` 결과 | Docker volume 파일 권한 |
| `AIRFLOW_ADMIN_USERNAME` | `admin` | Airflow 첫 관리자 계정 |
| `AIRFLOW_ADMIN_PASSWORD` | `openssl rand -hex 16` | Airflow 첫 관리자 비밀번호 |
| `AIRFLOW_ADMIN_EMAIL` | 본인 이메일 또는 운영용 이메일 | Airflow 첫 관리자 계정 |
| `POSTGRES_USER` | `airflow` | Airflow metadata DB |
| `POSTGRES_PASSWORD` | `openssl rand -hex 24` | Airflow metadata DB password |
| `POSTGRES_DB` | `airflow` | Airflow metadata DB |
| `AIRFLOW_FERNET_KEY` | 아래 생성 명령 참고 | Airflow connection/variable 암호화 |
| `AIRFLOW_SECRET_KEY` | `openssl rand -hex 32` | Airflow API/JWT secret |

### 선택값

| 값 | 언제 필요한가 |
| --- | --- |
| `WRANGLER_R2_SQL_AUTH_TOKEN` | Wrangler로 R2 SQL/Data Catalog 점검을 별도로 할 때 |

v1 smoke test만으로는 `WRANGLER_R2_SQL_AUTH_TOKEN`을 비워둬도 된다.

### Wrangler로 처리 가능한 범위

Wrangler로 처리하거나 재확인할 수 있는 값과 작업은 다음이다.

- `CLOUDFLARE_ACCOUNT_ID` 확인: `npx wrangler whoami`
- R2 bucket 생성/존재 확인: `npx wrangler r2 bucket create/list/info`
- R2 Data Catalog enable/status 확인: `npx wrangler r2 bucket catalog enable/get`
- 선택적 R2 SQL 점검: `npx wrangler r2 sql query`

Wrangler로 대체하지 않는 값은 다음이다.

- `R2_DATA_CATALOG_TOKEN`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`: Cloudflare R2 API token 화면에서 생성 직후 복사한다.
- `AIRFLOW_*`, `POSTGRES_*`: 로컬 Docker Compose 실행값이므로 `id`, `openssl`, Python/Airflow 이미지로 만든다.

## 2. Cloudflare account id 확인

Cloudflare dashboard에서 account를 선택한 뒤 account id를 확인한다.

Wrangler를 이미 로그인해 둔 경우 아래로도 확인할 수 있다.

```bash
npx wrangler whoami
```

`.env`에는 다음처럼 넣는다.

```dotenv
CLOUDFLARE_ACCOUNT_ID=<your-account-id>
R2_ENDPOINT=https://<your-account-id>.r2.cloudflarestorage.com
```

현재 설계에서는 jurisdiction-specific R2 bucket을 쓰지 않는다. 따라서 기본 endpoint인 `https://<account_id>.r2.cloudflarestorage.com`를 사용한다.

## 3. Wrangler bootstrap 인증 준비

bucket 생성과 Data Catalog enable은 Wrangler로 수행한다.

### 방법 A: 대화형 login

로컬에서 직접 한 번 bootstrap할 때는 이 방식이 제일 단순하다.

```bash
npx wrangler login
```

이 방식을 쓰면 `.env`에 `CLOUDFLARE_API_TOKEN`을 넣지 않아도 된다.

### 방법 B: API token 사용

스크립트나 비대화형 환경에서 bootstrap하려면 `CLOUDFLARE_API_TOKEN`을 만든다.

Cloudflare dashboard에서 일반 API token을 만들고, bootstrap용으로 다음 권한이 필요하다.

- account-level R2 bucket 생성/설정 권한
- R2 Data Catalog enable 권한

현재 Cloudflare R2 권한 이름 기준으로는 bootstrap token에 `Workers R2 Storage Write`와 `Workers R2 Data Catalog Write` 계열 권한이 필요하다. 이 token은 bootstrap이 끝난 뒤 폐기하거나 보관 범위를 제한한다.

```bash
export CLOUDFLARE_API_TOKEN=<bootstrap-token>
```

## 4. R2 bucket 생성 및 Data Catalog enable

이 프로젝트의 bucket 이름은 `seoul`이다.

```bash
npx wrangler r2 bucket create seoul
npx wrangler r2 bucket list
npx wrangler r2 bucket info seoul
npx wrangler r2 bucket catalog enable seoul
npx wrangler r2 bucket catalog get seoul
```

`catalog enable` 결과에서 아래 두 값을 복사한다.

```dotenv
R2_DATA_CATALOG_URI=<catalog-uri-from-output>
R2_DATA_CATALOG_WAREHOUSE=<warehouse-from-output>
```

bucket이 이미 있으면 `create`는 건너뛰고 `list`/`info`로 존재 여부만 확인한다. Data Catalog가 이미 켜져 있으면 `catalog enable` 대신 `catalog get`으로 상태와 warehouse를 확인한다.

`catalog enable` 출력을 놓쳤고 `catalog get` 출력만으로 URI를 확정하기 어렵다면 Cloudflare dashboard의 R2 Data Catalog 화면에서 `seoul` catalog 상세 페이지를 열어 `Catalog URI`와 `Warehouse`를 다시 확인한다.

## 5. Trino runtime용 R2 API token/key/secret 생성

Trino는 두 종류의 접근이 필요하다.

- Iceberg REST catalog 접근: `R2_DATA_CATALOG_TOKEN`
- R2 object storage 접근: `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`

Cloudflare 공식 문서 기준으로 R2 Data Catalog를 쓰는 Iceberg engine은 R2 Data Catalog 권한과 R2 storage 권한을 모두 가진 R2 API token이 필요하다.

중요:

- `Object Read & Write`만 있는 R2 key는 S3-compatible object 접근용으로는 충분할 수 있지만, Iceberg REST catalog 접근에는 부족하다.
- `R2_DATA_CATALOG_TOKEN`은 `R2_DATA_CATALOG_WAREHOUSE`에 대한 R2 Data Catalog 권한이 있어야 한다.
- 권한이 부족하면 `./scripts/check-r2-catalog-auth.sh`와 Trino에서 `403` 및 `Insufficient permission for R2 Data Catalog Warehouse`가 발생한다.
- 가능하면 `seoul` bucket/catalog/warehouse로 scope를 제한한 token을 사용한다.
- Dashboard에서 세밀한 Data Catalog scope를 줄 수 없으면, 임시 검증에는 bucket scope를 제한한 `Admin Read & Write`를 사용할 수 있지만 장기 운영에서는 custom policy 기반 최소 권한 token을 우선한다.

Dashboard 경로:

1. Cloudflare dashboard에 로그인한다.
2. `Storage & databases` > `R2`로 이동한다.
3. `Overview`의 account details 영역에서 `API Tokens` 관리를 연다.
4. `Create Account API token`을 선택한다.
5. 권한은 R2 object read/write와 R2 Data Catalog warehouse 접근을 모두 포함해야 한다.
6. 가능하면 bucket/catalog 범위를 `seoul`로 제한한다. Cloudflare UI가 세밀한 Data Catalog scope를 지원하지 않으면 custom policy 방식 또는 운영상 허용 가능한 최소 scope를 선택한다.
7. 생성 직후 아래 값을 모두 복사한다.

복사할 값:

```dotenv
R2_DATA_CATALOG_TOKEN=<r2-api-token-value>
R2_ACCESS_KEY_ID=<access-key-id-or-client-id>
R2_SECRET_ACCESS_KEY=<secret-access-key-or-client-secret>
```

주의:

- `R2_SECRET_ACCESS_KEY`는 생성 직후 다시 볼 수 없을 수 있다.
- `R2_DATA_CATALOG_TOKEN`은 Trino의 `iceberg.rest-catalog.oauth2.token`에 들어간다.
- `R2_ACCESS_KEY_ID`와 `R2_SECRET_ACCESS_KEY`는 Trino의 S3 호환 R2 접근 설정에 들어간다.
- 이 token은 prod/shared runtime용이다. 멘티 로컬 개발용으로 배포하지 않는다.
- 현재 Wrangler CLI는 이 runtime용 R2 API token 값과 S3 access key/secret을 대신 생성하거나 재조회하는 용도로 쓰지 않는다.

## 6. Airflow/Docker 로컬값 생성

아래 값들은 Cloudflare secret이 아니라 로컬 Docker Compose 실행값이다.

```bash
id -u
openssl rand -hex 16
openssl rand -hex 24
openssl rand -hex 32
```

Fernet key는 다음 중 하나로 만든다.

로컬 Python에 `cryptography`가 있는 경우:

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

로컬에 패키지가 없으면 구현에서 사용할 Airflow 이미지로 생성한다.

```bash
docker run --rm <airflow-image> python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

`.env`에는 다음처럼 넣는다.

```dotenv
AIRFLOW_UID=<id-u-result>
AIRFLOW_ADMIN_USERNAME=admin
AIRFLOW_ADMIN_PASSWORD=<openssl-rand-hex-16>
AIRFLOW_ADMIN_EMAIL=<your-email>

POSTGRES_USER=airflow
POSTGRES_PASSWORD=<openssl-rand-hex-24>
POSTGRES_DB=airflow

AIRFLOW_FERNET_KEY=<generated-fernet-key>
AIRFLOW_SECRET_KEY=<openssl-rand-hex-32>
```

## 7. 최종 `.env` 형태

```dotenv
# Cloudflare account
CLOUDFLARE_ACCOUNT_ID=<your-account-id>
CLOUDFLARE_API_TOKEN=<optional-bootstrap-token>

# R2/Data Catalog fixed names
R2_BUCKET_NAME=seoul
TRINO_ICEBERG_CATALOG=iceberg
SMOKE_SCHEMA=ops_smoke

# R2 S3-compatible access
R2_ENDPOINT=https://<your-account-id>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=<r2-access-key-id>
R2_SECRET_ACCESS_KEY=<r2-secret-access-key>

# R2 Data Catalog / Iceberg REST catalog
R2_DATA_CATALOG_TOKEN=<r2-api-token-value>
R2_DATA_CATALOG_URI=<catalog-uri>
R2_DATA_CATALOG_WAREHOUSE=<warehouse>

# Optional
WRANGLER_R2_SQL_AUTH_TOKEN=

# Airflow local runtime
AIRFLOW_UID=<id-u-result>
AIRFLOW_ADMIN_USERNAME=admin
AIRFLOW_ADMIN_PASSWORD=<generated-password>
AIRFLOW_ADMIN_EMAIL=<your-email>
AIRFLOW_FERNET_KEY=<generated-fernet-key>
AIRFLOW_SECRET_KEY=<generated-secret-key>

# Airflow metadata DB
POSTGRES_USER=airflow
POSTGRES_PASSWORD=<generated-postgres-password>
POSTGRES_DB=airflow
```

## 8. 값 준비 후 확인 순서

1. `.env`를 만들고 실제 값을 채운다.
2. `npx wrangler r2 bucket list`와 `npx wrangler r2 bucket info seoul`로 bucket이 보이는지 확인한다.
3. `npx wrangler r2 bucket catalog get seoul`로 Data Catalog 상태와 warehouse를 확인한다.
4. `Catalog URI`와 `Warehouse`가 `.env`의 `R2_DATA_CATALOG_URI`, `R2_DATA_CATALOG_WAREHOUSE`에 들어갔는지 확인한다.
5. `R2_DATA_CATALOG_TOKEN`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`가 같은 runtime용 R2 API token에서 나온 값인지 확인한다.
6. `R2_ENDPOINT`의 account id가 `CLOUDFLARE_ACCOUNT_ID`와 같은지 확인한다.
7. `.env`가 git에 올라가지 않도록 `.gitignore`에 포함한다.
8. `./scripts/check-r2-catalog-auth.sh`로 `R2_DATA_CATALOG_TOKEN`이 `R2_DATA_CATALOG_WAREHOUSE`에 접근 가능한지 확인한다.
9. `.env`를 바꾼 뒤에는 Trino를 재생성한다.

```bash
docker compose up -d --force-recreate trino
```

`./scripts/check-r2-catalog-auth.sh`가 `403`과 `Insufficient permission for R2 Data Catalog Warehouse`를 출력하면 Trino 설정 문제가 아니라 Cloudflare R2 API token 권한 또는 warehouse scope 문제다. 이 경우 `seoul` bucket/catalog/warehouse에 대해 R2 storage read/write와 R2 Data Catalog 접근 권한을 가진 runtime용 R2 API token을 새로 만들고 `.env`의 `R2_DATA_CATALOG_TOKEN`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`를 같은 token 세트에서 다시 채운다.

현재 확인된 성공 기준:

```text
R2 Data Catalog auth check HTTP status: 200
R2 Data Catalog token can access the configured warehouse.
```

end-to-end smoke DAG 성공 run:

```text
dag_id: common_dbt_smoke
run_id: manual__2026-06-27T14:29:09.888034+00:00
state: success
```

선택적으로 Wrangler의 R2 SQL까지 점검하려면 `WRANGLER_R2_SQL_AUTH_TOKEN`을 채운 뒤 warehouse 이름으로 간단한 query를 실행한다.

```bash
export WRANGLER_R2_SQL_AUTH_TOKEN=<r2-sql-token>
npx wrangler r2 sql query <warehouse> "SELECT * FROM <namespace>.<table_name> LIMIT 10;"
```

## 9. 참고 문서

- Cloudflare R2 Data Catalog manage catalogs: https://developers.cloudflare.com/r2/data-catalog/manage-catalogs/
- Cloudflare R2 Data Catalog Trino config: https://developers.cloudflare.com/r2/data-catalog/config-examples/trino/
- Cloudflare R2 API token authentication: https://developers.cloudflare.com/r2/api/tokens/
- Cloudflare R2 SQL query data: https://developers.cloudflare.com/r2-sql/query-data/
- Apache Airflow Docker Compose guide: https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/index.html
