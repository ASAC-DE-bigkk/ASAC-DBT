# dbt 초보자 가이드 — commerce (silver/gold 확인·실행법)

dbt 를 처음 다루는 사람을 위한 실전 가이드. **커머스 도메인 기준**으로, "무엇을 어디서 어떻게
확인하는지"를 실제 명령어·출력과 함께 설명한다. (설계 배경은 ASAC-DAG
`dags/domains/commerce/docs/pipeline/medallion-implementation-plan.md`.)

---

## 1. dbt 가 뭘 하는가 (이 프로젝트 한정)

- dbt 는 **SQL 로 데이터 변환(transform)을 관리하는 도구**다. 우리는 이미 Iceberg 에 적재된
  **bronze**(원본층)를 읽어 **silver**(정제·이력)를 만드는 `SELECT` 문들을 관리한다.
- dbt 는 데이터를 직접 옮기지 않는다. **Trino 에 SQL 을 보내** 테이블을 만들 뿐이다.
  (적재는 Airflow `commerce_load_bronze` 가 하고, dbt 는 그 결과를 SQL 로 가공한다.)
- 핵심 개념 3개만 기억하면 된다:
  - **model** = `models/**.sql` 파일 하나 = 만들어질 테이블 하나. 파일 이름 = 테이블 이름.
  - **source** = dbt 가 읽기만 하는 외부 테이블(우리의 bronze). `models/sources.yml` 에 정의.
  - **ref/source 함수** = 모델 간 의존성. `{{ ref('silver_license_history') }}`,
    `{{ source('commerce_bronze','localdata_license') }}`. dbt 가 이걸로 **실행 순서**를 정한다.

데이터 흐름:
```
raw(R2) ──commerce_load_bronze(Airflow)──▶ Iceberg bronze ──dbt(이 프로젝트)──▶ Iceberg silver
```

---

## 2. 이 프로젝트 구조 (파일별 역할)

`dbt/domains/commerce/` 안:

| 파일/폴더 | 역할 |
|---|---|
| `dbt_project.yml` | 프로젝트 설정(이름 `commerce`, 모델 기본 materialized=table) |
| `profiles.yml` | **접속 정보**(Trino host/port, dev=iceberg_dev / prod=iceberg, schema=commerce) |
| `models/sources.yml` | **읽을 bronze 테이블 선언** + 소스 검증 테스트 |
| `models/silver/silver_license_history.sql` | 업소 상태 변경 이력(정제된 변경로그, 암묵 버저닝) |
| `models/silver/silver_license_current.sql` | 현재 상태(업소당 최신 1행) |
| `models/schema.yml` | 모델 컬럼 설명 + not_null/unique 테스트 |
| `tests/*.sql` | 커스텀 검증(그레인 유일성·발행 게이트·연속중복 등) |
| `target/` | dbt 가 생성하는 산출물(컴파일된 SQL·실행 결과). git 무시. **여기서 실제 SQL 을 본다** |
| `logs/dbt.log` | 실행 로그 |

> 모델 파일은 `SELECT` 만 쓴다. `CREATE TABLE` 은 dbt 가 자동으로 감싼다(materialized=table).

---

## 3. 실행 환경 (어디서 돌리나)

dbt 는 **Airflow 이미지 안의 별도 venv**(`/home/airflow/dbt-venv`)에 설치돼 있다. 항상 컨테이너
안에서 돌린다. 매번 아래 3개 env 를 잡아준다:

```bash
docker compose exec -T airflow-scheduler bash -lc '
cd /opt/airflow/dbt/domains/commerce
export DBT_TARGET=dev DBT_PROFILES_DIR=$(pwd) DBT_PROJECT_DIR=$(pwd)
DBT=/home/airflow/dbt-venv/bin/dbt
$DBT <명령어>
'
```
- `DBT_TARGET=dev` → dev 카탈로그(`iceberg_dev`, 버킷 seoul-dev). prod 면 `prod`.
- `DBT_PROFILES_DIR` / `DBT_PROJECT_DIR` → 이 프로젝트 폴더(둘 다 같음, profiles.yml 이 여기 있음).

> 운영에서는 이걸 `commerce_localdata_transform` DAG(후속)이 자동으로 돌린다. 지금은 수동 확인용.

---

## 4. 핵심 명령어 (초보자가 쓸 것만)

순서대로 익히면 된다. **논리를 "확인"하는 명령은 `compile`·`show`, "실행"은 `run`·`test`.**

### 4-1. `dbt debug` — 접속 되나 확인 (제일 먼저)
```
Connection test: OK connection ok
All checks passed!
```
이게 안 나오면 Trino 가 안 떠 있거나 env 가 틀린 것. 여기부터 통과해야 나머지가 된다.

### 4-2. `dbt ls` — 뭐가 있는지 목록
모델·테스트·소스 이름을 나열. "이 프로젝트에 뭐가 있나" 파악용.
```
commerce.silver_license_history
commerce.silver_license_current
commerce.assert_silver_license_history_grain_unique
... (테스트들)
```

### 4-3. `dbt compile` — **실제로 나가는 SQL 보기 (로직 확인의 핵심)**
`.sql` 모델의 `{{ ref }}`/`{{ source }}` 를 실제 테이블명으로 치환한 **완성된 SQL** 을 만들어
`target/compiled/...` 에 저장한다. DB 를 건드리지 않는다. **"이 모델이 실제로 무슨 쿼리를
날리나"를 볼 때 이걸 쓴다.**
```bash
$DBT compile --select silver_license_current
# 결과 SQL 파일:
cat target/compiled/commerce/models/silver/silver_license_current.sql
```
→ `{{ ref('silver_license_history') }}` 가 `iceberg_dev.commerce.silver_license_history` 로
바뀐 실제 SQL 을 볼 수 있다.

### 4-4. `dbt show` — **실행 안 하고 결과 미리보기**
모델 SQL 을 DB 에서 돌려 상위 몇 행만 보여준다(테이블 생성은 안 함). 로직 결과 빠른 확인용.
```bash
$DBT show --select silver_license_current --limit 5
```

### 4-5. `dbt run` — **실제 테이블 생성/갱신**
모델 SQL 로 Trino 에 `CREATE TABLE AS SELECT` 를 실행. 우리 실측:
```
1 of 2 OK created sql table model commerce.silver_license_history .. [CREATE TABLE (1_341_987 rows) in 34.75s]
2 of 2 OK created sql table model commerce.silver_license_current .. [CREATE TABLE (1_341_784 rows) in 18.57s]
Completed successfully
```
- 특정 모델만: `$DBT run --select silver_license_history`
- 그 모델 + 하위 의존까지: `$DBT run --select silver_license_history+`

### 4-6. `dbt test` — **검증 실행**
schema.yml 의 not_null/unique + tests/ 의 커스텀 SQL 검증을 돌린다. 우리 실측:
```
Done. PASS=27 WARN=0 ERROR=0 SKIP=0 TOTAL=27
```
- 테스트 SQL 은 "**틀린 행을 SELECT**"하는 쿼리다. 결과가 0행이면 PASS, 1행이라도 나오면 FAIL.
  예) `tests/assert_silver_license_current_grain_unique.sql` = (dataset,opnsfteamcode,mgtno) 중복을 SELECT →
  중복이 있으면 그 행이 나와 FAIL.

### 4-7. `dbt build` — run + test 한 번에 (의존 순서대로)
실제 운영 흐름. 모델 만들고 바로 그 모델 테스트까지.

---

## 5. 로직을 "확인"하는 3가지 방법

1. **소스(.sql) 읽기** — `models/silver/*.sql`. `with ... as (...)` CTE 를 위에서 아래로 읽으면
   변환 단계가 보인다(아래 §7 모델 설명 참고).
2. **compile 로 실제 SQL 보기** — `target/compiled/.../*.sql`. ref/source 가 치환된 최종 쿼리.
   "dbt Jinja 가 뭘로 바뀌었나" 확실히 볼 때.
3. **run 로그 + target/run/** — 실제 실행된 `CREATE TABLE AS ...` 문과 결과(행수·소요시간).
   에러 시 `logs/dbt.log` 하단에 Trino 에러 원문이 찍힌다.

---

## 6. 결과 데이터 확인 (Trino 조회)

dbt 가 만든 테이블은 Trino 로 직접 조회한다(컨테이너 안):
```bash
docker compose exec -T airflow-scheduler python3 - <<'PY'
import trino.dbapi
c=trino.dbapi.connect(host='trino',port=8080,user='airflow',
                      catalog='iceberg_dev',schema='commerce',http_scheme='http')
cur=c.cursor()
cur.execute("SELECT dataset, trdstatenm, count(*) c FROM silver_license_current "
            "GROUP BY dataset, trdstatenm ORDER BY c DESC LIMIT 5")
print(cur.fetchall()); c.close()
PY
```
실측 결과(현재 상태, 업종×영업상태 상위):
```
general_restaurant 폐업 414,338 | instant_sale_mfg 폐업 138,860 | general_restaurant 영업/정상 120,342 ...
```

**확인 포인트**
- `silver_license_current` 행수 = bronze 유니크 mgtno 수(업소당 1행). 실측 1,341,784.
- `silver_license_history` 행수 ≥ current(변경 이력만큼 더 많음). 실측 1,341,987.
- current = history 에서 업소당 정렬 최신 1행(row_number=1)만 넘어옴.

---

## 7. 커머스 모델이 하는 일 (SQL 로직 요약)

### silver_license_history (이력, 암묵 버저닝)
1. `publishable` — 발행 게이트(`bronze_collection_run_manifest`)에서 `status='SUCCESS' AND
   is_publishable` 인 (dataset, bronze_run_id) 만 추린다. **적재 성공분만 silver 로 넘긴다.**
2. `bronze` — 위 발행분에 해당하는 bronze 행만 inner join. `collected_at` 은 bronze 의 UTC 값을
   **+9h 하여 KST** 로 변환(silver timestamp 는 전부 KST).
3. `parsed` — `record_json` 통짜에서 `json_extract_scalar` 로 컬럼 추출(BPLCNM 업소명,
   TRDSTATENM 영업상태, 주소, 좌표, LASTMODTS 등 — 빈 문자열은 null 로).
   UPDATEDT → timestamp 파싱(**무변환·KST** — 원문이 이미 KST).
4. `normalized`/`keyed` — LASTMODTS → timestamp 파싱(**무변환·KST**), 자치구(구) 파생,
   주소 정규화, 주소 해시 키, 정렬 전용 `updatedt_sort`/`lastmodts_sort`(결측=epoch).
5. `deduped` — **연속(인접) 중복 제거**: 정렬키 기준 직전 행과 content_hash 가 같으면 제거
   (재적재/재유입 노이즈 제거, A→B→A 원복은 보존).

명시적 버전 컬럼은 없다 — `(dataset, opnsfteamcode, mgtno)` 안에서 `updatedt_sort, lastmodts_sort,
observed_date, collected_at, content_hash` **내림차순 정렬이 곧 버전 순서**다.
타임존/결측 규약: [timestamps-and-nulls.md](timestamps-and-nulls.md).

### silver_license_current (현재)
- history 를 위 정렬키 내림차순으로 세워 업소당 최상위 1행(row_number=1)만 선택.
  grain=(dataset, opnsfteamcode, mgtno) — MGTNO 는 발급 자치단체 안에서만 유니크.

### 좌표 보정·gold
- 후속(계획서 Step 8·9). 지금은 미구현.

---

## 8. 자주 겪는 상황

- **에러를 어디서 보나**: 터미널 출력 하단 + `logs/dbt.log` 마지막 부분. Trino 에러 원문(컬럼 없음,
  타입 불일치 등)이 그대로 찍힌다.
- **`Compilation Error ... depends on a source ... not found`**: bronze 테이블이 아직 없음
  → `commerce_load_bronze` 로 적재부터. (silver 는 bronze 가 있어야 돈다.)
- **테스트 FAIL**: FAIL 난 테스트 이름으로 `target/compiled/.../<test>.sql` 을 열어 그 SELECT 를
  Trino 로 직접 돌려보면 **어떤 행이 규칙을 위반했는지** 바로 보인다.
- **다시 깨끗이**: `$DBT run` 은 테이블을 매번 새로 만든다(materialized=table). 그냥 재실행하면 됨.
- **모델 하나만 빠르게**: `--select <모델명>` 으로 범위 좁히기.

---

## 9. 한 줄 치트시트

```bash
cd /opt/airflow/dbt/domains/commerce
export DBT_TARGET=dev DBT_PROFILES_DIR=$(pwd) DBT_PROJECT_DIR=$(pwd); DBT=/home/airflow/dbt-venv/bin/dbt
$DBT debug                                   # 접속 확인
$DBT ls                                       # 목록
$DBT compile --select silver_license_current  # 실제 SQL 보기 → target/compiled/...
$DBT show --select silver_license_current --limit 5   # 결과 미리보기(테이블 생성 X)
$DBT run  --select silver_license_history silver_license_current   # 테이블 생성
$DBT test                                     # 검증(0행=PASS)
```
