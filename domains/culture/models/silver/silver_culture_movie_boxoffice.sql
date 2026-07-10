-- silver: KOBIS 일별 영화 박스오피스(전국+서울 한정) fact. top10 스냅샷.
-- 그레인 = (region, boxoffice_date, rank). boxoffice_date = load_date − 1일
-- (targetDt가 record_json에 없어 로더 계약[ASAC-DAG#197]에서 복원).
-- KOPIS 예매상황판 boxoffice(공연 예매)와 다른 축 = 영화 관객수. 공간축 시도(서울)까지라 면제.
-- region: 'nation'(전국) / 'seoul'(서울 한정 wideAreaCd=0105001). 두 랭킹은 서로 다른 영화 집합.

with unioned as (
    select 'nation' as region, record_json, ingest_ts,
           {{ culture_lineage('kobis') }}
    from {{ source('culture_bronze', 'bronze_kobis_boxoffice_nation') }}
    union all
    select 'seoul' as region, record_json, ingest_ts,
           {{ culture_lineage('kobis') }}
    from {{ source('culture_bronze', 'bronze_kobis_boxoffice_seoul') }}
),

typed as (
    select
        region,
        cast(json_extract_scalar(record_json, '$.rank') as integer)           as rank,
        json_extract_scalar(record_json, '$.movieCd')                         as movie_cd,
        nullif(trim(json_extract_scalar(record_json, '$.movieNm')), '')       as movie_nm,
        try(cast(json_extract_scalar(record_json, '$.openDt') as date))       as open_date,
        try(cast(json_extract_scalar(record_json, '$.audiCnt') as bigint))    as audience_count,
        try(cast(json_extract_scalar(record_json, '$.audiAcc') as bigint))    as audience_acc,
        try(cast(json_extract_scalar(record_json, '$.salesAmt') as bigint))   as sales_amount,
        try(cast(json_extract_scalar(record_json, '$.salesShare') as double)) as sales_share,
        try(cast(json_extract_scalar(record_json, '$.scrnCnt') as integer))   as screen_count,
        try(cast(json_extract_scalar(record_json, '$.showCnt') as integer))   as show_count,
        cast(load_date as date) - interval '1' day                            as boxoffice_date,
        ingest_ts, source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date
    from unioned
    where json_extract_scalar(record_json, '$.movieCd') is not null
),

latest as (
    select * from (
        select *, row_number() over (
            partition by region, boxoffice_date, rank
            order by {{ culture_dedup_order() }}
        ) as rn
        from typed
    ) where rn = 1
)

select
    region,
    boxoffice_date,
    rank,
    movie_cd,
    movie_nm,
    open_date,
    audience_count,
    audience_acc,
    sales_amount,
    sales_share,
    screen_count,
    show_count,
    cast(boxoffice_date as timestamp(6)) as event_at,
    source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date
from latest
