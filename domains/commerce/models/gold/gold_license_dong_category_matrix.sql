-- gold_license_dong_category_matrix — 행정동 × 중분류(category) 스톡 매트릭스.
--
-- 인사이트(#discovery/geo): dong_summary(행정동 총계)의 업종 세분판 — "이 동네엔 뭐가 많나".
-- 지도/동네 프로파일의 핵심 입력(D1 export 1순위급 — 417동 × 11분류 소형). 영업(01) 스톡 +
-- 최근 1년 개업 수(동네 활력 신호) 병기.
-- materialized=table(소형 스냅샷).

{{ config(materialized='table', tags=['gold', 'insight']) }}

with e as (
    select t.major, t.category,
           coalesce(e.admin_dong_code, 'UNK') as admin_dong_code,
           max(e.admin_dong) over (partition by e.admin_dong_code) as admin_dong,
           coalesce(e.gu_code, 'UNK') as gu_code, e.gu,
           substr(trim(coalesce(e.trdstategbn, '')), 1, 2) as st,
           case when regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$')
                then trim(e.apvpermymd) end as o_iso
    from {{ ref('silver_license_entity') }} e
    join {{ ref('commerce_dataset_taxonomy') }} t on t.short = e.dataset
),

kst as (
    select cast(cast(current_timestamp at time zone 'Asia/Seoul' as date) as varchar) as today
)

select e.admin_dong_code, max(e.admin_dong) as admin_dong,
       e.gu_code, max(e.gu) as gu,
       e.major, e.category,
       count_if(e.st = '01')                            as active_cnt,
       count(*)                                          as total_cnt,
       count_if(e.o_iso >= cast(cast(from_iso8601_date(k.today) - interval '365' day as date) as varchar)
                and e.o_iso < k.today)                   as opened_last_365d
from e cross join kst k
group by e.admin_dong_code, e.gu_code, e.major, e.category
