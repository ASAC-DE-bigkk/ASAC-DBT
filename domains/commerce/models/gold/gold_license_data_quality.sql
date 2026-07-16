-- gold_license_data_quality — dataset(API)별 데이터 커버리지·품질 프로파일 (거버넌스).
--
-- 인사이트(#discovery/quality): "어느 API 가 결측이 심한가" — 전화/좌표/행정동매핑/폐업일/주소
-- 보유율을 API 단위로 진단. 서빙·분석 신뢰도 판단과 수집 개선 우선순위의 근거.
-- materialized=table(소형 스냅샷 — 매일 재계산).

{{ config(materialized='table', tags=['gold', 'insight']) }}

select t.major, {{ label_major_ko('t.major') }} as major_ko,
       t.category, {{ label_category_ko('t.category') }} as category_ko,
       e.dataset, max(t.name_ko) as dataset_ko,
       count(*)                                                          as total_rows,
       count_if(substr(trim(coalesce(e.trdstategbn,'')),1,2) = '01')     as active_rows,
       round(1.0 * count_if(e.sitetel is not null and trim(e.sitetel) <> '') / count(*), 4)  as phone_coverage,
       round(1.0 * count_if(e.latitude is not null) / count(*), 4)       as geo_coverage,
       round(1.0 * count_if(e.admin_dong_code is not null) / count(*), 4) as admin_dong_coverage,
       round(1.0 * count_if(coalesce(trim(e.road_address), '') <> ''
                         or coalesce(trim(e.jibun_address), '') <> '') / count(*), 4) as address_coverage,
       round(1.0 * count_if(regexp_like(trim(coalesce(e.dcbymd,'')), '^\d{4}'))
             / nullif(count_if(substr(trim(coalesce(e.trdstategbn,'')),1,2) = '03'), 0), 4)  as close_date_coverage_of_closed,
       round(1.0 * count_if(e.bplcnm is not null and trim(e.bplcnm) <> '') / count(*), 4)    as name_coverage
from {{ ref('silver_license_entity') }} e
join {{ ref('commerce_dataset_taxonomy') }} t on t.short = e.dataset
group by t.major, t.category, e.dataset
