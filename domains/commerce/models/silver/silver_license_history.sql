-- 인허가 변경 이력(정제된 변경로그). bronze 변경로그 → publishable run 필터 → 파싱/파생 →
-- 연속 중복 제거(diff 재유입·reconcile 재방출 제거, 정당한 원복 A→B→A 보존).
{{ config(pre_hook="{{ delete_unmarked_silver_history_runs() }}") }}

-- materialized=incremental(append): 첫 실행/--full-refresh 는 전체 publishable run 을 백필하고,
-- 이후 실행은 silver_load_run_marker 의 DONE marker 가 없는 bronze_run_id 만 증분 처리한다.
-- 명시적 버전 컬럼(version_seq/valid_from/valid_to/is_current) 없음 —
-- **(dataset, opnsfteamcode, mgtno)** 안에서 (updatedt_sort, lastmodts_sort, observed_date,
-- collected_at, content_hash) 내림차순 정렬이 곧 버전 순서다(암묵 버저닝). current 는 최신 1행.
-- MGTNO 는 **발급 자치단체(OPNSFTEAMCODE) 안에서만 유니크**(실측: 관광식당 등 55개 키가
-- 서로 다른 구청의 별개 업소를 공유) — 업소 식별키에 opnsfteamcode 를 반드시 포함한다.
-- (같은 키의 업장명/상태 변경은 승계·개명 등 정상 버전 이력 — 키 충돌이 아님.)
-- 타임존 정책: silver 의 timestamp 는 **전부 KST(naive)** — KST 원문(UPDATEDT/LASTMODTS)은
-- 문자열로 보존하고 *_ts 는 파싱만(무변환, KST), collected_at 은 bronze 의 UTC 값을 +9h 하여 KST 로 변환.
-- (bronze 는 UTC 원본을 그대로 유지 = 소스 진실; KST 일원화는 silver 표기 계층에서만.)
-- 주소·동·좌표 보강 규약(지번 채움 우선순위, 법정동/행정동 분류·매핑, EPSG:5174→WGS84):
--   docs/address-and-geo.md · 결측 규약: docs/timestamps-and-nulls.md · 컬럼 구조: docs/dataset-columns.md

with publishable as (
    -- 데이터셋별 발행 게이트: is_publishable 인 (dataset, bronze_run_id) 만 반영.
    select distinct
        cast(dataset as varchar) as dataset,
        cast(bronze_run_id as varchar) as bronze_run_id
    from {{ source('commerce_bronze', 'collection_run_manifest') }}
    where status = 'SUCCESS'
      and is_publishable
),

bronze as (
    select
        cast(b.dataset as varchar) as dataset,
        cast(b.record_json as varchar) as record_json,   -- 원본 보존(비공통 필드 포함). silver 가 v1/v2 별칭으로 파싱
        cast(b.content_hash as varchar) as content_hash,
        cast(b.observed_date as varchar) as observed_date,
        cast(b.load_date as varchar) as load_date,
        cast(b.bronze_run_id as varchar) as bronze_run_id,
        cast(b.dag_run_id as varchar) as dag_run_id,
        cast(b.raw_object_key as varchar) as raw_object_key,
        -- bronze 는 수집 시점을 UTC 로 기록(_utcnow_iso). silver 는 KST 일원화 → +9h 로 변환.
        -- (한국은 DST 없음 — 고정 오프셋. bronze 원본은 UTC 유지, 여기서만 표기 변환.)
        cast(b.collected_at as timestamp(6)) + interval '9' hour as collected_at
    from {{ source('commerce_bronze', 'localdata_license') }} as b
    inner join publishable as p
        on cast(b.dataset as varchar) = p.dataset
        and cast(b.bronze_run_id as varchar) = p.bronze_run_id
    -- 단위 제외(삭제) — vars 목록 기반. 정책: docs/rebuild-and-ops.md
    where 1 = 1
        {{ not_in_excluded("cast(b.dataset as varchar)", 'exclude_datasets') }}
        {{ not_in_excluded("cast(b.observed_date as varchar)", 'exclude_observed_dates') }}
        {{ not_in_excluded("cast(b.load_date as varchar)", 'exclude_load_dates') }}
        {{ not_in_excluded("cast(b.bronze_run_id as varchar)", 'exclude_bronze_run_ids') }}
        {% if is_incremental() %}
        -- DONE marker 기반 증분: dbt test 통과 후 Airflow 가 기록한 run 만 완료로 간주한다.
        -- target table 이 없거나 --full-refresh 이면 is_incremental() 이 false 라 전체 백필된다.
        and {{ silver_unmarked_publishable_predicate('b') }}
        {% endif %}
),

parsed as (
    select
        *,
        -- 결측 규약: 원본 '' → null. record_json 원본은 보존. v1(구형)·v2(신형) 컬럼 표준을 lf() 로
        -- 정본(v1) 우선 → 없으면 v2 별칭으로 정규화. (개방자치단체코드+관리번호 = 업소 식별키.)
        {{ lf('MGTNO', 'MNG_NO') }} as mgtno,
        {{ lf('OPNSFTEAMCODE', 'OGDP_INST_CD') }} as opnsfteamcode,
        {{ lf('BPLCNM', 'BPLC_NM') }} as bplcnm,
        {{ lf('TRDSTATEGBN', 'SALS_STTS_CD') }} as trdstategbn,
        {{ lf('TRDSTATENM', 'SALS_STTS_NM') }} as trdstatenm,
        {{ lf('DTLSTATEGBN', 'DTL_SALS_STTS_CD') }} as dtlstategbn,
        {{ lf('DTLSTATENM', 'DTL_SALS_STTS_NM') }} as dtlstatenm,
        {{ lf('APVPERMYMD', 'LCPMT_YMD') }} as apvpermymd,
        {{ lf('DCBYMD', 'CLSBIZ_YMD') }} as dcbymd,
        {{ lf('SITETEL', 'TELNO') }} as sitetel,
        -- 지번주소 원천: v1 SITEWHLADDR + 숙박업/v2 의 LOTNO_ADDR
        {{ lf('SITEWHLADDR') }} as jibun_address_src,
        {{ lf('LOTNO_ADDR') }} as lotno_address,
        {{ lf('RDNWHLADDR', 'ROAD_NM_ADDR') }} as road_address,
        {{ lf('X', 'XCRD') }} as source_coord_x,
        {{ lf('Y', 'YCRD') }} as source_coord_y,
        {{ lf('LASTMODTS', 'LAST_MDFCN_YMD') }} as lastmodts,
        {{ lf('UPDATEDT', 'DATA_UPDT_YMD') }} as updatedt
    from bronze
),

-- Juso 보강 캐시(filled 만) — 키 유니크는 로더가 보장하나 조인 팬아웃 방지로 한 번 더 접는다.
juso_fill as (
    select
        cast(road_address_norm as varchar) as road_address_norm,
        max(cast(jibun_address as varchar)) as jibun_address_juso
    from {{ source('commerce_bronze', 'address_enrichment') }}
    where status = 'filled'
    group by 1
),

-- 지번 채움: 원천(SITEWHLADDR) → LOTNO_ADDR(필드명 상이 업종군) → Juso(도로명 키 조인).
-- 채움 계보는 jibun_address_source 로 남긴다(source|lotno_addr|juso_api|null).
enriched as (
    select
        p.*,
        nullif(trim(regexp_replace(regexp_replace(coalesce(p.road_address, ''), '\(.*$', ''), '\s+', ' ')), '') as road_address_norm,
        coalesce(p.jibun_address_src, p.lotno_address, j.jibun_address_juso) as jibun_address,
        case
            when p.jibun_address_src is not null then 'source'
            when p.lotno_address is not null then 'lotno_addr'
            when j.jibun_address_juso is not null then 'juso_api'
        end as jibun_address_source
    from parsed as p
    left join juso_fill as j
        on nullif(trim(regexp_replace(regexp_replace(coalesce(p.road_address, ''), '\(.*$', ''), '\s+', ' ')), '') = j.road_address_norm
),

normalized as (
    select
        *,
        -- UPDATEDT/LASTMODTS(KST 문자열, 14자리 기대, 비정형 가능) → **KST** timestamp(파싱만·무변환). 실패 시 null.
        -- (updatedt 는 parsed 에서 v1/v2 정규화됨 → 여기서 파싱. 정렬키는 keyed 에서 이걸 씀.)
        try(date_parse(
            substr(regexp_replace(updatedt, '[^0-9]', ''), 1, 14), '%Y%m%d%H%i%s'
        )) as updatedt_ts,
        try(date_parse(
            substr(regexp_replace(lastmodts, '[^0-9]', ''), 1, 14), '%Y%m%d%H%i%s'
        )) as lastmodts_ts,
        -- 주소 정규화 v1: '(' 이후 절단 → 연속 공백 1개 → trim → 빈값 null. (Python 수집측과 규칙 동일)
        nullif(trim(regexp_replace(regexp_replace(coalesce(jibun_address, ''), '\(.*$', ''), '\s+', ' ')), '') as jibun_address_norm,
        -- 자치구(gu) 파생 — 도로명 우선, 지번 폴백. 서울 외/미매칭은 null. (구 district 컬럼)
        -- 접두 변형 대응: 서울특별시|서울시|서울 + 무공백 결합형(서울시노원구…)까지 흡수.
        -- 시도/구 사이 공백은 \s*(0개 이상), 구는 lazy([가-힣]+?구)로 첫 '구'에서 멈춤(구로구구로동 안전).
        regexp_extract(
            coalesce(road_address, jibun_address, ''), '서울(?:특별시|시)?\s*([가-힣]+?구)', 1
        ) as gu
    from enriched
),

-- 지번주소의 동 토큰(구 다음). 지번 표기의 동은 원칙적으로 **법정동** — 분류는 참조로 판정.
-- gu 와 동일한 접두/무공백 대응. 동 토큰은 `[가-힣]+\d*(동|가)` 로 **번지 앞에서 정지** —
-- 무공백 결합형(마포구 공덕2동461)에서 동과 번지가 붙어도 '공덕2동' 만 뽑는다.
dong_token as (
    select
        *,
        case
            when coalesce(road_address, '') like '%*%' or coalesce(jibun_address, '') like '%*%'
                then null
            else nullif(regexp_extract(coalesce(jibun_address_norm, ''), '서울(?:특별시|시)?\s*[가-힣]+?구\s*([가-힣]+\d*(?:동|가))', 1), '')
        end as dong_raw
    from normalized
),

-- 행안부 행정동↔법정동 참조(서울) — enrich_admin_dong_ref 가 전량 교체 적재.
ref_dong as (
    select distinct
        cast(sgg_name as varchar) as sgg_name,
        cast(sgg_code as varchar) as sgg_code,
        cast(admin_dong_name as varchar) as admin_dong_name,
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(legal_dong_name as varchar) as legal_dong_name,
        cast(legal_dong_code as varchar) as legal_dong_code
    from {{ source('commerce_bronze', 'ref_admin_dong') }}
    where sido_name = '서울특별시'
),

ref_gu as (
    select sgg_name, min(sgg_code) as sgg_code
    from ref_dong
    group by 1
),

-- (구, 법정동) 1행: 법정동코드 + 대응 행정동 1개.
-- 법정동 1개가 행정동 여러 개에 걸치면(예: 역삼동→역삼1·2동) 정확한 배정은 번지 없이는 불가 —
-- **결정적 근사**: 숫자·구분점 제거한 행정동명이 법정동명과 같은 것 우선, 다음 행정동코드 오름차순.
ref_legal as (
    select sgg_name, legal_dong_name, legal_dong_code, admin_dong_name, admin_dong_code
    from (
        select
            *,
            row_number() over (
                partition by sgg_name, legal_dong_name
                order by
                    case when regexp_replace(admin_dong_name, '[0-9·.]+', '') = legal_dong_name
                         then 0 else 1 end,
                    admin_dong_code
            ) as rn
        from ref_dong
    )
    where rn = 1
),

-- (구, 행정동) 1행: 행정동코드 + 대응 법정동 1개(행정동은 법정동 여러 개를 관할 — 동일 근사 규칙).
ref_admin as (
    select sgg_name, admin_dong_name, admin_dong_code, legal_dong_name, legal_dong_code
    from (
        select
            *,
            row_number() over (
                partition by sgg_name, admin_dong_name
                order by
                    case when legal_dong_name = regexp_replace(admin_dong_name, '[0-9·.]+', '')
                         then 0 else 1 end,
                    legal_dong_code
            ) as rn
        from ref_dong
    )
    where rn = 1
),

-- 동 분류·매핑: dong_raw 가 법정동명에 맞으면 legal(우선), 아니면 행정동명에 맞으면 admin.
-- 한쪽이 확정되면 반대쪽은 참조 매핑으로 채운다(legal↔admin 상호 보완).
dong as (
    select
        n.*,
        rg.sgg_code as gu_code,
        coalesce(rl.legal_dong_name, ra.legal_dong_name) as legal_dong,
        coalesce(rl.legal_dong_code, ra.legal_dong_code) as legal_code,
        coalesce(ra.admin_dong_name, rl.admin_dong_name) as admin_dong,
        coalesce(ra.admin_dong_code, rl.admin_dong_code) as admin_dong_code
    from dong_token as n
    left join ref_gu as rg
        on n.gu = rg.sgg_name
    left join ref_legal as rl
        on n.gu = rl.sgg_name and n.dong_raw = rl.legal_dong_name
    -- 법정동 매치가 없을 때만 행정동으로 분류(법정동 우선 — 지번 표기 원칙)
    left join ref_admin as ra
        on rl.legal_dong_name is null
        and n.gu = ra.sgg_name and n.dong_raw = ra.admin_dong_name
),

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
    from dong
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
),

keyed as (
    select
        *,
        -- geocode 조인 키(§4.5) — Step 8 에서 bronze_geocode_address 와 조인. 도로명/지번 2종.
        case when road_address_norm is not null
             then lower(to_hex(sha256(cast(road_address_norm as varbinary)))) end as address_key_road,
        case when jibun_address_norm is not null
             then lower(to_hex(sha256(cast(jibun_address_norm as varbinary)))) end as address_key_jibun,
        -- 전순서 버전 정렬키: UPDATEDT → LASTMODTS → 관측일 → 수집시각 → content_hash(항상 tie-break).
        -- **1순위 폴백**: UPDATEDT(updatedt_ts) 결측 시 LASTMODTS(lastmodts_ts, 최종수정시점)로 정렬,
        -- 그마저 없으면 epoch(가장 오래된 것). → updatedt 없는 행이 무조건 최하위로 밀리지 않게 함.
        -- (실측 현재 데이터는 updatedt_ts 100% 존재 → 폴백은 방어적; 시각 해석엔 *_ts 를 쓸 것 — 정렬 전용.)
        coalesce(updatedt_ts, lastmodts_ts, timestamp '1970-01-01 00:00:00') as updatedt_sort,
        coalesce(lastmodts_ts, timestamp '1970-01-01 00:00:00') as lastmodts_sort
    from geo
),

affected_keys as (
    select
        distinct dataset, opnsfteamcode, mgtno
    from keyed
),

projected_new as (
    select
        dataset,
        opnsfteamcode,
        mgtno,
        record_json,
        bplcnm,
        trdstategbn,
        trdstatenm,
        dtlstategbn,
        dtlstatenm,
        apvpermymd,
        dcbymd,
        sitetel,
        road_address,
        jibun_address,
        jibun_address_source,
        road_address_norm,
        jibun_address_norm,
        gu,
        gu_code,
        legal_dong,
        legal_code,
        admin_dong,
        admin_dong_code,
        address_key_road,
        address_key_jibun,
        source_coord_x,
        source_coord_y,
        latitude,
        longitude,
        content_hash,
        updatedt,
        updatedt_ts,
        updatedt_sort,
        lastmodts,
        lastmodts_ts,
        lastmodts_sort,
        observed_date,
        collected_at,
        bronze_run_id,
        dag_run_id,
        raw_object_key,
        load_date,
        'new' as _silver_source
    from keyed
),

prior_tail as (
    {% if is_incremental() %}
    -- 새 batch 의 첫 행이 직전 silver 행과 같은 content_hash 인지 판정하기 위한
    -- key별 최신 1행만 붙인다. 전체 기존 history 를 재스캔하지 않는다.
    select
        dataset,
        opnsfteamcode,
        mgtno,
        record_json,
        bplcnm,
        trdstategbn,
        trdstatenm,
        dtlstategbn,
        dtlstatenm,
        apvpermymd,
        dcbymd,
        sitetel,
        road_address,
        jibun_address,
        jibun_address_source,
        road_address_norm,
        jibun_address_norm,
        gu,
        gu_code,
        legal_dong,
        legal_code,
        admin_dong,
        admin_dong_code,
        address_key_road,
        address_key_jibun,
        source_coord_x,
        source_coord_y,
        latitude,
        longitude,
        content_hash,
        updatedt,
        updatedt_ts,
        updatedt_sort,
        lastmodts,
        lastmodts_ts,
        lastmodts_sort,
        observed_date,
        collected_at,
        bronze_run_id,
        dag_run_id,
        raw_object_key,
        load_date,
        'prior' as _silver_source
    from (
        select
            h.*,
            row_number() over (
                partition by h.dataset, h.opnsfteamcode, h.mgtno
                order by h.updatedt_sort desc, h.lastmodts_sort desc,
                         h.observed_date desc, h.collected_at desc, h.content_hash desc
            ) as rn
        from {{ this }} as h
        inner join affected_keys as k
            on h.dataset = k.dataset
            and h.opnsfteamcode = k.opnsfteamcode
            and h.mgtno = k.mgtno
    )
    where rn = 1
    {% else %}
    select *
    from projected_new
    where false
    {% endif %}
),

ordered as (
    select
        *,
        lag(content_hash) over (
            partition by dataset, opnsfteamcode, mgtno
            order by updatedt_sort, lastmodts_sort, observed_date, collected_at, content_hash
        ) as prev_content_hash
    from (
        select * from prior_tail
        union all
        select * from projected_new
    )
),

-- 연속(인접) 중복만 제거 → diff 재유입/reconcile 재방출은 걸러내고 정당한 원복(A→B→A)은 보존.
-- 동일 content 재방출은 UPDATEDT/LASTMODTS 도 동일(해시가 두 필드를 포함)이라 항상 인접 정렬된다.
deduped as (
    select *
    from ordered
    where _silver_source = 'new'
      and (prev_content_hash is null or prev_content_hash <> content_hash)
)

select
    dataset,
    opnsfteamcode,
    mgtno,
    record_json,
    bplcnm,
    trdstategbn,
    trdstatenm,
    dtlstategbn,
    dtlstatenm,
    apvpermymd,
    dcbymd,
    sitetel,
    road_address,
    jibun_address,
    jibun_address_source,
    road_address_norm,
    jibun_address_norm,
    gu,
    gu_code,
    legal_dong,
    legal_code,
    admin_dong,
    admin_dong_code,
    address_key_road,
    address_key_jibun,
    source_coord_x,
    source_coord_y,
    latitude,
    longitude,
    content_hash,
    updatedt,
    updatedt_ts,
    updatedt_sort,
    lastmodts,
    lastmodts_ts,
    lastmodts_sort,
    observed_date,
    collected_at,
    bronze_run_id,
    dag_run_id,
    raw_object_key,
    load_date
from deduped
