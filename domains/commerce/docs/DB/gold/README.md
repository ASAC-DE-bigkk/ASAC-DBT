# DB/gold — gold(서빙 Postgres) 객체 명세 인덱스

gold 레이어 DB 객체(`serving.public.commerce_*`)의 명세. Supertype/Subtype 구조 + code 정규화 dim +
비공통 detail(cluster 8 + single 70) + 조회 뷰. 상위 인덱스: [../README.md](../README.md).

| 문서 | 내용 |
|---|---|
| [tables.md](tables.md) | **테이블 명세** — `commerce_business_entity`(+이력) · dim 3(dataset/region/status) · detail 78(cluster 8+single 70) · marker · 카탈로그 |
| [views.md](views.md) | **뷰 명세** — 조회 인터페이스: 도메인 view 8×2 + API view 152×2(current/history) |
| [cluster-domain-coherence.md](cluster-domain-coherence.md) | **detail cluster 도메인 정합성 검증** — 필드-유사도 병합 8개를 공식 LOCALDATA 코드·소관 법령으로 대조(오병합 0건) |
| [normalization-plan.md](normalization-plan.md) | **정규화(Option 1 적용됨)** — detail payload 저카디널리티 컬럼 72쌍(표본검증 완료) → `commerce_code_value` |
| [partitioning-indexing-plan.md](partitioning-indexing-plan.md) | **인덱싱 적용됨 · 파티셔닝 보류** — view SQL 근거 6개 인덱스 + entity_seq 전환, 라이브 실측(1187ms→18ms) |

> 병합 **알고리즘·경계**(Jaccard≥0.7 ∧ 멤버≥3 ∧ 공유≥8)의 근거는 [../../silver-noncommon-catalogs.md](../../silver-noncommon-catalogs.md),
> 기계용 카탈로그는 [../../gold-catalog.csv](../../gold-catalog.csv).
