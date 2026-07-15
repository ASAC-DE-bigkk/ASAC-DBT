-- gold_license_geo_grid — 좌표 격자(~500m) 상권 히트맵 × 업종.
--
-- 인사이트(#discovery/geo): 행정동보다 세밀한 **공간 밀도** — 좌표(84% 커버) 를 0.005도
-- (~서울 위도에서 500m 내외) 격자로 스냅해 영업 중 업소 밀도·최근 1년 개업을 집계.
-- 지도 히트맵/핫스팟 서빙용(D1 후보 — 격자 중심좌표 포함 평탄 스냅샷).
-- materialized=table(소형 스냅샷 — 수만 셀).

{{ config(materialized='table', tags=['gold', 'insight']) }}

with e as (
    select t.major, t.category,
           round(e.latitude  / 0.005) * 0.005 as grid_lat,
           round(e.longitude / 0.005) * 0.005 as grid_lng,
           substr(trim(coalesce(e.trdstategbn, '')), 1, 2) as st,
           case when regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$')
                then trim(e.apvpermymd) end as o_iso
    from {{ ref('silver_license_entity') }} e
    join {{ ref('commerce_dataset_taxonomy') }} t on t.short = e.dataset
    where e.latitude between 37.3 and 37.8                -- 서울 bbox 가드
      and e.longitude between 126.6 and 127.3
),

kst as (
    select cast(cast(current_timestamp at time zone 'Asia/Seoul' as date) as varchar) as today
)

select grid_lat, grid_lng, major, category,
       count_if(st = '01')                              as active_cnt,
       count_if(e.o_iso >= cast(cast(from_iso8601_date(k.today) - interval '365' day as date) as varchar)
                and e.o_iso < k.today and st = '01')     as opened_last_365d_active
from e cross join kst k
group by 1, 2, 3, 4
having count_if(st = '01') > 0
