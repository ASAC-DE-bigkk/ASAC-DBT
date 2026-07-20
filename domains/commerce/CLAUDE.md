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
