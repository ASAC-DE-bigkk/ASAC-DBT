-- gold: 시간대별 장소 인구혼잡도 (silver를 소비, 평균 인구 등 파생 + 위치/행정구역 보강).
--
-- incremental(merge): silver의 최근 수집분만(30분 lookback) 읽어 (ppltn_time, area_cd)
-- 키로 merge한다. 5분마다 전체 재생성하지 않으므로 스냅샷/데이터파일 누적이 최소화된다.
-- 실시간 지도(최신 슬라이스)와 시간별 분석(누적 히스토리)을 한 테이블로 동시에 만족한다.
--
-- 보강(참조 조인, gold의 몫):
--  * 위치: seed(seoul_ppltn_area_geo)를 area_cd로 left join → 중심점/카테고리
--  * 행정구역(통합축): area 중심점을 자치구 경계 seed(seoul_gu_boundary)에 point-in-polygon
--    → sido/sigungu. 좌표는 도메인마다 기준계·값이 달라 직접 join이 안 되므로, 도메인 간
--    통합 join 키는 행정구역(시/구)으로 통일한다. 좌표는 표시/정밀용으로 유지.
--
-- ⚠ 기존 table에서 전환 시 drop 없이 그대로 run하면 기존 테이블에 merge된다(안전).

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['ppltn_time', 'area_cd'],
) }}

with area_admin as (
    -- area 중심점 → 행정동 판정(정적, area당 1건). 동 경계 하나로 시/구/동을 한 번에
    -- (동 code 앞 5자리 = 자치구라 sigungu도 seed에 함께 있음). 경계 겹침 대비 1건 제한.
    select area_cd, sido, sigungu, dong
    from (
        select
            g.area_cd,
            '서울특별시' as sido,
            b.sigungu,
            b.dong,
            row_number() over (partition by g.area_cd order by b.dong) as rn
        from {{ ref('seoul_ppltn_area_geo') }} g
        left join {{ ref('seoul_dong_boundary') }} b
            on ST_Contains(ST_GeometryFromText(b.boundary_wkt), ST_Point(g.center_lon, g.center_lat))
    )
    where rn = 1
)

select
    s.ppltn_time,
    s.area_nm,
    s.area_cd,
    aa.sido,
    aa.sigungu,
    aa.dong,
    geo.category as area_category,
    geo.center_lon,
    geo.center_lat,
    s.area_congest_lvl,
    s.area_ppltn_min,
    s.area_ppltn_max,
    (s.area_ppltn_min + s.area_ppltn_max) / 2 as avg_ppltn,
    s.male_ppltn_rate,
    s.female_ppltn_rate,
    s.ppltn_rate_0,
    s.ppltn_rate_10,
    s.ppltn_rate_20,
    s.ppltn_rate_30,
    s.ppltn_rate_40,
    s.ppltn_rate_50,
    s.ppltn_rate_60,
    s.ppltn_rate_70,
    s.resnt_ppltn_rate,
    s.non_resnt_ppltn_rate,
    s.collected_at
from {{ ref('silver_seoul_ppltn') }} s
left join {{ ref('seoul_ppltn_area_geo') }} geo
    on s.area_cd = geo.area_cd
left join area_admin aa
    on s.area_cd = aa.area_cd
{% if is_incremental() %}
-- 이미 반영된 collected_at 이후(-30분 여유)의 silver만 스캔. merge가 기존 키를
-- 갱신하므로 lookback으로 같은 행을 다시 읽어도 결과는 동일(멱등).
where s.collected_at >= (
    select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
    from {{ this }}
)
{% endif %}
