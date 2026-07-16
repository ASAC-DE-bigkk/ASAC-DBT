-- gold_license_change_activity — 업소 정보 변경 활동(개명·이전·갱신 빈도) × 업종.
--
-- 인사이트(#discovery/change): history 버전이력에서 "무엇이 자주 바뀌나" — 업소당 평균
-- 버전수(갱신 활발도), 개명(bplcnm 변경)·이전(도로명주소 변경) 발생 업소 비율.
-- 승계/리브랜딩·이전 패턴의 업종별 차이. materialized=table(소형 스냅샷).

{{ config(materialized='table', tags=['gold', 'insight']) }}

with h as (
    select dataset, opnsfteamcode, mgtno, bplcnm, road_address,
           coalesce(updatedt_ts, lastmodts_ts, collected_at) as vts,
           collected_at, content_hash
    from {{ ref('silver_license_entity_history') }}
),

ord as (
    select dataset, opnsfteamcode, mgtno,
           bplcnm, lag(bplcnm) over w as prev_name,
           road_address, lag(road_address) over w as prev_addr
    from h
    window w as (partition by dataset, opnsfteamcode, mgtno
                 order by vts, collected_at, content_hash)
),

per_biz as (
    select dataset, opnsfteamcode, mgtno,
           count(*)                                                   as versions,
           count_if(prev_name is not null and coalesce(bplcnm,'') <> coalesce(prev_name,'')
                    and coalesce(trim(bplcnm),'') <> '' and coalesce(trim(prev_name),'') <> '') as renames,
           count_if(prev_addr is not null and coalesce(road_address,'') <> coalesce(prev_addr,'')
                    and coalesce(trim(road_address),'') <> '' and coalesce(trim(prev_addr),'') <> '') as relocations
    from ord
    group by 1, 2, 3
)

select t.major, {{ label_major_ko('t.major') }} as major_ko,
       t.category, {{ label_category_ko('t.category') }} as category_ko,
       p.dataset, max(t.name_ko) as dataset_ko,
       count(*)                                     as businesses,
       round(avg(p.versions), 2)                    as avg_versions,
       max(p.versions)                              as max_versions,
       count_if(p.renames > 0)                      as with_rename,
       round(1.0 * count_if(p.renames > 0) / count(*), 4)      as rename_ratio,
       count_if(p.relocations > 0)                  as with_relocation,
       round(1.0 * count_if(p.relocations > 0) / count(*), 4)  as relocation_ratio
from per_biz p
join {{ ref('commerce_dataset_taxonomy') }} t on t.short = p.dataset
group by t.major, t.category, p.dataset
