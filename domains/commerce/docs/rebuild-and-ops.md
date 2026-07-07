# 적재형태·재빌드 정책 + 단위 재적재/삭제 운영 가이드

silver 의 **적재형태(materialization) 정책**과, **특정 일자·특정 인허가 API(dataset)·특정 run
단위의 재적재/삭제**를 설정 파일 변경만으로 수행하는 절차를 정의한다. (관리 문서 — 운영자는
이 문서만 보면 된다.)

---

## 1. 적재형태 정책 (materialization)

| 항목 | 정책 |
|---|---|
| materialization | 전 모델 `table` — **매 실행 bronze 전체에서 전량 재빌드** ([dbt_project.yml](../dbt_project.yml) `+materialized: table`) |
| 원칙 | **silver/gold 는 bronze 의 순수 함수** — 상태를 갖지 않고, 같은 bronze + 같은 설정이면 항상 같은 결과 |
| 멱등성 | 재실행·재시도 안전. 실패하면 그냥 다시 `dbt run` |
| incremental 미채택 사유 | ① 입력이 변경로그라 소형 ② 암묵 버저닝의 정렬·인접 dedup 은 키별 전체 이력이 필요 ③ R2 Data Catalog 의 incremental 이슈(ASAC-DAG 계획서 §2.2) |
| 재검토 트리거 | 일일 재빌드 소요가 실측으로 문제 될 때(수십 분대) → 변경 키만 재계산하는 key-scoped 증분 검토. bronze 성장의 지배 요인인 **분기 full_reconcile 재유입 정책**을 먼저 결정할 것 |

이 원칙의 귀결: **"재적재"는 layer 마다 의미가 다르다.**

- **silver 재적재** = `dbt run` 한 번(항상 전량). 별도 단위 개념이 없다 — 단위 제어는 아래
  §2(입력 = bronze 쪽)와 §3(제외 = vars)이 담당한다.
- **bronze 재적재** = ASAC-DAG `commerce_load_bronze` 의 몫(워터마크 상태 파일로 단위 제어).

## 2. 단위 재적재 (특정 dataset / 특정 시점 이후) — bronze 상태 파일 수정

bronze 적재 상태는 R2 의 파일로만 관리된다(RDB 없음): `{prefix}/commerce_bronze_state/_watermark.json`
= `{ "<dataset short>": "<마지막 적재 run_id>" }`. **파일 수정 → `commerce_load_bronze` 실행 →
`dbt run`** 순서면 끝난다 (적재는 (dataset, run_id) 단위 delete-then-insert 멱등이라 중복이 생기지 않는다).

| 원하는 것 | `_watermark.json` 수정 | 다음 실행의 동작 |
|---|---|---|
| **특정 dataset 전체 재적재** (예: general_restaurant) | 해당 key **삭제** | 그 dataset 첫 run 부터 전체 재적재(전체 스냅샷=PyIceberg, 이후 증분=Trino) |
| **특정 시점 이후 재적재** (특정 일자 포함) | 해당 key 값을 **그 일자 직전 완료 run_id 로 되돌림** | 그 이후 모든 완료 run 을 순서대로 재적재(멱등 — 기존 행은 run 단위로 교체) |
| **전부 처음부터** | 파일 삭제(+Iceberg 테이블 drop 가능) | 39종 전체 재적재. raw 는 불변이라 항상 가능 |

```bash
# 예: general_restaurant 만 처음부터 재적재 (R2 상태 파일 편집)
# 1) _watermark.json 에서 "general_restaurant" 항목 제거 후 업로드
# 2) 적재 → 변환
docker compose exec airflow-scheduler airflow dags trigger commerce_load_bronze
docker compose exec airflow-scheduler airflow dags trigger commerce_localdata_transform
```

- run_id 목록은 raw 폴더(`{prefix}/raw/commerce/YYYY/MM/DD/run_id=*`) 또는
  receipt(`{prefix}/commerce_bronze_state/receipts/<date>/`)에서 확인한다.
- silver 는 전량 재빌드라 **bronze 가 바뀌면 자동 반영** — silver 쪽 추가 조치 없음.

## 3. 단위 삭제 (특정 dataset / 일자 / run 을 silver 에서 제외) — dbt vars 수정

[dbt_project.yml](../dbt_project.yml) 의 `vars` 목록에 넣고 `dbt run` 하면 전량 재빌드에서
해당 단위가 빠진다. **복원 = 목록에서 제거 후 다시 `dbt run`** — bronze 는 불변이므로
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
# 영구 반영: dbt_project.yml vars 수정 → 커밋 → dbt run
# 일회성 확인(파일 수정 없이): --vars 오버라이드
dbt run  --select silver_license_history silver_license_current \
  --vars '{exclude_bronze_run_ids: ["2026-07-01_040000_123"]}'
dbt test --select silver_license_history silver_license_current
```

> 발행 게이트와의 구분: manifest(`is_publishable`) 게이트는 **적재가 불완전한 run 을 자동
> 차단**하는 장치, `exclude_*` vars 는 **정상 발행됐지만 사후에 빼기로 결정한 단위**를 수동
> 제외하는 장치다. 역할이 다르므로 둘 다 유지한다.

## 4. 오케스트레이션

`commerce_localdata_transform` DAG(ASAC-DAG 번들, 05:00 KST — bronze 적재 04:00 이후):
`dbt run --select silver_*` → `dbt test --select silver_*`. DAG 는 상태가 없으므로(§1)
수동 재실행이 언제나 안전하다. gold 는 Step 9 구현 시 태스크 2개가 뒤에 추가된다.

## 5. 운영 노트

- **Iceberg 스냅샷 누적**: 전량 재빌드는 실행마다 새 스냅샷을 만든다. R2 Data Catalog 의
  스냅샷 만료/컴팩션 적용 여부를 확인하고, 미적용이면 분기 운영 캘린더(full_reconcile)에
  `expire_snapshots` 성 유지보수를 함께 등록할 것.
- **vars 변경은 커밋으로 남긴다**: 제외 목록이 곧 "현재 silver 의 정의"다. 일회성 `--vars` 는
  확인용으로만 쓰고, 유지할 결정은 dbt_project.yml 에 반영해 이력을 남긴다.
- **검증 루틴**: 어떤 단위 조작 후에도 `dbt test` 4종(행 유니크·발행 게이트·인접 중복)이
  통과해야 한다. 실패 시 `target/compiled/.../*.sql` 을 Trino 로 직접 실행해 위반 행을 본다.
- 타임존·결측 규약: [timestamps-and-nulls.md](timestamps-and-nulls.md) ·
  컬럼 구조: [dataset-columns.md](dataset-columns.md)
