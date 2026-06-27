# ELT Infra: Airflow + Trino + dbt + Cloudflare R2 Iceberg

This repository runs a local Docker-based control plane for a shared prod Cloudflare R2 Data Catalog/Iceberg environment.

The first version proves the execution path:

1. Airflow runs a smoke DAG.
2. The DAG runs dbt.
3. dbt connects to Trino.
4. Trino connects to Cloudflare R2 Data Catalog as an Iceberg REST catalog.
5. dbt creates, reads, tests, and drops smoke tables in `iceberg.ops_smoke`.

## Current Status

As of 2026-06-27, the first end-to-end smoke run has passed.

Verified:

- Airflow `3.2.2` API server, scheduler, DAG processor, and triggerer are running.
- dbt runs from an isolated virtualenv in the Airflow image.
- Trino loads the `iceberg` catalog.
- R2 Data Catalog auth check returns HTTP `200`.
- The Airflow DAG `dbt_trino_iceberg_smoke` completed successfully.
- `iceberg.ops_smoke` remains as the reserved smoke schema, and smoke tables are dropped by cleanup.

## Fixed Names

| Item | Value |
| --- | --- |
| R2 bucket | `seoul` |
| Trino catalog | `iceberg` |
| Smoke schema | `ops_smoke` |
| Airflow web port | `30585` |
| Airflow DAG | `dbt_trino_iceberg_smoke` |
| dbt project/profile | `elt_smoke` |
| Airflow version | `3.2.2` |
| dbt version | `1.10.22` |
| dbt-trino version | `1.10.2` |

## Files

| Path | Purpose |
| --- | --- |
| `docker-compose.yml` | Postgres, Trino, Airflow init/API server/scheduler/DAG processor/triggerer |
| `Dockerfile.airflow` | Airflow 3.2.2 image with `dbt-core` and `dbt-trino` installed in an isolated venv |
| `trino/catalog/iceberg.properties` | Trino Iceberg REST catalog config |
| `dbt/elt_smoke` | dbt smoke project |
| `dags/dbt_trino_iceberg_smoke.py` | Airflow DAG for dbt smoke run |
| `scripts/bootstrap-cloudflare.sh` | R2 bucket/Data Catalog bootstrap helper |
| `scripts/check-r2-catalog-auth.sh` | Verifies the R2 Data Catalog token can access the configured warehouse |
| `.env.example` | Required local values without secrets |

## Prepare `.env`

Create `.env` from `.env.example` and fill the real values. Do not commit `.env`.

Required Cloudflare runtime values:

- `CLOUDFLARE_ACCOUNT_ID`
- `R2_ENDPOINT`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_DATA_CATALOG_TOKEN`
- `R2_DATA_CATALOG_URI`
- `R2_DATA_CATALOG_WAREHOUSE`

`R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` are for R2 object storage access. `R2_DATA_CATALOG_TOKEN` is for the Iceberg REST catalog. The runtime token must have both R2 object access and R2 Data Catalog warehouse access for `seoul`. Object Read & Write alone is not enough for the Iceberg REST catalog and returns `403` with `Insufficient permission for R2 Data Catalog Warehouse`.

Required Airflow/Postgres local values:

- `AIRFLOW_UID`
- `AIRFLOW_ADMIN_USERNAME`
- `AIRFLOW_ADMIN_PASSWORD`
- `AIRFLOW_ADMIN_EMAIL`
- `AIRFLOW_FERNET_KEY`
- `AIRFLOW_SECRET_KEY`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`

`CLOUDFLARE_API_TOKEN` can stay empty when you use `npx wrangler login` locally. `WRANGLER_R2_SQL_AUTH_TOKEN` is only needed for optional Wrangler R2 SQL checks.

## Bootstrap Cloudflare

If the `seoul` bucket or Data Catalog does not exist yet:

```bash
./scripts/bootstrap-cloudflare.sh
```

The script creates or verifies the bucket and enables or verifies the Data Catalog. It does not create runtime R2 API tokens, because Cloudflare shows secret values only at token creation time.

After creating or rotating runtime credentials, run:

```bash
./scripts/check-r2-catalog-auth.sh
docker compose up -d --force-recreate trino
```

## Start Local Services

Initialize Airflow metadata and admin user:

```bash
docker compose up airflow-init
```

Start Airflow and Trino:

```bash
docker compose up -d
```

Open Airflow:

```text
http://localhost:30585
```

Use the credentials from `.env`.

## Run Smoke DAG

Trigger `dbt_trino_iceberg_smoke` from the Airflow UI, or run:

```bash
docker compose exec airflow-scheduler airflow dags trigger dbt_trino_iceberg_smoke
```

The DAG runs:

1. `dbt run-operation prepare_smoke_schema`
2. `dbt seed --full-refresh --select sample_events`
3. `dbt run --select smoke_event_counts`
4. `dbt test --select sample_events smoke_event_counts`
5. `dbt run-operation cleanup_smoke`

The cleanup step drops `iceberg.ops_smoke.smoke_event_counts` and `iceberg.ops_smoke.sample_events`.

## Direct Checks

Trino is only exposed on the Docker network. Use `docker compose exec` for direct checks:

```bash
docker compose exec trino trino --execute "SHOW CATALOGS"
docker compose exec trino trino --execute "SHOW SCHEMAS FROM iceberg"
```

Check that the R2 Data Catalog token can access the configured warehouse:

```bash
./scripts/check-r2-catalog-auth.sh
```

If this returns `403` with `Insufficient permission for R2 Data Catalog Warehouse`, recreate the Cloudflare R2 API token with R2 storage read/write and R2 Data Catalog warehouse access for the `seoul` catalog/warehouse, then update `.env`.

When `.env` changes, recreate Trino so it receives the new environment values:

```bash
docker compose up -d --force-recreate trino
```

Run dbt directly from the Airflow image:

```bash
docker compose run --rm --no-deps --workdir /opt/airflow/dbt/elt_smoke --entrypoint /home/airflow/dbt-venv/bin/dbt airflow-scheduler debug
```

Check the most recent smoke run:

```bash
docker compose exec airflow-scheduler airflow dags list-runs dbt_trino_iceberg_smoke -o json
docker compose exec airflow-scheduler airflow tasks states-for-dag-run dbt_trino_iceberg_smoke <run-id>
```

## Mentee Workflow

The shared Cloudflare/R2/Data Catalog environment is prod. Mentees should not receive the mentor's prod Cloudflare credential.

Allowed with peer review:

- Changes inside a mentee-owned domain schema, such as `iceberg.weather`
- Domain-specific DAG/dbt model/test/source changes
- Small public/non-sensitive `dbt seed` CSV files
- Low-frequency schedule changes with small cost impact

Requires mentor approval:

- Shared infrastructure changes
- Runtime secret changes
- R2 direct upload or landing path design
- Reserved schema changes such as `iceberg.ops_smoke`
- Backfills, high-frequency schedules, or expensive workloads
- Writes or drops outside the mentee-owned domain schema

For local development, mentees should use Docker Compose and either stay at local/dbt validation level or use their own Cloudflare account.

## References

- Cloudflare R2 Data Catalog Trino config: https://developers.cloudflare.com/r2/data-catalog/config-examples/trino/
- Cloudflare R2 Data Catalog get started: https://developers.cloudflare.com/r2/data-catalog/get-started/
- Apache Airflow Docker Compose guide: https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/index.html
- dbt Trino setup: https://docs.getdbt.com/docs/core/connect-data-platform/trino-setup
- Trino Iceberg REST catalog docs: https://trino.io/docs/current/object-storage/metastores.html
