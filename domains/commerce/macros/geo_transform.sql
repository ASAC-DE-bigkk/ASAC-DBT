{#- 중부원점 TM(EPSG:5174) → WGS84 CTE 체인. 입력 CTE 는 source_coord_x/y 를 가져야 하며,
    출력 CTE `geo` 가 latitude/longitude 를 추가한다(원문 X/Y 는 보존). 파라미터·검증:
    docs/address-and-geo.md — 랜드마크 회귀 테스트: tests/assert_silver_license_current_geo_landmark.sql. -#}
{% macro tm5174_to_wgs84_ctes(input_cte) %}
-- ── 좌표 변환: 중부원점 TM(EPSG:5174, Bessel1841 · lat0 38° · lon0 127°0'10.405" ·
--    FE 200000 · FN 500000) → WGS84 위경도. 순수 계산(외부 보정 없음).
--    판별 근거·파라미터·검증(시청/GFC 랜드마크): docs/address-and-geo.md
--    상수는 사전 계산 수치 리터럴(Bessel e²=0.006674372231802, e'²=0.006719218799175,
--    M0(38°)=4207077.707850479, 직화계수 RECT=6366742.520369791, footpoint 급수 C2~C8).
geo_mu as (
    select
        *,
        try_cast(source_coord_x as double) as gx,
        try_cast(source_coord_y as double) as gy,
        (4207077.707850479 + (try_cast(source_coord_y as double) - 500000.0))
            / 6366742.520369791 as g_mu
    from {{ input_cte }}
),

geo_fp as (  -- footpoint 위도(급수 전개 — 반복 없음)
    select
        *,
        g_mu + 2.511273242321781e-3 * sin(2 * g_mu)
             + 3.678785854246945e-6 * sin(4 * g_mu)
             + 7.381011789501251e-9 * sin(6 * g_mu)
             + 1.683256291024713e-11 * sin(8 * g_mu) as g_phi1
    from geo_mu
),

geo_t as (
    select
        *,
        sin(g_phi1) as g_sp,
        cos(g_phi1) as g_cp,
        tan(g_phi1) as g_tp,
        6377397.155 / sqrt(1 - 0.006674372231802 * sin(g_phi1) * sin(g_phi1)) as g_n1,
        6377397.155 * (1 - 0.006674372231802)
            / power(1 - 0.006674372231802 * sin(g_phi1) * sin(g_phi1), 1.5) as g_r1
    from geo_fp
),

geo_d as (
    select
        *,
        (gx - 200000.0) / g_n1 as g_d,
        0.006719218799175 * g_cp * g_cp as g_c1,
        g_tp * g_tp as g_t1
    from geo_t
),

geo_bl as (  -- Bessel 타원체 위경도(라디안). lon0(127°0'10.405")=2.216618594896318 rad
    select
        *,
        g_phi1 - (g_n1 * g_tp / g_r1) * (
            g_d * g_d / 2
            - (5 + 3 * g_t1 + 10 * g_c1 - 4 * g_c1 * g_c1 - 9 * 0.006719218799175)
              * power(g_d, 4) / 24
            + (61 + 90 * g_t1 + 298 * g_c1 + 45 * g_t1 * g_t1
               - 252 * 0.006719218799175 - 3 * g_c1 * g_c1) * power(g_d, 6) / 720
        ) as g_phib,
        2.216618594896318 + (
            g_d - (1 + 2 * g_t1 + g_c1) * power(g_d, 3) / 6
            + (5 - 2 * g_c1 + 28 * g_t1 - 3 * g_c1 * g_c1
               + 8 * 0.006719218799175 + 24 * g_t1 * g_t1) * power(g_d, 5) / 120
        ) / g_cp as g_lamb
    from geo_d
),

geo_ecef as (  -- Bessel 타원체 위경도 → 지심직교(ECEF, h=0)
    select
        *,
        (6377397.155 / sqrt(1 - 0.006674372231802 * sin(g_phib) * sin(g_phib)))
            * cos(g_phib) * cos(g_lamb) as g_ex,
        (6377397.155 / sqrt(1 - 0.006674372231802 * sin(g_phib) * sin(g_phib)))
            * cos(g_phib) * sin(g_lamb) as g_ey,
        (6377397.155 / sqrt(1 - 0.006674372231802 * sin(g_phib) * sin(g_phib)))
            * (1 - 0.006674372231802) * sin(g_phib) as g_ez
    from geo_bl
),

geo_xyz as (  -- 7-parameter Helmert(한국 표준: ΔX -115.80 ΔY 474.99 ΔZ 674.11 ·
              -- rx 1.16" ry -2.31" rz -1.63" · s 6.43ppm, position-vector) → WGS84 ECEF
    select
        *,
        -115.80 + 1.00000643 * (g_ex - (-7.902463002085436e-6) * g_ey + (-1.119919603363028e-5) * g_ez) as g_wx,
        474.99 + 1.00000643 * ((-7.902463002085436e-6) * g_ex + g_ey - 5.623838700870617e-6 * g_ez) as g_wy,
        674.11 + 1.00000643 * (-(-1.119919603363028e-5) * g_ex + 5.623838700870617e-6 * g_ey + g_ez) as g_wz
    from geo_ecef
),

geo_pb as (  -- Bowring 보조항: 적도면 거리 p, 보조각 theta. a=6378137, b=6356752.314245179
    select
        *,
        sqrt(g_wx * g_wx + g_wy * g_wy) as g_p,
        atan2(g_wz * 6378137.0, sqrt(g_wx * g_wx + g_wy * g_wy) * 6356752.314245179) as g_theta
    from geo_xyz
),

geo_wgs as (  -- WGS84 ECEF → 위경도(Bowring 비반복식). e²=0.006694379990141, e'²=0.006739496742276
    select
        *,
        degrees(atan2(
            g_wz + 0.006739496742276 * 6356752.314245179 * power(sin(g_theta), 3),
            g_p - 0.006694379990141 * 6378137.0 * power(cos(g_theta), 3)
        )) as g_lat,
        degrees(atan2(g_wy, g_wx)) as g_lon
    from geo_pb
),

-- 좌표 유효성: 한반도 bbox 밖(원천 오류·타지역 지점·0/음수)은 null (원문 X/Y 는 보존).
geo as (
    select
        *,
        case when gx is not null and gy is not null
                  and g_lat between 33.0 and 39.5 and g_lon between 124.0 and 132.0
             then round(g_lat, 7) end as latitude,
        case when gx is not null and gy is not null
                  and g_lat between 33.0 and 39.5 and g_lon between 124.0 and 132.0
             then round(g_lon, 7) end as longitude
    from geo_wgs
)
{% endmacro %}
