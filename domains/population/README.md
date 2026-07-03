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
| `models/schema.yml` | source(bronze) + seed/모델/컬럼 문서 + 테스트 선언 |
| `models/silver/silver_seoul_ppltn.sql` | bronze `payload`를 `json_extract_scalar`로 파싱 후 dedup (incremental merge) |
| `models/gold/gold_seoul_ppltn_by_time.sql` | silver 소비, 시간별 파생 + 위치 seed 조인 |
| `seeds/seoul_ppltn_area_geo.csv` | ★ 121장소 위치 참조 (중심점/bbox/폴리곤 WKT, WGS84) |
| `tests/assert_silver_not_empty.sql` | silver 비어있지 않음 검증 |
| `profiles.yml` | dev/prod 프로파일 (target으로 카탈로그 분리) |

## 위치 참조 seed: seoul_ppltn_area_geo

서울시 배포 shapefile("서울시 주요 121장소 영역", WGS84)에서 추출한 조인용 참조
테이블입니다. `dbt seed`로 적재되며(transform DAG의 `dbt_seed` 태스크), gold가
`area_cd`로 left join해 중심점 좌표/분류를 붙입니다. 폴리곤 WKT는 행마다 붙이기엔
무거워 seed에만 두고 필요할 때 직접 join합니다.

- **원본 보존**: shapefile 원본은 R2 `reference/population/area_geo/`에 아카이브.
  중심점 계산 방식(면적 가중 centroid)을 바꾸고 싶으면 원본에서 재추출합니다.
- **갱신 절차**: 서울시가 장소를 바꾸면 CSV 재생성 → PR → 머지 → 다음 run에 반영.
  `area_cd`/`area_nm` unique + not_null 테스트가 seed 품질을 지킵니다.

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

## materialization: silver·gold 둘 다 incremental(merge)

- **silver**: `incremental` + `merge`, unique_key `(area_nm, ppltn_time)`. 매 run은
  `max(collected_at) - 30분`(지연 도착 lookback) 이후의 bronze만 파싱해 merge하므로
  bronze가 쌓여도 run 비용이 일정합니다 → 수집(5분)과 같은 5분 주기로 돌립니다.
- **gold**: `incremental` + `merge`, unique_key `(ppltn_time, area_cd)`. silver의 최근
  수집분만(30분 lookback) merge합니다. 5분마다 **전체 재생성하지 않으므로** 스냅샷/
  데이터파일 누적이 최소화되고, 실시간 지도(최신 슬라이스)와 시간별 분석(누적 히스토리)을
  한 테이블로 동시에 만족합니다. (같은 `(ppltn_time, area_cd)`는 2건 이상 나오지 않음)

### ⚠ 첫 run / drop 직후 주의 (R2 Data Catalog eventual consistency)

테이블을 **drop한 직후** run하면 카탈로그가 잠시 "존재"로 응답해 `is_incremental()`이
잘못 true가 되고(자기참조 SQL) 실패할 수 있습니다. 대응:

- 기존 `table`에서 전환할 때는 **drop 없이 그대로** run — 기존 테이블에 merge되므로 안전.
- 새 환경(빈 스키마)의 첫 run은 테이블이 없어 전체 생성 — 정상 동작.
- drop이 꼭 필요했다면(스키마 변경 등) 실패 시 잠시 후 재실행(DAG retry로도 흡수).

## 멱등성

- **silver**: merge 키 `(area_nm, ppltn_time)` + 배치 내 `collected_at` 최신 1건 dedup →
  같은 구간을 N번 돌려도 결과 동일(멱등). lookback으로 이미 반영된 행을 다시 읽어도
  같은 키를 같은 값으로 갱신할 뿐입니다.
- **gold**: 매번 전체 재생성(멱등).
- bronze에 같은 `ppltn_time`이 5분마다 중복 수집돼도 silver가 최신 1건으로 흡수합니다.

## dev/prod 분리

- `profiles.yml`: dev → `iceberg_dev`(seoul-dev), prod → `iceberg`(seoul).
- `schema.yml`의 source `database: "{{ target.database }}"` → 타깃 카탈로그와 자동 정렬.
- 기본 target은 dev. **prod는 팀 합의 없이 쓰지 않습니다.**

## 실행

```bash
# Airflow 자동: ASAC-DAG population_transform DAG가 5분마다 dbt run + test

# 수동 (컨테이너 내부, dev):
cd /opt/airflow/dbt/domains/population
export DBT_PROFILES_DIR=$PWD DBT_PROJECT_DIR=$PWD
/home/airflow/dbt-venv/bin/dbt build --target dev
```

## 향후

- **공통 축**: 상위 API 설계에 따라 장소=자치구+동, 시간=hourly 매핑을 gold/통합에 반영
- **커스텀 매크로**: 반복되는 `json_extract_scalar` 파싱을 매크로로 묶어 재사용
