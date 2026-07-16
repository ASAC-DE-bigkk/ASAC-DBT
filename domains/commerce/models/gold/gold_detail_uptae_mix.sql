-- gold_detail_uptae_mix — 업태(uptaenm) 구성·플로우 × 업종 × 자치구.
--
-- 인사이트(#discovery 최종 비평 — 준확실 판정): uptaenm 은 **소스의 마지막 미소비 분류 축**
-- (taxonomy 소분류보다 한 단계 깊음 — 예: 일반음식점 안의 한식/커피숍/호프). 보유 detail 중 실물 컬럼 보유 19개 union(silver_lodging_detail 은 카탈로그-실물 스키마
-- 드리프트로 제외 — change-log 비고), 현재 버전(entity ⋈ content_hash) 기준 영업 스톡 + 최근 1년 개업.
-- materialized=table(소형 스냅샷).

{{ config(materialized='table', tags=['gold', 'insight']) }}

with ent as (
    select t.major, t.category, t.name_ko, e.gu, e.dataset, e.opnsfteamcode, e.mgtno, e.content_hash,
           coalesce(e.gu_code, 'UNK') as gu_code,
           substr(trim(coalesce(e.trdstategbn, '')), 1, 2) as st,
           case when regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(e.apvpermymd) end as o_iso
    from {{ ref('silver_license_entity') }} e
    join {{ ref('commerce_dataset_taxonomy') }} t on t.short = e.dataset
),

kst as (
    select cast(cast(current_timestamp at time zone 'Asia/Seoul' as date) as varchar) as today
),

raw as (
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_amusement_park_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_animal_sale_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_emission_repair_agent_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_feed_manufacturing_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_food_sanitation_business_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_high_pressure_gas_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_hospital_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_large_store_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_livestock_processing_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_livestock_sale_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_livestock_storage_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_livestock_transport_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_mail_order_sale_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_medical_institution_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_medical_similar_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_petroleum_alt_fuel_sale_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_petroleum_sale_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_public_sanitation_service_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    union all
    select e.major, e.category, e.name_ko, e.gu, e.dataset, e.gu_code, e.st, e.o_iso,
           nullif(trim(d.uptaenm), '') as uptaenm
    from ent e
    join {{ source('commerce_silver_details', 'silver_sports_facility_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
)

select r.major, r.category, r.dataset, r.uptaenm, r.gu_code,
       {{ label_major_ko('r.major') }} as major_ko,
       {{ label_category_ko('r.category') }} as category_ko,
       max(r.name_ko) as dataset_ko,
       max(r.gu) as gu,
       count_if(r.st = '01')                            as active_cnt,
       count(*)                                          as total_cnt,
       count_if(r.o_iso >= cast(cast(from_iso8601_date(k.today) - interval '365' day as date) as varchar)
                and r.o_iso < k.today)                   as opened_last_365d
from raw r cross join kst k
where r.uptaenm is not null
group by 1, 2, 3, 4, 5
