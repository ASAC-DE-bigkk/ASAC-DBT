# citydata 도메인 — dbt (silver / gold)

서울시 **실시간 도시데이터 통합**(`citydata`)의 **bronze → silver → gold** 변환을 담는 dbt
프로젝트입니다. bronze 원본 적재는 ASAC-DAG(`domains/citydata`)가, 여기서는 그 bronze를
읽어 도메인별로 정제·집계합니다. 하나의 citydata 번들에서 **인구·상권·승하차·따릉이·대기질**
마트를 파생하며, 스키마를 분리합니다: 인구는 `seoul_ppltn`, 그 외 citydata 신호는 `seoul_citydata`.

> dbt 프로젝트명은 역사적 이유로 `seoul_ppltn`을 유지합니다(profile 매칭). 폴더/도메인만
> citydata 로 개명 — 출력 스키마·모델은 그대로라 소비자 영향 없음.

## 메달리온 구조

```
bronze_seoul_citydata (source)  ─ ASAC-DAG가 적재. (장소×블록) 행 + 블록 원본 payload JSON
   │  block_name 별로 골라 json_extract 파싱
   ├─ LIVE_PPLTN_STTS  → silver_seoul_ppltn            (인구, seoul_ppltn)
   ├─ LIVE_CMRCL_STTS  → silver_citydata_cmrcl(_rsb)   (상권/업종, seoul_citydata)
   ├─ LIVE_SUB/BUS_PPLTN → silver_citydata_transit_ppltn (승하차, seoul_citydata)
   ├─ SBIKE_STTS       → silver_citydata_sbike          (따릉이, seoul_citydata)
   └─ WEATHER_STTS     → silver_citydata_air            (날씨/대기질, seoul_citydata)
                              │
                              ▼
   gold_seoul_ppltn_by_time / _daily   (인구 시계열·일집계, seoul_ppltn)
   gold_citydata_place_latest          (장소별 크로스 신호 최신 스냅샷, seoul_citydata)
   gold_citydata_cmrcl_daily           (일 소비 인사이트, seoul_citydata)
```

| 파일 | 역할 |
|------|------|
| `models/schema.yml` | source(bronze/bronze_citydata) + seed/모델/컬럼 문서 + 테스트 선언 |
| `models/silver/silver_seoul_ppltn.sql` | citydata bronze의 `LIVE_PPLTN_STTS` 블록을 파싱·dedup (인구) |
| `models/silver/silver_citydata_*.sql` | 상권·업종·승하차·따릉이·대기질 블록별 grain 파싱 |
| `models/gold/gold_seoul_ppltn_by_time.sql`·`_daily.sql` | 인구 시간별/일 파생 |
| `models/gold/gold_citydata_place_latest.sql` | 장소별 혼잡도×소비×승하차×따릉이×대기질 최신 1행 |
| `models/gold/gold_citydata_cmrcl_daily.sql` | 일 소비 인사이트 |
| `models/dim/dim_seoul_area.sql` | 장소 차원(좌표·행정구역) |
| `seeds/seoul_ppltn_area_geo.csv` | ★ 121장소 위치 참조 (중심점/bbox/폴리곤 WKT, WGS84) |
| `macros/generate_schema_name.sql` | custom schema 를 접두사 없이 그대로 사용(seoul_ppltn / seoul_citydata) |
| `profiles.yml` | dev/prod 프로파일 (target으로 카탈로그 분리) |

## 위치 참조 seed: seoul_ppltn_area_geo

서울시 배포 shapefile("서울시 주요 121장소 영역", WGS84)에서 추출한 조인용 참조
테이블입니다. `dbt seed`로 적재되며(transform DAG의 `dbt_seed` 태스크), 모델이
`area_cd`로 left join해 중심점 좌표/분류를 붙입니다. 폴리곤 WKT는 행마다 붙이기엔
무거워 seed에만 두고 필요할 때 직접 join합니다.

- **원본 보존**: shapefile 원본은 R2 `reference/population/area_geo/`에 아카이브.
  중심점 계산 방식(면적 가중 centroid)을 바꾸고 싶으면 원본에서 재추출합니다.
- **갱신 절차**: 서울시가 장소를 바꾸면 CSV 재생성 → PR → 머지 → 다음 run에 반영.
  `area_cd`/`area_nm` unique + not_null 테스트가 seed 품질을 지킵니다.

## bronze가 schema-on-read라 silver가 파싱한다

bronze는 블록 원본 JSON을 `payload` 컬럼에 통째로 저장합니다(파싱 안 함). 따라서
**개별 필드 분해는 silver의 몫**이고, silver는 `block_name`으로 자기 블록을 골라 파싱합니다.
블록 payload가 `[{...}]` 배열인 경우(예: 인구) `$[0].` 로 꺼냅니다:

```sql
json_extract_scalar(payload, '$[0].AREA_NM')          as area_nm,
json_extract_scalar(payload, '$[0].AREA_CONGEST_LVL') as area_congest_lvl,
...
where block_name = 'LIVE_PPLTN_STTS'
```

이점: API 필드가 바뀌어도 bronze는 안 깨지고(컬럼 고정), **파싱 규칙을 dbt SQL로 버전 관리**하며,
원본 보존으로 재처리(replay)가 가능합니다. (bronze 설계 근거: ASAC-DAG `domains/citydata/docs/bronze-metadata.md`)

## materialization: 전 모델 incremental

- **silver**: `incremental` + `merge`. 매 run은 `max(collected_at) - lookback` 이후의 bronze만
  파싱해 merge하므로 bronze가 쌓여도 run 비용이 일정합니다 → 수집(5분)과 같은 5분 주기로 돌립니다.
- **gold**: `incremental`. `gold_citydata_place_latest`는 단일키(area_cd) merge의
  중복-insert 이슈를 피하려 **`delete+insert`** 를 씁니다(매 run 창에 등장한 area_cd 재삽입 →
  유일성 보장). 나머지 gold는 `merge`(복합키). 전체 재생성이 없어 스냅샷/파일 누적이 최소화됩니다.

### ⚠ 첫 run / drop 직후 주의 (R2 Data Catalog eventual consistency)

테이블을 **drop한 직후** run하면 카탈로그가 잠시 "존재"로 응답해 `is_incremental()`이
잘못 true가 되고(자기참조 SQL) 실패할 수 있습니다. 대응:

- 기존 `table`에서 전환할 때는 **drop 없이 그대로** run — 기존 테이블에 merge되므로 안전.
- 새 환경(빈 스키마)의 첫 run은 테이블이 없어 전체 생성 — 정상 동작.
- drop이 꼭 필요했다면(스키마 변경 등) 실패 시 잠시 후 재실행(DAG retry로도 흡수).

## dev/prod 분리

- `profiles.yml`: dev → `iceberg_dev`(seoul-dev), prod → `iceberg`(seoul).
- `schema.yml`의 source `database: "{{ target.database }}"` → 타깃 카탈로그와 자동 정렬.
- 기본 target은 dev. **prod는 팀 합의 없이 쓰지 않습니다.**

## 실행

```bash
# Airflow 자동: ASAC-DAG citydata_transform DAG가 5분마다 dbt run + test

# 수동 (컨테이너 내부, dev):
cd /opt/airflow/dbt/domains/citydata
export DBT_PROFILES_DIR=$PWD DBT_PROJECT_DIR=$PWD
/home/airflow/dbt-venv/bin/dbt build --target dev
```
