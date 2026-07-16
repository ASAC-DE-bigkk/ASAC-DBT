-- gold_license_phone_succession — 연쇄창업: 같은 전화의 폐업→개업 업종전환 매트릭스.
--
-- 인사이트(#discovery 최종 비평 — 확실 판정): "같은 사업자가 폐업 후 무엇으로 재도전하나" —
-- 동일 정규화 전화번호에서 선행 폐업 후 후행 개업(간격 ≤3년, **주소 상이** — 동일 주소는
-- address_succession 소관이라 구조적 배제, 20+ 공용번호 컷). 주소·좌표가 바뀌어도 사업자
-- 단위 행태를 추적하는 유일한 축. 한계 명시: 전화 44%·번호 승계/재배정 노이즈 → 근사 지표.
-- materialized=table(소형 스냅샷).

{{ config(materialized='table', tags=['gold', 'insight']) }}

with p as (
    select t.major, t.category, e.dataset,
           regexp_replace(trim(e.sitetel), '[^0-9]', '') as tel,
           coalesce(trim(e.road_address), trim(e.jibun_address), '') as addr,
           case when regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(e.apvpermymd) end as o_iso,
           case when regexp_like(trim(coalesce(e.dcbymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(e.dcbymd) end as c_iso
    from {{ ref('silver_license_entity') }} e
    join {{ ref('commerce_dataset_taxonomy') }} t on t.short = e.dataset
    where e.sitetel is not null
      and length(regexp_replace(trim(e.sitetel), '[^0-9]', '')) between 9 and 11
),

tel_ok as (                                              -- 공용번호(20+ 지점) 컷
    select tel from p group by tel having count(*) < 20
),

pairs as (
    select a.major as closed_major, a.category as closed_category,
           b.major as opened_major, b.category as opened_category,
           date_diff('day', try(from_iso8601_date(a.c_iso)), try(from_iso8601_date(b.o_iso))) as gap_days,
           row_number() over (partition by a.tel, a.c_iso, a.category
                              order by b.o_iso) as rn
    from p a
    join tel_ok k on k.tel = a.tel
    join p b on b.tel = a.tel
    where a.c_iso is not null and b.o_iso is not null
      and b.o_iso > a.c_iso
      and b.o_iso <= cast(cast(try(from_iso8601_date(a.c_iso)) + interval '1095' day as date) as varchar)
      and a.addr <> b.addr                               -- 동일 주소 배제(자리 승계와 분리)
)

select closed_major, closed_category, opened_major, opened_category,
       {{ label_major_ko('closed_major') }}       as closed_major_ko,
       {{ label_category_ko('closed_category') }} as closed_category_ko,
       {{ label_major_ko('opened_major') }}       as opened_major_ko,
       {{ label_category_ko('opened_category') }} as opened_category_ko,
       count(*)                              as successions,
       round(avg(gap_days), 1)               as avg_gap_days,
       approx_percentile(gap_days, 0.5)      as p50_gap_days,
       count_if(gap_days <= 365)             as within_1y
from pairs
where rn = 1 and gap_days is not null and gap_days > 0
group by 1, 2, 3, 4
