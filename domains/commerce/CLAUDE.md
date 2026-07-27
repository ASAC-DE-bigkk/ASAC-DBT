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

## 공용 D1 Serving Contract (추적 — 지금은 대상 아님)

공용 Cloudflare **D1** 서빙용 도메인 공통 계약(ASAC-DAG #478)이 있다. dbt 쪽 몫은 모델
`config.meta.serving.*` 선언 + ASAC-DBT `serving_contract/` **Validator/CI Gate** 통과다.
단, **commerce D1 export 는 미구현**(gold 는 Iceberg 카탈로그에만 존재 — [serving-design.md](docs/DB/gold/serving-design.md) §5-⑤)
이고, CI 게이트(`serving-contract-gate`)는 **`meta.serving` 선언 모델만 검증**하므로 선언이 없는 지금
commerce yml PR 은 **0 models = PASS**(강제되지 않음). 즉 지금 고칠 D1 서빙 코드도, merge 를 막는
포맷 위반도 없다. commerce 는 자체 tier 스킴(iceberg_api/d1_rollup/d1_direct)을 갖고 있어 **D1 export
를 짓는 시점에** 이 계약(`meta.serving.*`)으로 수렴해야 한다.

- **필드 매핑 정본(각 gold 모델의 계약 필드값·근거·적용 절차)**: [docs/DB/gold/serving-contract-mapping.md](docs/DB/gold/serving-contract-mapping.md)
  — 22 gold 중 지금 선언 대상은 d1_direct 15개, product_id·grain·primary_key·publication_mode 등 값 확정.
- 추적(정본으로 가는 길): dags 번들 [`docs/serving-contract-chain.md`](../../../dags/domains/commerce/docs/serving-contract-chain.md)
  (상위 규약 `dags/domains/commerce/CLAUDE.md` §19.2). 타 도메인 dbt 폴더는 여전히 무접촉.
