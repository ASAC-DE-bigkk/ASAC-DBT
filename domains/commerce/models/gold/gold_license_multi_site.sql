-- gold_license_multi_site — 동일 전화번호 다지점(체인/다점포 사업자 추정) × 업종.
--
-- 인사이트(#discovery/chain): 정규화 전화번호(숫자만, 9~11자리)가 같은 영업 중 업소 = 동일
-- 운영 주체 추정. 실측: 2-4지점 27,255개 번호(6.1만 지점)·5-19지점 855개. **20+ 지점 번호는
-- 공용/콜센터 의심으로 제외**(31개 번호). 업종별 다점포화 비율 — 프랜차이즈/체인 침투 신호.
-- 한계 명시: 전화 보유율 44%·번호 공유≠법인 동일. 근사 지표로 사용.
-- materialized=table(소형 스냅샷).

{{ config(materialized='table', tags=['gold', 'insight']) }}

with p as (
    select t.major, t.category, e.dataset,
           regexp_replace(trim(e.sitetel), '[^0-9]', '') as tel
    from {{ ref('silver_license_entity') }} e
    join {{ ref('commerce_dataset_taxonomy') }} t on t.short = e.dataset
    where substr(trim(coalesce(e.trdstategbn, '')), 1, 2) = '01'
      and e.sitetel is not null
      and length(regexp_replace(trim(e.sitetel), '[^0-9]', '')) between 9 and 11
),

tel_sites as (
    select tel, count(*) as n_sites from p group by 1
),

joined as (
    select p.major, p.category, p.dataset, p.tel, ts.n_sites
    from p join tel_sites ts on ts.tel = p.tel
    where ts.n_sites < 20                                 -- 공용번호 컷
)

select major, category, dataset,
       count(*)                                            as sites_with_phone,
       count_if(n_sites >= 2)                              as multi_site_locations,
       round(1.0 * count_if(n_sites >= 2) / count(*), 4)   as multi_site_ratio,
       count(distinct case when n_sites >= 2 then tel end) as multi_site_operators,
       max(n_sites)                                        as max_sites_per_operator
from joined
group by 1, 2, 3
