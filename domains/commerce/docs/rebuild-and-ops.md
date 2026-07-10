# 적재형태·증분/백필 정책 + 단위 재적재/삭제 운영 가이드

silver 의 **적재형태(materialization) 정책**과, **특정 일자·특정 인허가 API(dataset)·특정 run
단위의 증분/백필/삭제**를 수행하는 절차를 정의한다. (관리 문서 — 운영자는
이 문서만 보면 된다.)

---

## 1. 적재형태 정책 (materialization)

| 항목 | 정책 |
|---|---|
| `silver_license_history` | `incremental` + `append`. 첫 실행/`--full-refresh` 는 publishable bronze 전체를 백필하고, 이후 실행은 이 테이블에 아직 없는 `bronze_run_id` 만 읽는다. |
| `silver_license_current` | `table`. history 를 기준으로 현재 1행을 재계산한다. bronze 전체를 다시 파싱하지 않는다. |
| 증분 marker | `silver_load_run_marker` 의 `(dataset, bronze_run_id, status='DONE')` — dbt test 통과 후 Airflow 가 기록한다. |
| marker 없음 | marker table/target table 이 없거나 `--full-refresh` 를 주면 `is_incremental()` 이 false → 해당 경로의 publishable bronze 전체 백필. |
| 멱등성 | DONE marker 가 없는 후보 run 은 pre-hook 으로 history 에서 선삭제 후 재삽입한다. dbt test 통과 전에는 DONE 이 찍히지 않아 재시도 가능하다. |
| 리소스 정책 | Airflow 태스크는 직렬, dbt profile `threads: 1`. full-refresh/backfill 도 Trino/Iceberg 쿼리로 처리하고 Airflow/Python 에 전체 데이터를 올리지 않는다. |

이 원칙의 귀결: **"재적재"는 layer 마다 의미가 다르다.**

- **silver 증분 반영** = `dbt run` 한 번. `silver_load_run_marker` 에 DONE 이 있는 run 은 건너뛰고 신규 run 만 처리한다.
- **silver 전체 백필** = `dbt run --full-refresh --select silver_license_history+`. 기존 marker/table 을
  버리고 publishable bronze 전체로 다시 만든다.
- **bronze 재적재** = ASAC-DAG `commerce_load_bronze` 의 몫(워터마크 상태 파일로 단위 제어).

공식 문서 근거:
- dbt incremental 모델은 첫 실행에 전체를 만들고 이후 `is_incremental()` 조건으로 필터링한 행만
  처리한다: https://docs.getdbt.com/docs/build/incremental-models
- dbt-trino 의 기본 incremental strategy 는 `append` 이며, `delete+insert`/`merge` 는 connector
  지원과 unique key 조건을 탄다: https://docs.getdbt.com/reference/resource-configs/trino-configs
- dbt `threads: 1` 은 한 번에 한 모델 경로만 실행해 warehouse 부하를 낮춘다:
  https://docs.getdbt.com/docs/running-a-dbt-project/using-threads

## 2. 단위 재적재 (특정 dataset / 특정 시점 이후) — bronze 상태 파일 수정

bronze 적재 상태는 R2 의 파일로만 관리된다(RDB 없음): `{prefix}/commerce_bronze_state/_watermark.json`
= `{ "<dataset short>": "<마지막 적재 run_id>" }`. **파일 수정 → `commerce_load_bronze` 실행 →
`dbt run`** 순서면 끝난다. bronze 적재는 (dataset, run_id) 단위 delete-then-insert 멱등이고,
silver 는 아직 반영되지 않은 `bronze_run_id` 만 추가한다.

| 원하는 것 | `_watermark.json` 수정 | 다음 실행의 동작 |
|---|---|---|
| **특정 dataset 전체 재적재** (예: general_restaurant) | 해당 key **삭제** | 그 dataset 첫 run 부터 전체 재적재(전체 스냅샷=PyIceberg, 이후 증분=Trino) |
| **특정 시점 이후 재적재** (특정 일자 포함) | 해당 key 값을 **그 일자 직전 완료 run_id 로 되돌림** | 그 이후 모든 완료 run 을 순서대로 재적재(멱등 — 기존 행은 run 단위로 교체) |
| **전부 처음부터** | 파일 삭제(+Iceberg 테이블 drop 가능) | 152종 전체 재적재. raw 는 불변이라 항상 가능 |

```bash
# 예: general_restaurant 만 처음부터 재적재 (R2 상태 파일 편집)
# 1) _watermark.json 에서 "general_restaurant" 항목 제거 후 업로드
# 2) 적재 → 변환
docker compose exec airflow-scheduler airflow dags trigger commerce_load_bronze
docker compose exec airflow-scheduler airflow dags trigger commerce_load_silver
```

- run_id 목록은 raw 폴더(`{prefix}/raw/commerce/YYYY/MM/DD/run_id=*`) 또는
  receipt(`{prefix}/commerce_bronze_state/receipts/<date>/`)에서 확인한다.
- silver history 가 이미 동일 `bronze_run_id` 를 반영한 상태에서 bronze 내용을 강제로 교체했다면
  DONE marker 가 있으면 다시 읽지 않는다. 이 경우 `dbt run --full-refresh --select silver_license_history+`
  로 해당 환경의 silver marker 를 재생성한다.

## 3. 단위 삭제 (특정 dataset / 일자 / run 을 silver 에서 제외) — dbt vars 수정

[dbt_project.yml](../dbt_project.yml) 의 `vars` 목록에 넣고 `dbt run --full-refresh --select
silver_license_history+` 하면 백필 입력에서 해당 단위가 빠진다. **복원 = 목록에서 제거 후 다시
full-refresh** — bronze 는 불변이므로
삭제는 "silver 노출 제외"이고 원본·감사 이력은 항상 bronze 에 남는다.

| var | 단위 | 예 |
|---|---|---|
| `exclude_datasets` | 인허가 API(dataset) | `["general_restaurant"]` |
| `exclude_observed_dates` | 논리 수집일(KST) | `["2026-07-01"]` |
| `exclude_load_dates` | 적재일(KST) | `["2026-07-02"]` |
| `exclude_bronze_run_ids` | 수집 run(가장 정밀) | `["2026-07-01_040000_123"]` |

적용 지점: [models/silver/silver_license_history.sql](../models/silver/silver_license_history.sql)
bronze CTE 의 `where` 절(매크로 [macros/exclusions.sql](../macros/exclusions.sql)).
current·(후속) gold 는 history 를 참조하므로 자동 전파된다.

```bash
# 영구 반영: dbt_project.yml vars 수정 → 커밋 → full-refresh 백필
# 일회성 확인(파일 수정 없이): --vars 오버라이드
dbt run --full-refresh --select silver_license_history+ \
  --vars '{exclude_bronze_run_ids: ["2026-07-01_040000_123"]}'
dbt test --select silver_license_history silver_license_current
```

> 발행 게이트와의 구분: manifest(`is_publishable`) 게이트는 **적재가 불완전한 run 을 자동
> 차단**하는 장치, `exclude_*` vars 는 **정상 발행됐지만 사후에 빼기로 결정한 단위**를 수동
> 제외하는 장치다. 역할이 다르므로 둘 다 유지한다.

## 4. 오케스트레이션

`commerce_load_silver` DAG(ASAC-DAG 번들, 05:00 KST — bronze 적재 04:00 이후):
`ensure_silver_marker` → `dbt run --select silver_*` → `dbt test --select silver_*` →
`mark_silver_done`. DAG 는 DONE marker 가 없는 신규 `bronze_run_id` 만 처리한다.
gold 는 Step 9 구현 시 태스크 2개가 뒤에 추가된다.

## 5. 운영 노트

- **Iceberg 스냅샷 누적**: incremental append 와 full-refresh 모두 스냅샷을 만든다. R2 Data Catalog 의
  스냅샷 만료/컴팩션 적용 여부를 확인하고, 미적용이면 분기 운영 캘린더에 유지보수를 등록할 것.
- **vars 변경은 커밋으로 남긴다**: 제외 목록이 곧 "현재 silver 의 정의"다. 일회성 `--vars` 는
  확인용으로만 쓰고, 유지할 결정은 dbt_project.yml 에 반영해 이력을 남긴다.
- **검증 루틴**: 어떤 단위 조작 후에도 `dbt test` 4종(행 유니크·발행 게이트·인접 중복)이
  통과해야 한다. 실패 시 `target/compiled/.../*.sql` 을 Trino 로 직접 실행해 위반 행을 본다.
- 타임존·결측 규약: [timestamps-and-nulls.md](timestamps-and-nulls.md) ·
  컬럼 구조: [dataset-columns.md](dataset-columns.md)

## 6. 청크(부분) 백필 — 대용량 전체 재빌드 시 OOM 회피

**평상시 증분은 소량**(당일 변경분)이라 문제없다. 하지만 **전체 재빌드**(테이블 drop 후 최초 빌드,
또는 `--full-refresh`)는 `silver_license_history` 의 window 연산(dedup `lag`/정렬)이 **전 행을 한 번에**
메모리에 올려 Trino 노드 한도(`query.max-memory-per-node`, 기본 heap 30%)를 초과할 수 있다
(실측: 152종 290만행 전체 재빌드 → `EXCEEDED_LOCAL_MEMORY_LIMIT`).

→ **`include_datasets` 화이트리스트**로 dataset 배치를 나눠 순차 적재한다(각 배치=별도 dataset 이라
서로 격리 — insert·`delete_unmarked` pre-hook 모두 배치 범위만 처리해 이전 배치를 건드리지 않는다).
가장 큰 단일 dataset 이 한 배치에 들어갈 정도면 절대 OOM 나지 않는다.

```bash
# 전체 백필을 행수 기준 배치로(예: 큰 것 분리). 배치마다 history+current 함께.
dbt run --select silver_license_history silver_license_current \
  --vars '{include_datasets: ["mail_order_sale"]}'
dbt run --select silver_license_history silver_license_current \
  --vars '{include_datasets: ["general_restaurant","instant_sale_mfg","rest_restaurant"]}'
# … 나머지 배치. 배치 크기는 노드 메모리에 맞춰 조정(한 배치 총행수 ≲ 100만 권장).
dbt test --select silver_license_history silver_license_current
```

- `include_datasets` 는 **`exclude_datasets` 와 반대**(화이트리스트). 비우면 필터 없음(평상시 동작 불변).
- current 도 같은 배치의 grain 만 재계산(collected_at 순서 무관 — 백필이 시간순 밖으로 들어와도 누락 없음).
- 배치 간 **마킹 불필요**(dataset 격리). 백필 완료 후 일상 운영은 marker 증분으로 자동 이어진다.
- 대안(인프라): Trino `query.max-memory-per-node` 상향 또는 `spill-enabled=true`. 단 배치가 무설정으로 안전.
