# docs — commerce dbt (silver/gold 변환) 문서 인덱스

`dbt/domains/commerce/`(silver 정규화 + gold 카탈로그/서빙)의 모든 문서 인덱스. **용도별**로 묶고,
하위 폴더는 자체 README 로 다시 인덱싱한다. 파이프라인 전체(레이어 계보·수집)는 dags 번들 문서
(`dags/domains/commerce/docs/`)에, 이 폴더는 **dbt 변환·DB 산출물**에 집중한다.

## 설계·근거 (왜 이렇게 만들었나)

| 문서 | 내용 |
|---|---|
| [silver-noncommon-catalogs.md](silver-noncommon-catalogs.md) | **핵심 설계 근거** — API 단위 152종 실측 → 공통(silver)/비공통(gold 카탈로그) 분리, 이력·marker, cluster/single 경계 |
| [dataset-columns.md](dataset-columns.md) | 데이터셋 컬럼 구조 — 공통 영역 vs 분야별(개별) 영역과 dbt 처리(#80) |

## 규약 (변환 규칙)

| 문서 | 내용 |
|---|---|
| [address-and-geo.md](address-and-geo.md) | 주소·행정구역(행정동/법정동)·좌표 보강 규약 |
| [timestamps-and-nulls.md](timestamps-and-nulls.md) | 타임스탬프 타임존 · 결측치 처리 규약 |

## 운영·학습

| 문서 | 내용 |
|---|---|
| [rebuild-and-ops.md](rebuild-and-ops.md) | 적재형태·증분/백필 정책 + 단위 재적재/삭제 + §6 청크 백필(대용량 OOM 회피) |
| [beginner-guide.md](beginner-guide.md) | dbt 초보자 가이드 — 모델 읽기·compile·Trino 조회법 |

## DB 명세 (테이블/뷰 — 레이어별 하위 폴더)

| 폴더 | 내용 |
|---|---|
| [DB/](DB/README.md) | **테이블·뷰 전체 명세**(ERD·키 규약) → [silver/](DB/silver/README.md) · [gold/](DB/gold/README.md) |

## 기계용 산출물 (실측·카탈로그 데이터)

| 파일 | 내용 |
|---|---|
| [api-field-inventory.csv](api-field-inventory.csv) | 152종 API 응답 필드 전수 실측 인벤토리(152행) |
| [api-field-clusters.json](api-field-clusters.json) | 비공통 필드 Jaccard 클러스터 산출물 |
| [gold-catalog.csv](gold-catalog.csv) | gold 카탈로그 스냅샷(103행 — object/kind/members/payload) |
