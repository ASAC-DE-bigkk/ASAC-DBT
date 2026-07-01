# population 도메인 — dbt (silver / gold)

서울시 실시간 인구혼잡도(citydata_ppltn)의 **bronze → silver → gold** 변환을 담는 dbt
프로젝트입니다. bronze 원본 적재는 ASAC-DAG(`domains/population`)가, 여기서는 그 bronze를
읽어 정제·집계합니다.

## 메달리온 구조

```
bronze (source)   ─ ASAC-DAG가 적재. schema-on-read(원본 payload JSON + 메타데이터)
   │  json_extract로 파싱
   ▼
silver_seoul_ppltn ─ 개별 필드 분해 + (area_nm, ppltn_time) 최신 1건 dedup
   │
   ▼
gold_seoul_ppltn_by_time ─ 시간별 장소 혼잡도 (avg_ppltn 등 파생)
```

| 파일 | 역할 |
|------|------|
| `models/schema.yml` | source(bronze) + 모델/컬럼 문서 + 테스트 선언 |
| `models/silver/silver_seoul_ppltn.sql` | bronze `payload`를 `json_extract_scalar`로 파싱 후 dedup |
| `models/gold/gold_seoul_ppltn_by_time.sql` | silver 소비, 시간별 파생 |
| `tests/assert_silver_not_empty.sql` | silver 비어있지 않음 검증 |
| `profiles.yml` | dev/prod 프로파일 (target으로 카탈로그 분리) |

## bronze가 schema-on-read라 silver가 파싱한다

bronze는 원본 레코드 JSON을 `payload` 컬럼에 통째로 저장합니다(파싱 안 함). 따라서
**개별 필드 분해는 silver의 몫**입니다:

```sql
json_extract_scalar(payload, '$.AREA_NM')          as area_nm,
json_extract_scalar(payload, '$.AREA_CONGEST_LVL') as area_congest_lvl,
try_cast(nullif(trim(json_extract_scalar(payload, '$.AREA_PPLTN_MIN')), '') as integer) as area_ppltn_min,
...
```

이점: API 필드가 바뀌어도 bronze는 안 깨지고(컬럼 고정), **파싱 규칙을 dbt SQL로 버전 관리**하며,
원본 보존으로 재처리(replay)가 가능합니다. (bronze 설계 근거: ASAC-DAG `domains/population/docs/bronze-metadata.md`)

## materialization: 지금은 table (incremental 보류)

silver/gold 모두 `table`(전체 재생성)입니다. 규모가 작아 15분 주기 재생성이 충분히 쌉니다.

- **incremental(merge)** 을 시도했으나, dbt-trino + **R2 Data Catalog의 eventual consistency**로
  첫 run에 `is_incremental()`이 잘못 true로 잡혀(drop된 테이블을 "존재"로 응답 → 자기참조 SQL)
  실패했습니다. 카탈로그 등록 상태가 안정된 뒤 재시도 예정(향후 과제).
- 데이터가 커지면 incremental로 전환해 5분 주기도 싸게 처리할 수 있습니다.

## 멱등성

- **silver/gold**: 매번 전체 재생성 + silver의 `(area_nm, ppltn_time)` dedup → **N번 돌려도 결과 동일(멱등)**.
- bronze에 같은 `ppltn_time`이 5분마다 중복 수집돼도 silver가 최신 1건으로 흡수합니다.

## dev/prod 분리

- `profiles.yml`: dev → `iceberg_dev`(seoul-dev), prod → `iceberg`(seoul).
- `schema.yml`의 source `database: "{{ target.database }}"` → 타깃 카탈로그와 자동 정렬.
- 기본 target은 dev. **prod는 팀 합의 없이 쓰지 않습니다.**

## 실행

```bash
# Airflow 자동: ASAC-DAG seoul_ppltn_transform DAG가 15분마다 dbt run + test

# 수동 (컨테이너 내부, dev):
cd /opt/airflow/dbt/domains/population
export DBT_PROFILES_DIR=$PWD DBT_PROJECT_DIR=$PWD
/home/airflow/dbt-venv/bin/dbt build --target dev
```

## 향후

- **incremental 전환** (카탈로그 안정화 후)
- **공통 축**: 상위 API 설계에 따라 장소=자치구+동, 시간=hourly 매핑을 gold/통합에 반영
- **커스텀 매크로**: 반복되는 `json_extract_scalar` 파싱을 매크로로 묶어 재사용
