# Airflow + Trino + dbt + Cloudflare Iceberg 인터뷰 정리

- 작성일: 2026-06-27
- 목적: 별도 인프라 디렉터리에서 Airflow, Trino, dbt, Cloudflare R2 Data Catalog/Iceberg 기반 실행 환경과 멘토/멘티 운영 모델을 만들기 위한 요구사항 정리
- 현재 상태: 요구사항 인터뷰 완료 후 첫 버전 scaffold 구현과 end-to-end smoke 검증 완료. 일부 보안/확장 세부값은 추후 결정 항목으로 남김.

## 1. 목표

Airflow가 dbt를 실행하고, dbt는 Trino를 실행 엔진으로 사용한다.

Trino는 Cloudflare R2 Data Catalog의 Iceberg REST catalog에 연결해야 하며, dbt 작업에서 Iceberg 테이블 조회, 생성, 삭제가 가능해야 한다.

첫 버전은 실제 비즈니스 dbt 모델을 만드는 것이 아니라, prod용 공용 실행 인프라를 만들고 end-to-end로 잘 동작하는지 확인하는 것이 목표다.

추가 목표는 멘토 1명이 5명의 멘티에게 ELT 개발/배포 환경을 제공하는 것이다. 멘티는 각자 도메인 데이터를 수집하고 DAG/dbt 작업을 만들 수 있어야 하지만, 멘토의 개인 Cloudflare credential이나 개인 정보를 직접 공유하지 않는 것을 기본 원칙으로 둔다.

공유 Cloudflare/R2/Data Catalog 환경은 prod용으로만 둔다. 별도의 shared dev 환경은 만들지 않는다. 멘티의 개발 검증은 로컬 Docker Compose와 개인 Cloudflare 계정 기반 검증으로 처리한다.

## 2. 확정된 아키텍처

### 실행 구조

- Docker 기반으로 Airflow와 Trino를 띄운다.
- Airflow 안에서 dbt smoke DAG를 실행한다.
- dbt는 `dbt-trino` adapter를 사용해 Trino에 연결한다.
- Trino는 Cloudflare R2 Data Catalog를 Iceberg REST catalog로 사용한다.
- 현재 구현은 Airflow `3.2.2`, dbt `1.10.22`, dbt-trino `1.10.2`를 사용한다.
- dbt는 Airflow Python dependency와 충돌하지 않도록 Airflow image 안의 별도 virtualenv에 설치한다.

### 메달리언 구조

- `bronze = raw`로 정의한다.
- `bronze/raw`는 각 도메인의 원천 레이어다.
- schema/namespace는 멘티 또는 도메인 구분에 사용한다.
- 레이어 구분은 schema가 아니라 테이블 이름 prefix로 표현한다.
- 첫 버전에서 멘티가 직접 추가하는 작은 입력 데이터는 R2 직접 업로드가 아니라 `dbt seed`로 재현 가능하게 관리한다.

### Trino catalog/namespace 구조

첫 버전은 Cloudflare R2 bucket 하나에 R2 Data Catalog 하나를 enable하고, Trino catalog도 하나만 둔다.

Trino catalog 이름은 `iceberg`로 둔다.

| Trino namespace | 역할 | 쓰기 정책 |
| --- | --- | --- |
| `iceberg.<domain>` | 멘티/도메인별 prod 데이터 | 해당 도메인의 DAG/dbt가 관리 |
| `iceberg.ops_smoke` | 인프라 smoke test 전용 | smoke DAG만 생성/조회/삭제 |

Trino의 테이블 전체 이름은 `catalog.schema.table` 형태다. 첫 버전에서는 `catalog = iceberg`로 고정하고, `schema/namespace = domain`으로 둔다.

예시:

```sql
-- weather 도메인의 raw/bronze 원천 테이블
iceberg.weather.raw_events

-- weather 도메인의 변환 중간 테이블
iceberg.weather.stg_events

-- weather 도메인의 mart/gold 산출 테이블
iceberg.weather.mart_event_counts

-- infra smoke test 전용 테이블
iceberg.ops_smoke.sample_events
```

이 방식은 schema를 도메인 경계로 남겨두고, layer는 `raw_`, `stg_`, `mart_` 같은 table prefix로 표현한다. 나중에 도메인별 물리 격리, 비용 분리, 권한 분리가 중요해지면 bucket/Data Catalog를 분리하는 구조로 확장한다.

### prod용 공용 환경 보호 원칙

이 환경에는 shared dev가 없으므로, Airflow/dbt가 쓰는 모든 Cloudflare R2/Iceberg 작업은 prod용 작업으로 본다.

기본 방어선은 domain ownership, PR review, reserved schema 보호다.

- 각 멘티는 자기 도메인 schema, 예: `iceberg.weather`, `iceberg.finance` 안의 DAG/dbt 작업을 관리한다.
- 다른 도메인의 schema/table을 삭제하거나 변경하는 작업은 멘토 승인이 필요하다.
- `iceberg.ops_smoke`는 인프라 smoke DAG 전용 schema로 예약한다.
- smoke DAG는 `iceberg.ops_smoke`에서만 테이블 생성/조회/삭제 검증을 수행한다.
- 첫 버전에서는 멘티별 runtime credential 또는 schema-level write isolation까지 완성하지 않는다.
- Trino access control은 `ops_smoke` 같은 예약 schema 보호와 향후 도메인별 권한 분리에 사용할 수 있게 구성 여지를 둔다.

의미:

- `prod`라는 별도 schema/catalog를 만들지 않는다.
- prod 보호는 "prod schema 쓰기 금지"가 아니라 "공용 prod 환경에서 자기 도메인 밖을 건드리지 않기"가 핵심이다.
- Airflow가 prod credential로 실행되므로, repo merge 권한과 PR review가 실질적인 prod 변경 통제 수단이다.
- 나중에 멘티별 Airflow connection 또는 Trino user/role을 분리하면 schema-level write 권한까지 강제할 수 있다.

예시:

```sql
-- 허용: weather 도메인 DAG/dbt가 자기 schema에 테이블을 만든다.
CREATE TABLE iceberg.weather.raw_events AS
SELECT *
FROM iceberg.ops_smoke.sample_events;

-- 허용: weather 도메인 DAG/dbt가 자기 schema 안에서 변환한다.
CREATE TABLE iceberg.weather.mart_event_counts AS
SELECT event_type, count(*) AS event_count
FROM iceberg.weather.raw_events
GROUP BY event_type;

-- 멘토 승인 필요: weather 작업이 finance 도메인 테이블을 삭제한다.
DROP TABLE iceberg.finance.raw_transactions;

-- 금지: 일반 도메인 작업이 smoke 전용 schema를 변경한다.
DROP TABLE iceberg.ops_smoke.sample_events;

-- 허용: 다른 도메인 데이터를 읽는 것은 케이스별로 PR에서 검토한다.
SELECT *
FROM iceberg.finance.mart_daily_revenue
LIMIT 10;
```

여기서 `iceberg`가 Trino catalog 이름이고, `weather`, `finance`, `ops_smoke`가 schema/namespace 이름이다.

## 3. 멘토/멘티 운영 모델

### 배포 제어면

prod 환경의 기본 제어면은 Cloudflare 콘솔 직접 접근이 아니라 Airflow DAG 배포다.

- DAG repository를 prod Airflow DAG 디렉터리와 git sync한다.
- 멘티는 자기 도메인의 DAG/dbt 변경을 PR로 올리고, 서로 리뷰한 뒤 merge할 수 있다.
- DAG가 prod credential로 실행될 수 있으므로, prod로 sync되는 DAG repository의 merge 권한은 prod 실행 권한에 가깝게 취급한다.
- prod 환경 직접 접근은 예외 상황에서만 승인하에 허용한다.

### 초기 prod merge policy

멘티 peer review만으로 허용하는 변경:

- 자기 도메인의 DAG 추가/수정
- 자기 도메인의 dbt model/test/source/schema 수정
- 자기 도메인의 `dbt seed` CSV 추가/수정
- 비용 영향이 작고 실행 빈도가 낮은 스케줄 변경

멘토 승인이 필요한 변경:

- Cloudflare bucket, R2 Data Catalog, Trino catalog, Airflow 설정 등 공용 인프라 변경
- prod runtime secret, R2 access key, Data Catalog token, Airflow connection 변경
- `dbt seed`가 아닌 R2 직접 업로드/landing 경로 추가
- 공용 prod 환경의 domain boundary, reserved schema, cleanup 정책, 권한 정책 변경
- 대량 backfill, 고빈도 스케줄, 비용 영향이 큰 DAG 추가
- 다른 멘티 도메인의 테이블이나 데이터를 삭제/변경하는 작업

### 로컬 개발 원칙

- 멘티 로컬 개발은 멘토의 prod Cloudflare credential에 의존하지 않는다.
- 최소 검증 경로는 Docker Compose 기반 로컬 smoke test다.
- 실제 Cloudflare R2/Data Catalog 연동까지 로컬에서 검증하고 싶은 멘티는 본인 Cloudflare 계정을 사용한다.
- 멘토가 새로 만든 Cloudflare 계정은 prod/shared runtime용으로 보고, 멘티 로컬 credential 배포용으로 사용하지 않는다.

### 멘티 데이터 반입 정책

첫 버전에서 멘티가 repo에 포함하고 싶은 데이터는 `dbt seed`를 공식 경로로 안내한다.

`dbt seed`에 적합한 데이터:

- 작은 CSV
- 정적이거나 자주 바뀌지 않는 데이터
- 코드표, 매핑 테이블, 샘플 데이터, 수업용 fixture
- Git에 커밋해도 되는 공개/비민감 데이터

`dbt seed`에 넣지 않는 데이터:

- 대용량 원천 데이터
- 자주 갱신되는 API 원문 또는 수집 dump
- 개인정보, 비밀번호, API token, 민감 데이터
- Git repository를 데이터 저장소처럼 쓰게 만드는 파일

R2 직접 업로드, landing/raw upload prefix, 장기 보존/lifecycle 정책은 첫 버전 범위 밖으로 둔다. 나중에 대용량 원천 데이터가 필요해지면 `landing/` 또는 `raw_uploads/` prefix와 보존/cleanup 정책을 별도로 설계한다.

## 4. Cloudflare 리소스 토폴로지

현재 Cloudflare 쪽 R2 Data Catalog 리소스는 없는 상태이므로 생성해야 한다.

첫 버전 bootstrap 대상은 1개 R2 bucket + Data Catalog enable이다.

| Bucket/Catalog 목적 | 설명 |
| --- | --- |
| `seoul` | 멘티 도메인 schema와 smoke schema를 담는 단일 Iceberg catalog backing bucket |

bucket naming convention은 Cloudflare R2에 실제로 만들 bucket 이름을 어떤 규칙으로 정할지에 대한 결정이다.

첫 버전 규칙:

- bucket name: `seoul`
- Trino catalog name: `iceberg`
- Iceberg schema/namespace: `<domain>`, `ops_smoke`

이름을 이렇게 고정하면 bootstrap script, `.env.example`, Trino catalog 설정, README가 같은 이름을 기준으로 작성될 수 있다.

참고: 첫 버전에서는 bucket을 하나만 둔다. schema는 환경 구분이 아니라 멘티/도메인 구분에 사용한다. `ops_smoke`는 인프라 검증 전용 예약 schema다.

이 bucket에 R2 Data Catalog를 enable하면 `Warehouse`와 `Catalog URI`가 나온다. 이 값들을 `.env`에 저장하고 Trino catalog properties에서 참조한다.

Cloudflare 계정은 멘토 개인 계정과 분리된 새 계정을 사용한다. prod/shared runtime에 필요한 credential은 Airflow/Trino runtime secret으로만 관리하고, 멘티 로컬 개발용으로 배포하지 않는다.

공식 문서 기준 예시 명령:

```bash
npx wrangler r2 bucket create seoul
npx wrangler r2 bucket catalog enable seoul
```

## 5. 로컬 준비물

Cloudflare 관련 로컬 준비물은 키파일보다는 `.env`에 넣을 토큰/키/엔드포인트 세트로 본다. 단, 아래 값들은 prod/shared runtime 구성에 필요한 값이며 멘티에게 공통 배포하지 않는다. 멘티가 Cloudflare 연동까지 로컬에서 검증하려면 각자 본인 Cloudflare 계정의 값을 사용한다.

| 변수 | 용도 |
| --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | R2 endpoint 구성 |
| `CLOUDFLARE_API_TOKEN` | Wrangler bootstrap용 Cloudflare API token |
| `R2_ACCESS_KEY_ID` | Trino가 R2 객체를 읽고 쓰는 S3 호환 access key |
| `R2_SECRET_ACCESS_KEY` | Trino가 R2 객체를 읽고 쓰는 S3 호환 secret key |
| `R2_ENDPOINT` | 보통 `https://<account_id>.r2.cloudflarestorage.com` |
| `R2_DATA_CATALOG_TOKEN` | Trino Iceberg REST catalog OAuth2 token |
| `R2_DATA_CATALOG_URI` | `seoul` bucket에서 enable한 catalog URI |
| `R2_DATA_CATALOG_WAREHOUSE` | `seoul` bucket에서 enable한 warehouse |
| `WRANGLER_R2_SQL_AUTH_TOKEN` | 선택. Wrangler R2 SQL/Data Catalog 점검용 |

주의:

- `R2_SECRET_ACCESS_KEY`는 생성 직후 다시 볼 수 없을 수 있으므로 안전하게 보관해야 한다.
- `R2_ACCESS_KEY_ID`와 `R2_SECRET_ACCESS_KEY`는 S3-compatible object access용이고, `R2_DATA_CATALOG_TOKEN`은 Iceberg REST catalog 접근용이다.
- `Object Read & Write`만 있는 R2 key는 Data Catalog warehouse 접근에는 부족할 수 있다.
- `R2_DATA_CATALOG_TOKEN`에는 `seoul` Data Catalog warehouse 접근 권한이 있어야 하며, 부족하면 `Insufficient permission for R2 Data Catalog Warehouse`가 발생한다.
- 실제 secret 값은 저장소에 커밋하지 않는다.
- repo에는 `.env.example`만 둔다.
- prod credential은 Airflow/Trino runtime secret 또는 배포 환경의 `.env`에만 둔다.
- 멘티 로컬용 `.env`는 개인 계정 또는 로컬 smoke 전용 값으로 채운다.

## 6. 첫 버전 산출물

첫 버전은 문서와 자동화 스크립트를 둘 다 제공한다.

구현 산출물:

- Docker compose
- Trino 설정
- Airflow 이미지 또는 환경 설정
- dbt smoke project
- dbt seed 예시 및 seed 사용 가이드
- Airflow smoke DAG
- `.env.example`
- Cloudflare bootstrap script
- R2 Data Catalog auth check script
- README 또는 운영 문서

Cloudflare bootstrap script 범위:

- `seoul` R2 bucket 생성
- `seoul` bucket의 R2 Data Catalog enable
- 출력된 `Warehouse`, `Catalog URI`를 사용자가 `.env`에 옮길 수 있게 안내

## 7. 구현 기본값

### repository

이 인프라는 별도 repository로 관리하되, repository root는 현재 경로인 `/home/dwlee/infra`로 둔다.

### Docker Compose

- compose project name: `elt-infra`
- services: `postgres`, `airflow-init`, `airflow-apiserver`, `airflow-scheduler`, `airflow-dag-processor`, `airflow-triggerer`, `trino`
- network: `elt_net`
- volumes: `postgres_data`, `airflow_logs`

### local ports

- Airflow web UI host port: `30585`
- Trino는 기본적으로 Docker network 내부에서만 접근한다.
- host에서 Trino CLI 또는 browser로 직접 접속해야 하면 나중에 `30586:8080` 매핑을 추가한다.

### dbt/Airflow names

- dbt project name: `elt_smoke`
- dbt profile name: `elt_smoke`
- dbt profile target: `prod`
- Airflow DAG id: `dbt_trino_iceberg_smoke`
- smoke seed name: `sample_events`
- smoke model name: `smoke_event_counts`

## 8. 검증 기준

첫 버전은 아래가 통과하면 성공으로 본다.

1. bootstrap 스크립트로 `seoul` R2 bucket 생성 및 Data Catalog enable 가능
2. Trino가 `iceberg` catalog를 로드
3. Airflow에서 dbt smoke DAG 실행 가능
4. dbt smoke가 `iceberg.ops_smoke.sample_events` seed table을 생성
5. downstream smoke model이 `iceberg.ops_smoke.smoke_event_counts`를 생성하고 seed table을 참조
6. smoke 종료 시 `iceberg.ops_smoke` 안의 샘플 테이블 drop 또는 cleanup 가능
7. 일반 도메인 schema, 예: `iceberg.weather`, `iceberg.finance`를 README 예시로 안내
8. README에 멘티 로컬 개발 방식, seed 사용 기준, prod merge policy가 명시됨

현재 검증 결과:

- `./scripts/check-r2-catalog-auth.sh`가 HTTP `200` 반환
- Trino `SHOW CATALOGS`에서 `iceberg` catalog 확인
- Trino `CREATE SCHEMA IF NOT EXISTS iceberg.ops_smoke` 성공
- Airflow DAG `dbt_trino_iceberg_smoke` 성공
- 성공 run id: `manual__2026-06-27T14:29:09.888034+00:00`
- task 상태: `prepare_smoke_schema`, `seed_sample_events`, `run_smoke_model`, `test_smoke_relations`, `cleanup_smoke` 모두 success
- cleanup 후 `SHOW TABLES FROM iceberg.ops_smoke` 결과는 비어 있음

## 9. 명시적 Non-goals

첫 버전에 포함하지 않는다.

- 실제 비즈니스 dbt 모델 작성
- prod 스케줄 운영 정책 수립
- BI 연동
- 기존 pseudolab catalog UI 연동
- 세밀한 권한 모델 설계
- 운영용 권한 분리/감사 체계 완성
- 멘티에게 prod Cloudflare credential 배포
- R2 직접 업로드/landing 경로 구현
- 대용량 원천 데이터 수집/보존 정책 구현
- 민감 데이터, 개인정보, 비밀번호, API token을 포함한 seed 또는 raw data 취급
- 완전 자동 CI/CD 승인 체계 구축

## 10. 추후 인터뷰 항목

아래는 일부러 보류한 결정이다.

- Cloudflare API token permission 범위의 최소화 수준
- 추후 R2 직접 업로드/landing 경로가 필요할 때 prefix, lifecycle, 보존 정책을 어떻게 둘지

## 11. 참고 문서

- Cloudflare R2 Data Catalog Trino config: https://developers.cloudflare.com/r2/data-catalog/config-examples/trino
- Cloudflare R2 Data Catalog get started: https://developers.cloudflare.com/r2/data-catalog/get-started/
- Cloudflare R2 Data Catalog manage catalogs: https://developers.cloudflare.com/r2/data-catalog/manage-catalogs/
- Cloudflare R2 SQL query via Wrangler: https://developers.cloudflare.com/r2-sql/query-data/
- dbt Trino setup: https://docs.getdbt.com/docs/core/connect-data-platform/trino-setup
- dbt seeds: https://docs.getdbt.com/docs/build/seeds
- Trino Iceberg REST catalog/metastore docs: https://trino.io/docs/current/object-storage/metastores.html
- Trino access control: https://trino.io/docs/current/security/file-system-access-control.html
