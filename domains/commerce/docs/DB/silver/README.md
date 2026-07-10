# DB/silver — silver(Iceberg 정규화) 객체 명세 인덱스

silver 레이어 DB 객체(`iceberg_dev.commerce.silver_*`)의 명세. v1/v2 통합 공통 카탈로그 +
비공통 `record_json` 보존 + 증분/재개 marker. 상위 인덱스: [../README.md](../README.md).

| 문서 | 내용 |
|---|---|
| [tables.md](tables.md) | **테이블 명세** — `silver_license_history`(append-only 전 버전) · `silver_license_current`(최신 1행) · 보강 참조 · `silver_load_run_marker` |

> 공통/비공통 분리 설계와 이력 보존 근거: [../../silver-noncommon-catalogs.md](../../silver-noncommon-catalogs.md).
