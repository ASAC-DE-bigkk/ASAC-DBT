-- gold_license_dong_summary — 행정동별 업소 현황 집계(소형 · D1 export 1순위).
--
-- 서빙 레이어 정책(dags docs/PROJECT.md §4): D1(SQLite) 은 소형·조회 최적화 테이블만 받는다.
-- 이 모델은 그 대표 — 행정동(행안부 10자리) 그레인 수백 행짜리 사전 집계라 D1 특성(용량 상한·
-- 엣지 읽기 최적화·조인 최소화)에 정확히 부합한다(§4.2).
--
-- grain = admin_dong_code (마스킹 주소 등 admin_dong_code null 인 업소는 제외 — 동 매핑 불가).
-- 상태 코드: LOCALDATA 영업상태 TRDSTATEGBN — '01' 영업/정상 · '03' 폐업 (v1/v2 는 silver 에서 통합).

{{ config(materialized='table') }}

select
    admin_dong_code,
    max(admin_dong)                                   as admin_dong,
    max(gu_code)                                      as gu_code,
    max(gu)                                           as gu,
    count(*)                                          as business_count,
    count(*) filter (where trdstategbn = '01')        as business_open_count,
    count(*) filter (where trdstategbn = '03')        as business_closed_count,
    count(distinct dataset)                           as dataset_count,
    count(*) filter (where latitude is not null)      as geocoded_count,
    max(collected_at)                                 as latest_collected_at
from {{ ref('gold_license_entity') }}
where admin_dong_code is not null
group by admin_dong_code
