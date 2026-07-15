-- gold_license_status_duration — 상태 지속기간 요약: 상태가 바뀔 때 그 상태가 얼마나 유지됐나.
--
-- 인사이트 계약(#71): 이력(silver_license_entity_history)의 **상태 전이**를 세그먼트로 병합해
-- (같은 상태 연속 버전 = 1세그먼트), 세그먼트 지속일을 상태군·업종·시군구별로 집계한다 —
-- "상태 변화 데이터로 지속기간이 분야별로 어떻게 다른지"의 정본. 상태군은 코드 2자리 정규화
-- (dataset 별 라벨 이질 — status-aggregation-queries.md §1.1). dtl 상태(테이블 특성별 상이)는
-- dataset 스코프 쿼리로 별도 조회(§4.4) — 전역 grain 에 넣으면 코드체계가 섞여 오염된다.
--
-- 시각 기준: coalesce(updatedt_ts, lastmodts_ts, collected_at) — 원천 갱신시각(상태 변화의
-- 실제 시점) 우선. 진행 중 세그먼트(is_ongoing)는 KST 오늘까지로 계산해 구분 표기.
-- materialized=table(소형 요약 — 전량 재계산이 곧 멱등·중복 불가. D1 export 는 스냅샷 교체).

{{ config(materialized='table') }}

with h as (
    select dataset, opnsfteamcode, mgtno,
           substr(trim(coalesce(trdstategbn, '')), 1, 2) as st,
           coalesce(updatedt_ts, lastmodts_ts, collected_at) as vts,
           collected_at, content_hash
    from {{ ref('silver_license_entity_history') }}
    where trdstategbn is not null and trim(trdstategbn) <> ''
),

ord as (
    select *,
           lag(st) over (partition by dataset, opnsfteamcode, mgtno
                         order by vts, collected_at, content_hash) as prev_st
    from h
),

-- 상태 변경점만 = 세그먼트 시작 (첫 버전 포함)
seg_start as (
    select dataset, opnsfteamcode, mgtno, st, vts, collected_at, content_hash
    from ord
    where prev_st is null or prev_st <> st
),

seg as (
    select *,
           lead(vts) over (partition by dataset, opnsfteamcode, mgtno
                           order by vts, collected_at, content_hash) as next_start
    from seg_start
),

dur as (
    select dataset, st,
           next_start is null as is_ongoing,
           date_diff('day', vts,
                     coalesce(next_start,
                              cast(current_timestamp at time zone 'Asia/Seoul' as timestamp(6)))) as days
    from seg
    where vts is not null
)

select d.dataset,
       max(t.major)    as major,
       max(t.category) as category,
       d.st            as status_code,
       case d.st when '01' then '영업/정상' when '02' then '휴업' when '03' then '폐업'
                 when '04' then '취소/말소' when '05' then '제외/전출' else '기타' end as status_group,
       d.is_ongoing,
       count(*)                              as n_segments,
       round(avg(d.days), 1)                 as avg_days,
       approx_percentile(d.days, 0.5)        as p50_days,
       approx_percentile(d.days, 0.9)        as p90_days,
       max(d.days)                           as max_days
from dur d
join {{ ref('commerce_dataset_taxonomy') }} t on t.short = d.dataset
where d.days >= 0                            -- 시각 역전(원천 오류) 세그먼트 제외
group by d.dataset, d.st, d.is_ongoing
