-- gold_detail_area_profile — 영업장 면적(sitearea, ㎡) 분포 × 업종 3단 × 자치구.
--
-- 인사이트(#discovery/detail): 업종을 넘는 공통 payload 축 1위(23개 detail 보유, 수치 유효율
-- ~78% 실측) — "이 업종/구의 평균 영업장 크기". 영업(01) 현재 버전만(entity ⋈ detail
-- content_hash 매칭 — 정본 패턴). materialized=table(소형 스냅샷).

{{ config(materialized='table', tags=['gold', 'insight']) }}

with ent as (
    select t.major, t.category, e.dataset, e.opnsfteamcode, e.mgtno, e.content_hash,
           coalesce(e.gu_code, 'UNK') as gu_code
    from {{ ref('silver_license_entity') }} e
    join {{ ref('commerce_dataset_taxonomy') }} t on t.short = e.dataset
    where substr(trim(coalesce(e.trdstategbn, '')), 1, 2) = '01'
),

raw as (
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_amusement_park_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_animal_drug_wholesale_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_animal_hospital_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_animal_medical_device_sale_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_animal_pharmacy_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_animal_sale_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_culture_arts_corporation_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_feed_manufacturing_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_food_sanitation_business_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_high_pressure_gas_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_hospital_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_large_store_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_livestock_breeding_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_livestock_processing_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_livestock_sale_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_livestock_storage_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_livestock_transport_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_lodging_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_meat_packaging_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_petroleum_sale_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_public_sanitation_service_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_sports_facility_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.dataset, e.gu_code,
           case when regexp_like(trim(coalesce(d.sitearea, '')), '^[0-9]+(\.[0-9]+)?$')
                then cast(trim(d.sitearea) as double) end as area_m2
    from ent e
    join {{ source('commerce_silver_details', 'silver_tourism_operator_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
)

select major, category, dataset, gu_code,
       count(area_m2)                          as n_with_area,
       round(avg(area_m2), 1)                  as avg_m2,
       approx_percentile(area_m2, 0.5)         as p50_m2,
       approx_percentile(area_m2, 0.9)         as p90_m2,
       count_if(area_m2 < 33)                  as lt_33m2,
       count_if(area_m2 >= 330)                as ge_330m2
from raw
where area_m2 is not null and area_m2 > 0 and area_m2 < 1000000   -- 이상치 컷
group by 1, 2, 3, 4
