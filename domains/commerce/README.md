# dbt/domains/commerce — 서울 인허가(상권) silver/gold

ASAC-DBT 의 commerce 도메인 프로젝트. Trino + Iceberg(Cloudflare R2 Data Catalog) 위에서
bronze(원본층) → silver(정제·SCD2) → gold(집계)를 만든다. **자립형** — 타 도메인 프로젝트에
의존하지 않는다(공유하는 것은 Trino 접속 env 계약뿐).

전체 설계·단계별 계획: ASAC-DAG `dags/domains/commerce/docs/pipeline/medallion-implementation-plan.md`.

## 레이어

- **bronze**(입력, 이 프로젝트가 만들지 않음): `<catalog>.<COMMERCE_SCHEMA>.bronze_localdata_license`
  (ASAC-DAG 의 `commerce_load_bronze` DAG 가 raw 증분을 적재 — 전체=PyIceberg / 증분=Trino) +
  `bronze_collection_run_manifest`(발행 게이트). sources: [models/sources.yml](models/sources.yml).
- **silver**
  - `silver_license_history` — SCD2 이력. publishable run 필터 → 파싱/파생(자치구·주소 키) →
    **연속 중복 제거**(A→B→A 원복 보존) → `valid_from/valid_to/is_current`.
    grain (dataset, mgtno, version_seq).
  - `silver_license_current` — 업소당 최신 1버전(`is_current`). grain (dataset, mgtno).
- **gold** — 후속(Step 9). 현재 미구현.

## 버전(같은 key·다른 value) 처리

인허가는 매일 전량 수집되지만 raw 는 변경분만 저장(diff). bronze 는 변경로그이고, silver 가
`content_hash`(키 정렬 canonical JSON sha256) 기준으로 버전을 판정한다. 전역 dedup 이 아니라
**연속(인접) 중복만** 제거하므로 정당한 원복은 이력에 보존된다.

## 좌표 보정(Step 8, 후속)

silver 에 `district`·`address_key_road`·`address_key_jibun` 파생 컬럼을 이미 둔다. Step 8 에서
`bronze_geocode_address`(주소→위경도 지오코딩 결과)를 `silver_license_current` 에 LEFT JOIN 해
`lon/lat_corrected`·`location_source` 를 추가한다. 원천 `X`,`Y`(TM, 미보정)는 그대로 보존.

## 실행

```bash
export DBT_TARGET=dev            # dev=iceberg_dev(seoul-dev) / prod=iceberg
export DBT_PROFILES_DIR=$(pwd)
dbt deps        # (필요 시)
dbt run  --select silver_license_history silver_license_current
dbt test --select silver_license_history silver_license_current
```

접속 env: `TRINO_HOST/PORT/USER/HTTP_SCHEME`, `TRINO_DEV_ICEBERG_CATALOG|TRINO_ICEBERG_CATALOG`,
`COMMERCE_SCHEMA`(기본 commerce). 오케스트레이션은 후속 `commerce_localdata_transform` DAG.

## 테스트

- grain unique: history (dataset, mgtno, version_seq) · current (dataset, mgtno)
- `assert_silver_commerce_uses_publishable_runs` — 미발행 run 유입 0
- `assert_silver_license_history_no_adjacent_duplicates` — 연속 중복 제거 불변식(A→B→A 보존)
