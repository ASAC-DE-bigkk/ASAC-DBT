-- dim_transit_bus_route_tier — 버스 노선의 수집 티어 분류 (#286, 수집 정책은 ASAC-DAG #440·#449).
--
-- 한 행 = 아카이브 개시일 이후 관측된 버스 노선 1개. grain: bus_route_id.
--
-- ── 왜 '수집 런 시각'으로 판정하는가 ────────────────────────────────────
--   티어의 원천 정의(routeType: 3 간선·6 광역 = tier1)는 R2 reference
--   (reference/transit/bus_routes/latest.json)에만 있고 웨어하우스엔 적재되지 않는다.
--   그래서 수집 결과로 역산해야 하는데, **수집 정책을 직접 관측하는 신호**를 쓴다:
--
--     tier2 는 BUS_TIER2_HOURS(09·19시) 의 **정시 런**에만 실린다(분<10).
--     tier1 은 dense 시간대의 :10·:20·:30·:40·:50 런에도 매번 실린다.
--     → dag_run_id 의 분(minute)이 00 이 아닌 런에 등장했다면 그 노선은 tier1 이다.
--
--   앞서 쓰던 '관측 시간대 종류 수 >= N' 휴리스틱은 폐기했다: 수집 창 크기에 종속해
--   정책이 바뀔 때마다 임계를 다시 잡아야 했고, 무엇보다 티어링이 실효하지 않던
--   구간(전 노선이 매 런 수집)에서는 신호 자체가 없어 627/682 노선을 tier1 로
--   오분류했다(2026-07-20 실측). 런 시각 신호는 그런 구간과 정상 구간을 구분한다 —
--   전 노선이 매 런 수집되면 모두 tier1 로 나오지만, 그건 실제로 "모두 tier1 처럼
--   촘촘히 수집됐다"는 사실을 정확히 반영한 것이라 파생(*_t1)의 의미가 깨지지 않는다.
--
-- ── 관측 창 = 아카이브 개시일 이후 ──────────────────────────────────────
--   정책 전환 전 구간을 섞으면 그때의 무차별 수집이 분류를 오염시키므로,
--   var transit_archive_start_at 이후만 본다(아카이브 6종과 같은 하한).
--   개시 직후 몇 분간은 :00 런밖에 없어 전 노선이 tier2 로 나올 수 있다 —
--   첫 dense 런(:10)이 돌면 즉시 정상화되고, 그 사이 버킷의 tier 는 null/2 로
--   스탬프되어 *_t1 집계에서만 빠진다(안전한 방향의 오류).
--
-- ── 소비 계약 ───────────────────────────────────────────────────────────
--   기반 아카이브 gold 가 빌드 시점에 조인해 tier 를 스탬프한다(#286 원칙 ①).
--   시간대 비교 지표(리듬·프로파일)는 tier=1 만 필터(원칙 ②). 미등재 노선은
--   조인 miss → tier null → tier1 집계에서 제외.
--
-- ── 매 빌드 전체 재계산(table) ──────────────────────────────────────────
--   분류 창이 슬라이딩이라 증분이 무의미하고, 수집 정책 변경(env 조정)에 자동 추종한다.
--   reference(routeType)를 웨어하우스로 적재하는 정공법이 생기면 이 모델은 그 조인으로
--   대체하고, 이 관측 기반 판정은 검증용으로만 남긴다.

{{ config(materialized='table') }}

with observed as (
    select
        bus_route_id,
        dag_run_id,
        event_at,
        -- Airflow run_id 예: 'scheduled__2026-07-21T00:10:00+00:00' → 분 '10'.
        -- 수동 런(manual__…)은 임의 시각이라 티어 신호로 쓸 수 없어 제외한다.
        case
            when dag_run_id like 'scheduled\_\_%' escape '\'
            then regexp_extract(dag_run_id, 'T\d{2}:(\d{2}):', 1)
        end as run_minute
    from {{ ref('silver_transit_bus_position') }}
    where event_at >= timestamp '{{ var("transit_archive_start_at") }}'
)

select
    bus_route_id,
    -- 정시(:00)가 아닌 스케줄 런에 실렸다 = dense 수집 대상 = tier1.
    count(case when run_minute is not null and run_minute <> '00' then 1 end) as dense_run_obs_cnt,
    case
        when count(case when run_minute is not null and run_minute <> '00' then 1 end) > 0
        then 1 else 2
    end as tier,
    count(distinct hour(event_at)) as obs_hour_kind_cnt,   -- 진단용(분류에는 미사용)
    count(*) as obs_cnt,
    max(event_at) as last_event_at
from observed
group by bus_route_id
