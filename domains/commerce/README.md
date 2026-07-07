# dbt/domains/commerce — 서울 인허가(상권) silver/gold

ASAC-DBT 의 commerce 도메인 프로젝트. Trino + Iceberg(Cloudflare R2 Data Catalog) 위에서
bronze(원본층) → silver(정제·변경이력) → gold(집계)를 만든다. **자립형** — 타 도메인 프로젝트에
의존하지 않는다(공유하는 것은 Trino 접속 env 계약뿐).

전체 설계·단계별 계획: ASAC-DAG `dags/domains/commerce/docs/pipeline/medallion-implementation-plan.md`.

> **dbt 가 처음이라면 → [docs/beginner-guide.md](docs/beginner-guide.md)** (확인·실행·디버깅 실전 가이드).
> 컬럼 구조(39종 공통/개별): [docs/dataset-columns.md](docs/dataset-columns.md) ·
> 타임존/결측 규약: [docs/timestamps-and-nulls.md](docs/timestamps-and-nulls.md) ·
> 주소·구/동 코드·좌표 변환 규약: [docs/address-and-geo.md](docs/address-and-geo.md) ·
> **적재형태·재빌드 정책 + 단위 재적재/삭제 운영: [docs/rebuild-and-ops.md](docs/rebuild-and-ops.md)**

## 레이어

- **bronze**(입력, 이 프로젝트가 만들지 않음): `<catalog>.<COMMERCE_SCHEMA>.bronze_localdata_license`
  (ASAC-DAG 의 `commerce_load_bronze` DAG 가 raw 증분을 적재 — 전체=PyIceberg / 증분=Trino) +
  `bronze_collection_run_manifest`(발행 게이트). sources: [models/sources.yml](models/sources.yml).
- **silver**
  - `silver_license_history` — 정제된 변경 이력. publishable run 필터 → 파싱/파생(자치구·주소 키) →
    **연속 중복 제거**(A→B→A 원복 보존). **명시적 버전 컬럼 없음** — (dataset, opnsfteamcode, mgtno) 안에서
    `updatedt_sort, lastmodts_sort, observed_date, collected_at, content_hash` **내림차순 정렬이
    곧 버전 순서**(암묵 버저닝). 행 식별 그레인 (dataset, opnsfteamcode, mgtno, collected_at, content_hash).
  - `silver_license_current` — 업소당 최신 1행(위 정렬의 최상위, row_number=1).
    grain (dataset, opnsfteamcode, mgtno) — MGTNO 는 발급 자치단체 안에서만 유니크.
- **gold** — 후속(Step 9). 현재 미구현. 이력 기반 상태 갱신 시 history 의 암묵 버저닝
  정렬을 그대로 사용한다.

## 버전(같은 key·다른 value) 처리

인허가는 매일 전량 수집되지만 raw 는 변경분만 저장(diff). bronze 는 변경로그이고, silver 가
`content_hash`(키 정렬 canonical JSON sha256) 기준으로 변경을 판정한다. 전역 dedup 이 아니라
**연속(인접) 중복만** 제거하므로 정당한 원복은 이력에 보존된다. `version_seq`/`valid_from`/
`valid_to`/`is_current` 같은 명시 버전 컬럼은 두지 않는다 — 버전 순서가 필요한 소비처는
`order by updatedt_sort desc, lastmodts_sort desc, observed_date desc, collected_at desc,
content_hash desc` 로 재현한다(current 가 그 예).

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
`COMMERCE_SCHEMA`(기본 commerce). 오케스트레이션: ASAC-DAG 의 `commerce_load_silver`
DAG(05:00 KST, run silver → test silver). 적재형태(marker 증분 + full-refresh 백필)·특정 dataset/일자/run 단위
재적재·삭제 절차: [docs/rebuild-and-ops.md](docs/rebuild-and-ops.md) — 단위 삭제는
`dbt_project.yml` 의 `vars`(`exclude_datasets`/`exclude_observed_dates`/`exclude_load_dates`/
`exclude_bronze_run_ids`) 수정만으로 동작한다.

## 테스트

- 행 유니크: history (dataset, opnsfteamcode, mgtno, collected_at, content_hash) · current (dataset, opnsfteamcode, mgtno)
- `assert_silver_commerce_uses_publishable_runs` — 미발행 run 유입 0
- `assert_silver_license_history_no_adjacent_duplicates` — 연속 중복 제거 불변식
  (암묵 버전 정렬 기준 인접 동일 hash 0건, A→B→A 보존)
