-- gold_license_stock_age_band — 영업 중(01) 업소의 업력 밴드 분포 × 업종 3단 × 자치구.
--
-- 인사이트(#discovery): "지금 영업 중인 업소들의 연령 구성" — 신생 상권(1년 미만 비중 높음) vs
-- 노포 상권(20년+ 비중)을 구분. flow(이벤트)·lifespan(폐업분)과 달리 **생존자 스톡의 구성**.
-- materialized=table(소형 스냅샷 — 매일 재계산이 정합. D1 은 스냅샷 교체).

{{ config(materialized='table', tags=['gold', 'insight']) }}

with e as (
    select t.major, t.category, e.dataset, coalesce(e.gu_code, 'UNK') as gu_code,
           t.name_ko, e.gu,
           date_diff('day',
               try(from_iso8601_date(case when regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$')
                                          then trim(e.apvpermymd) end)),
               cast(current_timestamp at time zone 'Asia/Seoul' as date)) as age_days
    from {{ ref('silver_license_entity') }} e
    join {{ ref('commerce_dataset_taxonomy') }} t on t.short = e.dataset
    where substr(trim(coalesce(e.trdstategbn, '')), 1, 2) = '01'          -- 영업 중만
),

banded as (
    select major, category, dataset, gu_code, name_ko, gu,
           case when age_days < 365        then '0_lt1y'
                when age_days < 365 * 3    then '1_1to3y'
                when age_days < 365 * 5    then '2_3to5y'
                when age_days < 365 * 10   then '3_5to10y'
                when age_days < 365 * 20   then '4_10to20y'
                else                            '5_ge20y' end as age_band
    from e
    where age_days is not null and age_days >= 0
)

select major, category, dataset, gu_code, age_band,
       count(*) as active_cnt,
       -- add-only 라벨 컬럼(포지셔널 GROUP BY 1..5 보존 위해 code 컬럼 뒤 일괄 배치; 모두 group key 종속 → grain 불변)
       {{ label_major_ko('major') }} as major_ko,
       {{ label_category_ko('category') }} as category_ko,
       max(name_ko) as dataset_ko,
       max(gu) as gu,
       {{ label_age_band_ko('age_band') }} as age_band_ko
from banded
group by 1, 2, 3, 4, 5
