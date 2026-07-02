# AGENTS.md

이 파일은 `ask-seoul-sample` 작업 시 에이전트가 반드시 따르는 최소 규칙이다.

## 프로젝트 맥락

- 이 repo는 Airflow, Trino, dbt, Cloudflare R2/Data Catalog/Iceberg 연결을 검증하는 실행 허브다.
- `dags/`는 `ASAC-DAG` submodule이고, `dbt/`는 `ASAC-DBT` submodule이다.
- root `sample`, `dags`, `dbt`는 각각 별도 Git repo로 보고 상태와 커밋을 따로 확인한다.
- 현재 목표는 실제 API 데이터를 멘토님이 정한 smoke flow에 태워 end-to-end로 검증하는 것이다.
- 기본 흐름은 `Airflow API 수집 -> R2 raw upload -> Trino Iceberg bronze -> dbt silver/gold -> Trino final query`다.

## 협업 브랜치 원칙

- 개발/테스트는 dev 기준으로 진행하고, PR도 우선 dev를 base로 올린다.
- prod/main 반영은 dev 통합 테스트 후 팀/멘토 승인 뒤 진행한다.
- submodule 내부 변경은 해당 repo에서 먼저 브랜치/커밋/PR을 만들고, root는 필요한 경우 submodule pointer만 갱신한다.
- `.gitmodules`의 기본 main 추적 의도는 함부로 바꾸지 않는다. dev 협업 흐름이 필요하면 별도 문서나 명시적 승인 후 변경한다.
- 사용자의 명시 승인 없이 `git commit`, `git push`, PR 생성, destructive git 명령을 실행하지 않는다.

## 이슈 기반 작업 플로우

- 기능 추가, 버그 수정, 데이터 적재 작업은 먼저 해당 GitHub repo에 이슈를 만든다.
- 이슈는 팀 공용 issue template form 중 작업 성격에 맞는 것을 선택해 작성한다.
- 이슈/PR을 작성하기 전 sibling repo `../asac-org-github/.github`의 공용 템플릿을 먼저 확인한다.
- 이슈는 `ISSUE_TEMPLATE/feature_request.yml`, `ISSUE_TEMPLATE/data-ingestion.yml`, `ISSUE_TEMPLATE/bug_report.yml` 중 작업 성격에 맞는 항목/필수 필드를 유지한다.
- 이미 관련 이슈가 있으면 새로 만들지 않고 기존 이슈를 기준으로 작업한다.
- 브랜치는 이슈 번호를 포함해 dev에서 딴다. 예: `feat/52-weather-grid-coverage`, `fix/44-traffic-bronze-validation`.
- 작업은 변경 대상 repo에서 진행한다. DAG는 `dags/`, dbt는 `dbt/`, 실행환경은 sample root다.
- PR은 dev를 base로 올리고, 본문에는 연결 이슈, 변경 요약, 검증 결과, 데이터 적재 작업이면 raw 경로와 table 영향을 적는다.
- PR 본문은 `../asac-org-github/.github/PULL_REQUEST_TEMPLATE.md`의 섹션과 체크리스트를 기준으로 작성한다. `gh pr create`를 쓸 때도 이 템플릿을 복사한 UTF-8 body file을 만든다.
- GitHub issue/PR 본문에 한글이 있으면 UTF-8 markdown 파일을 `--body-file`로 넘기고, 생성 후 `gh issue view` 또는 `gh pr view`로 깨짐 여부를 확인한다.

## 작업 경계

- 파일 수정 전에는 어떤 파일을 왜 바꾸는지 짧게 알린다.
- 큰 경계마다 멈추고 진행 상황을 보고한 뒤 넘어갈지 확인한다.
- 사용자가 만든 변경사항을 되돌리지 않는다. 충돌하면 먼저 상태를 설명한다.
- repo 탐색은 `rg`, `rg --files`, `git status`, `git diff`를 우선 사용한다.
- 실행 결과를 보고할 때 secret 값은 절대 출력하지 않는다.

## 기존 의도 파악

기존 tracked 코드, 설계, 문서를 수정하거나 평가하기 전에는 git 이력으로 의도를 먼저 본다.

필수 조회:

```bash
git log --follow -p -- <file>
git blame -L <start>,<end> -- <file>
git show <hash>
```

submodule 파일이면 해당 submodule 안에서 조회한다.

```bash
git -C dags log --follow -p -- <file>
git -C dbt log --follow -p -- <file>
```

응답이나 수정 전에는 파악한 의도를 1-2문장으로 먼저 요약한다.

예외:

- 새 파일
- 커밋이 1개뿐인 파일
- 명백한 오타, 포매팅, import 정리
- git 이력과 무관한 일반 설명
- 사용자가 명시적으로 이력 조회를 생략하라고 한 경우

## STOP-FIRST

제안이나 수정이 기존 의도를 깨면 같은 턴에 결론, 코드, patch, 평가를 내지 않는다.

위반 예:

- race, deadlock, regression, do not, fixes 등으로 보호된 결정을 뒤집음
- 과거에 기각된 대안을 다시 도입함
- 기존 edge case, 실패 경로, idempotency, ordering, atomicity를 깨뜨림
- 의도 확인 없이 "불필요하다", "잘못됐다"고 평가함

이 경우 정확히 아래 형식으로 멈춘다.

```text
⚠️ 의도 위반 가능성

깨지는 의도: <한 문장>
출처: <커밋 해시 / PR 번호 / 라인>
원래 회피하려던 시나리오: <구체적으로>
내 제안/평가가 이걸 깨는 이유: <한 문장>
선택지:
 A) 의도 유지 — <우회 방법 또는 평가 보류 사유>
 B) 의도 폐기 — 이 경우 감수해야 할 리스크: <구체적>

어느 쪽으로 갈지 알려줘.
```

## 환경과 secret

- `.env`, `.env.*`, API key, R2 key, token, password는 커밋하지 않는다.
- dev 테스트는 `seoul-dev` bucket과 dev schema를 우선 사용한다.
- prod bucket/schema는 팀/멘토 승인 없이 쓰지 않는다.
- R2/Data Catalog 값은 저장소와 Iceberg metadata 접근용이고, `KMA_SERVICE_KEY`, `SEOUL_OPEN_API_KEY`는 외부 API 호출용이다.
- secret 존재 여부는 말해도 되지만 실제 값을 로그, 문서, 응답에 노출하지 않는다.

## 파이프라인 규칙

- 멘토님이 제공한 smoke flow를 우선 따른다. 별도 아키텍처를 임의로 새로 만들지 않는다.
- Bronze는 원본 JSON/XML과 수집 metadata를 추적 가능하게 보존한다.
- Bronze metadata에는 가능한 한 `request_id`, `source_id`, redacted request params, `result_code`, `result_msg`, `collected_at`, `load_date`, `payload_hash`, `raw_object_key`를 둔다.
- Silver는 표준 시간, 타입 캐스팅, 좌표/장소 후보, 중복 제거, source native id 보존을 담당한다.
- Gold는 분석 가능한 요약 table이나 feature mart를 담당한다. Gold에서 처음으로 원천 정규화를 시작하지 않는다.
- 재실행 시 중복 적재가 생길 수 있다고 가정하고 dedup 기준을 명시한다.
- 실패를 조용히 삼키지 말고 Airflow task 실패나 명시적 validation error로 드러낸다.

## Source API 규칙

- KMA는 우선 `getVilageFcst`를 사용하고, 성공 기준은 `response.header.resultCode == "00"`이다.
- KMA `base_date + base_time`은 `issued_at`, `fcstDate + fcstTime`은 `forecast_at`으로 해석한다.
- KMA `serviceKey`는 request metadata, raw path, 로그에 원문으로 남기지 않는다.
- Seoul TOPIS는 우선 `AccInfo` XML 응답을 사용하고, 성공 기준은 `AccInfo/RESULT/CODE == INFO-000`이다.
- TOPIS 시간 값은 `HHMM` 또는 `HHMMSS`일 수 있으므로 6자리 고정으로 가정하지 않는다.
- TOPIS `grs80tm_x`, `grs80tm_y`는 WGS84 위경도가 아니라 GRS80 TM 좌표다.

## 검증과 기록

- 가능하면 Python compile, dbt parse/run/test, Trino final query까지 확인한다.
- 로컬에 dbt가 없으면 Airflow/dbt 컨테이너 또는 멘토님 런타임에서 검증한다.
- end-to-end 검증은 dev R2/dev schema에서 먼저 수행한다.
- 실행 보고에는 DAG run id, 성공/실패 task, 최종 row count, 생성 object/table을 포함한다.
- 이슈와 레슨런은 `LessonRun.md`에 짧고 재사용 가능하게 기록한다.
