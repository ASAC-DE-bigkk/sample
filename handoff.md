# Handoff - 2026-06-29

## 목적

집에서 MacBook으로 이어서 작업할 수 있도록 오늘 작업 상태, 브랜치, PR, 남은 일을 정리한다.

## 관련 repo

```text
sample root:
  team:     https://github.com/ASAC-DE-bigkk/sample.git

dags submodule:
  team:     https://github.com/ASAC-DE-bigkk/ASAC-DAG

dbt submodule:
  team: https://github.com/ASAC-DE-bigkk/ASAC-DBT
```

## ASAC-DAG PRs

### PR #11 - Weather Bronze

- URL: https://github.com/ASAC-DE-bigkk/ASAC-DAG/pull/11
- Issue: https://github.com/ASAC-DE-bigkk/ASAC-DAG/issues/9
- Branch: `feat/9-kma-vilage-fcst-bronze`
- File: `domains/weather/kma_vilage_fcst_bronze.py`

Status:

- KMA `getVilageFcst` raw JSON upload to R2 dev
- Bronze Iceberg table insert
- PR body updated to `domains/weather/...`
- compile check passed

### PR #14 - Traffic Bronze

- URL: https://github.com/ASAC-DE-bigkk/ASAC-DAG/pull/14
- Issue: https://github.com/ASAC-DE-bigkk/ASAC-DAG/issues/13
- Branch: `feat/13-seoul-traffic-incident-bronze`
- File: `domains/traffic/seoul_traffic_incident_bronze.py`

Status:

- Seoul TOPIS `AccInfo` raw XML upload to R2 dev
- Bronze Iceberg table insert
- PR body updated to `domains/traffic/...`
- dev target default schedule set to every minute
- prod target remains unscheduled unless `ASK_SEOUL_TRAFFIC_DAG_SCHEDULE` is explicitly set
- compile check passed

## MacBook에서 이어받기

```bash
git clone https://github.com/ASAC-DE-bigkk/sample.git ask-seoul-sample
cd ask-seoul-sample
git fetch origin
git submodule update --init --recursive
```

DAG 작업 브랜치 확인:

```bash
cd dags
git remote add team https://github.com/ASAC-DE-bigkk/ASAC-DAG 2>/dev/null || true
git fetch team

git switch feat/13-seoul-traffic-incident-bronze
python -m py_compile domains/traffic/seoul_traffic_incident_bronze.py

git switch feat/9-kma-vilage-fcst-bronze
python -m py_compile domains/weather/kma_vilage_fcst_bronze.py
```

## 오늘 남겨둔 로컬 변경 주의

이 Windows 작업 폴더에는 PR에 포함하지 않은 파일/변경이 남아 있었다.

```text
dags/ask_seoul_api_medallion.py
dbt/elt_smoke/models/silver/silver_kma_vilage_fcst.sql
dbt/elt_smoke/models/silver/silver_seoul_traffic_incident.sql
dbt/elt_smoke/models/gold/gold_ask_seoul_api_ingestion_summary.sql
dbt/elt_smoke/tests/assert_gold_ask_seoul_row_counts_positive.sql
dbt/elt_smoke/models/schema.yml
dbt/elt_smoke/profiles.yml
```

이들은 아직 정리된 PR 범위가 아니다. MacBook에서 이어서 작업할 때는 먼저 현재 원격 브랜치와 로컬 파일을 비교하고, 별도 이슈/PR로 나눌지 결정한다.

## 다음 작업 후보

1. PR #14 dev Airflow run 실행
   - DAG run id
   - task 상태
   - R2 raw object key
   - Bronze row count
   - PR 본문 업데이트

2. Silver/dbt schema contract 합의
   - KMA `base_date + base_time`, `fcstDate + fcstTime`
   - TOPIS `occr_date + occr_time`, `exp_clr_date + exp_clr_time`
   - dedup key
   - source native id
   - GRS80 TM 좌표 처리

3. `dags/common/` 설계
   - 두 DAG 이상에서 반복된 helper만 이동
   - sample root의 `common/`이 아니라 ASAC-DAG repo 안의 `common/`이 Airflow runtime 공통 로직 위치다.

4. 공용 PR 템플릿 공유
   - 이슈는 작업 성격별 YAML form
   - PR은 구현/검증/영향 공유용 공통 Markdown template 유지

## 검증 명령

```bash
cd dags
python -m py_compile domains/weather/kma_vilage_fcst_bronze.py
python -m py_compile domains/traffic/seoul_traffic_incident_bronze.py
```

## 보안

- `.env`는 커밋하지 않는다.
- API key, R2 key, token, password는 로그/PR/문서에 원문으로 남기지 않는다.
- prod bucket/schema는 멘토/팀 승인 전까지 사용하지 않는다.
