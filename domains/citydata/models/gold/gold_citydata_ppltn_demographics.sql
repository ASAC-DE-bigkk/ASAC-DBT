-- gold: 장소×요일×시간대 인구 **성별·나이대 세그먼트** 패턴 (챗봇 서빙용, R2→D1 export 소스).
--
-- silver_citydata_ppltn 의 wide 한 성별/나이대 비율을 **long** 으로 언피벗해
-- (area, dow, hour, segment_type, segment) 그레인으로 요일×시간대 평균 집계한다.
-- "토요일 오후 2시 20대가 가장 많은 지역" 류 질의를 segment 필터 + avg_est_headcount
-- 정렬로 바로 답한다. 성별×나이대 교차는 API 에 없어 담지 않는다 — 챗봇/D1 이
-- age headcount × gender rate 로 곱해 근사(독립가정, 여기서 곱하나 거기서 곱하나 동일).
--
-- 지표:
--  * avg_rate_pct        : 그 (요일,시간) 버킷의 세그먼트 비율(%) 평균
--  * avg_est_headcount    : 추정 인원수 평균 = avg(인구중간값 × 비율/100). ★"많은" 랭킹 키.
--                           ⚠ 인구범위 중간값 × 비율 추정치(교차분포 아님).
--  * avg_ppltn            : 인구중간값 평균 (세그먼트 무관 참고)
--  * avg_congest_score    : 혼잡도 평균 (1 여유 · 2 보통 · 3 약간붐빔 · 4 붐빔)
--  * sample_count         : 집계된 5분 실측 스냅샷 수 (신뢰도)
--
-- silver_ppltn 은 LIVE_PPLTN(실측)만 파싱하므로 전 행이 실측이다(fcst_yn 은 "예보 존재
-- 여부" 플래그라 전부 'Y' — 실측/예보 구분 아님, 필터 안 함).
-- table+replace(프로젝트 기본) 상속 — 매 run 전체 재빌드(멱등).
-- dow: Trino day_of_week — 1=월 … 6=토 … 7=일. hour: 0~23 (KST, event_at 기준).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
) }}

with src as (
    select
        p.area_cd,
        p.admin_dong_code,
        p.gu_code,
        p.longitude,
        p.latitude,
        day_of_week(p.event_at) as dow,
        hour(p.event_at)        as hour,
        (cast(p.area_ppltn_min as double) + p.area_ppltn_max) / 2.0 as pop_mid,
        case p.area_congest_lvl
            when '여유'      then 1
            when '보통'      then 2
            when '약간 붐빔' then 3
            when '붐빔'      then 4
        end as congest_score,
        p.male_ppltn_rate, p.female_ppltn_rate,
        p.ppltn_rate_0, p.ppltn_rate_10, p.ppltn_rate_20, p.ppltn_rate_30,
        p.ppltn_rate_40, p.ppltn_rate_50, p.ppltn_rate_60, p.ppltn_rate_70
    from {{ ref('silver_citydata_ppltn') }} p
    where p.event_at is not null
        and p.area_ppltn_max is not null
),

-- wide → long: 성별 2 + 나이대 8 = 10 세그먼트를 병렬 배열 UNNEST 로 언피벗.
unpvt as (
    select
        s.area_cd, s.admin_dong_code, s.gu_code, s.longitude, s.latitude,
        s.dow, s.hour, s.pop_mid, s.congest_score,
        seg.segment_type, seg.segment, seg.rate
    from src s
    cross join unnest(
        array['gender', 'gender', 'age', 'age', 'age', 'age', 'age', 'age', 'age', 'age'],
        array['male', 'female', '0', '10', '20', '30', '40', '50', '60', '70'],
        array[s.male_ppltn_rate, s.female_ppltn_rate,
              s.ppltn_rate_0, s.ppltn_rate_10, s.ppltn_rate_20, s.ppltn_rate_30,
              s.ppltn_rate_40, s.ppltn_rate_50, s.ppltn_rate_60, s.ppltn_rate_70]
    ) as seg (segment_type, segment, rate)
    where seg.rate is not null
)

select
    u.area_cd,
    a.area_nm,
    a.area_category,
    u.admin_dong_code,
    u.gu_code,
    u.longitude,
    u.latitude,
    u.dow,
    u.hour,
    u.segment_type,
    u.segment,
    round(avg(u.rate), 2)                          as avg_rate_pct,
    round(avg(u.pop_mid * u.rate / 100.0), 1)      as avg_est_headcount,
    round(avg(u.pop_mid), 1)                       as avg_ppltn,
    round(avg(u.congest_score), 2)                 as avg_congest_score,
    count(*)                                       as sample_count
from unpvt u
left join {{ ref('dim_seoul_area') }} a on u.area_cd = a.area_cd
group by
    u.area_cd, a.area_nm, a.area_category, u.admin_dong_code, u.gu_code,
    u.longitude, u.latitude, u.dow, u.hour, u.segment_type, u.segment
