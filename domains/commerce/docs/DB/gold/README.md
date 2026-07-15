# DB/gold — gold 객체 명세 인덱스

> **2026-07-14 서빙 레이어 개편**(dags docs/PROJECT.md §4): gold 는 **Iceberg**
> (`iceberg[_dev].commerce.*` — 코어 dbt 3모델 + 카탈로그 구동 detail 78)로 이전, 서빙 Postgres 폐기.
> 아래 tables/views/normalization/partitioning 문서는 **구 Postgres 구조 기준**(구조 개념·detail
> 명세는 여전히 유효 — entity_seq/뷰/인덱스 등 Postgres 전용 요소만 폐기됨). 상위: [../README.md](../README.md).

| 문서 | 내용 |
|---|---|
| [status-aggregation-queries.md](status-aggregation-queries.md) | **상태·기간 집계 쿼리(정본, Iceberg — 실행 검증)** — 개업/폐업 연·월 × 업종 3단·업태, 상태군별(휴업/취소 detail 일자), 당해/당월/이번주/오늘, D1(SQLite) 집계 관리 방안 |
| [tables.md](tables.md) | 테이블 명세(구 Postgres 기준) — entity(+이력) · dim 3 · detail 78(cluster 8+single 70) · 카탈로그 |
| [views.md](views.md) | 뷰 명세(구 Postgres 기준 — Iceberg 미승계, detail 직접 조회로 대체) |
| [cluster-domain-coherence.md](cluster-domain-coherence.md) | **detail cluster 도메인 정합성 검증** — 필드-유사도 병합 8개를 공식 LOCALDATA 코드·소관 법령으로 대조(오병합 0건) |
| [normalization-plan.md](normalization-plan.md) | 정규화(구 Postgres 기준) — detail payload 저카디널리티 72쌍 → code_value(Iceberg 포팅 후보) |
| [partitioning-indexing-plan.md](partitioning-indexing-plan.md) | 인덱싱/파티셔닝(구 Postgres 기준 — Iceberg 에선 비적용) |

> 병합 **알고리즘·경계**(Jaccard≥0.7 ∧ 멤버≥3 ∧ 공유≥8)의 근거는 [../../silver-noncommon-catalogs.md](../../silver-noncommon-catalogs.md),
> 기계용 카탈로그는 [../../gold-catalog.csv](../../gold-catalog.csv).
