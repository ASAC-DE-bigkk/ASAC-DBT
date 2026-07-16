-- gold_license_status_transition — 상태 전이 매트릭스(from→to) × 업종.
--
-- 인사이트(#discovery/change): "휴업하면 재개하나 폐업하나" — 상태 전이의 방향·확률.
-- status_duration(한 상태의 지속일)과 상보: 이건 **전이 자체의 빈도**. 예: 02→01(재개) vs
-- 02→03(휴업 후 폐업), 01→04(영업 중 취소) 등. history 버전순(원천 갱신시각) 인접쌍 집계.
-- materialized=table(소형 스냅샷).

{{ config(materialized='table', tags=['gold', 'insight']) }}

with h as (
    select dataset, opnsfteamcode, mgtno,
           substr(trim(coalesce(trdstategbn, '')), 1, 2) as st,
           coalesce(updatedt_ts, lastmodts_ts, collected_at) as vts,
           collected_at, content_hash
    from {{ ref('silver_license_entity_history') }}
    where trdstategbn is not null and trim(trdstategbn) <> ''
),

ord as (
    select dataset, st,
           lag(st) over (partition by dataset, opnsfteamcode, mgtno
                         order by vts, collected_at, content_hash) as prev_st
    from h
),

trans as (
    select dataset, prev_st as from_status, st as to_status
    from ord
    where prev_st is not null and prev_st <> st          -- 실제 전이만
)

select t.major, t.category, tr.dataset,
       tr.from_status, tr.to_status,
       case tr.from_status when '01' then '영업' when '02' then '휴업' when '03' then '폐업'
                           when '04' then '취소/말소' when '05' then '제외/전출' else '기타' end as from_group,
       case tr.to_status   when '01' then '영업' when '02' then '휴업' when '03' then '폐업'
                           when '04' then '취소/말소' when '05' then '제외/전출' else '기타' end as to_group,
       -- add-only 라벨: positional GROUP BY(1,2,3,4,5) 보존 위해 grain 컬럼 뒤에 배치.
       -- major_ko/category_ko 는 그룹키(t.major/t.category)의 함수적 종속 식, dataset_ko 는 max() 집계 → grain 불변.
       {{ label_major_ko('t.major') }} as major_ko,
       {{ label_category_ko('t.category') }} as category_ko,
       max(t.name_ko) as dataset_ko,
       count(*) as transitions
from trans tr
join {{ ref('commerce_dataset_taxonomy') }} t on t.short = tr.dataset
group by 1, 2, 3, 4, 5
