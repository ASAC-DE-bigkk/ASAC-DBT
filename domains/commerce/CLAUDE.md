# CLAUDE.md — dbt/domains/commerce (에이전트 작업 규약)

이 파일은 **commerce dbt 번들**(`dbt/domains/commerce/`)에서 작업할 때의 규약이다.
레이어·모델·실행 등 **상세 규약의 정본은 [README.md](README.md)** 이며, 이 파일은 그 위에
전역 규칙만 얹는다. commerce 도메인 전체(수집·오케스트레이션 포함)의 상위 규약은
ASAC-DAG `dags/domains/commerce/CLAUDE.md` 를 따른다.

## 언어 규정 (Language convention)

- **사람이 읽는 산출물은 한글로 작성한다.** 사용자에게 출력하는 대화 응답, 이슈·PR 본문,
  `docs/` 문서, 리포트, 커밋 메시지 등 "읽는 사람"이 있는 결과물은 기본 **한글**.
- **백그라운드 작업은 영어로 진행해도 된다.** SQL/dbt 모델 코드, 매크로, 식별자·컬럼명,
  내부 로그, 임시 파일 등 사람이 직접 읽는 최종 산출물이 아닌 것은 **영어** 허용.
- 판단 기준: "사람이 읽으라고 만든 것인가?" → 예: **한글**. 기계·내부용인가? → **영어** 무방.

## 작업 경계

- commerce 도메인의 dbt 변경은 이 번들(`dbt/domains/commerce/`) 안에서만 수행한다.
- **타 도메인 dbt 폴더**(`traffic_weather`, `culture`, `transit`, `citydata`)는 **읽기만 하고
  수정하지 않는다.** 교차 도메인 참조는 gold 레이어의 published source 계약으로만 이뤄진다
  (예: weather 가 `commerce_gold.gold_license_dong_summary` 를 source 로 소비).

## D1 서빙 계약 (commerce 자체 관리)

commerce gold → 공유 Cloudflare **D1(SQLite)** 서빙은 **commerce 안에서 자체 규약으로 관리**한다.
타 도메인 방식을 따라갈 필요 없다.

- **정본 규약**: gold 모델 `config.meta.serving.serving_tier`(`d1_direct`/`d1_rollup`/`iceberg_api`)
  + `d1_table` · `publication_mode`(`iceberg`/`rollup`) · `product_id`(`gold_*`) · `product_question`.
  선언·소비의 정본은 export `SERVING_SPEC` 과 대조된다.
- **구현(진행 중, 미구현 아님)**:
  - 계약(dbt): **ASAC-DBT #334 → PR #335**(`serving_tier` 재정리).
  - export(dags): **ASAC-DAG #493 → PR #494** `commerce_serving_export`(gold Asset 트리거 분리 DAG,
    `include/gold/serving_export.py`). direct 15 = `SELECT *` 스냅샷, rollup = export 시 GROUP BY 파생,
    iceberg_api = D1 금지·Trino 직조회. 기존 serving Postgres 경로는 폐기(2026-07-14).
- **설계 정본**: [docs/DB/gold/serving-design.md](docs/DB/gold/serving-design.md)(tier 분류·화면 매핑·서빙 계약).
- **org 공통 계약(#478)과의 관계**: ASAC-DAG #478 `meta.serving.enabled/…` 는 별개의 org 공통 계약이다.
  commerce 는 자체 `serving_tier` 규약을 쓰며 org 계약에 강제 종속되지 않는다. 추적(참고): dags 번들
  [`docs/serving-contract-chain.md`](../../../dags/domains/commerce/docs/serving-contract-chain.md).
  **주의(향후 확인)**: ASAC-DBT `serving-contract-gate` CI 는 `config.meta.serving` 이 있는 **모든** 모델을
  #478 규격으로 검사하므로, commerce 의 `serving_tier` 블록이 그 게이트에 걸릴 수 있다 — 이 정합은
  commerce 자체 PR(#335 계열)에서 결정한다(게이트 예외/네임스페이스 분리/수렴 중 택1). 타 도메인 무접촉.
