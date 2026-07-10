# culture quality_status + 미래 커버리지 계측 — 설계 (ASAC-DBT #111)

> **목적**: "소스가 갱신을 멈춰도 초록" 갭 해소의 실제 착지점. 조사 결과 원래 이슈가
> 상정한 event-time(등록/수정 시각)이 culture 데이터에 **존재하지 않아**(silver 12개 전수
> 확인, 등록일/수정일 필드 0건), 두 축으로 재정의한다:
> ① **quality_status** — 행별 공간축 정밀도 표식(주력), ② **미래 커버리지 계측** — freshness
> 대체(경량). 2026-07-10 설계. dbt-only, 인프라 게이트 없음.

## 0. 조사 요약 (설계 근거)

- **event-time 부재**: silver 12개 어디도 record_json에서 등록/수정 타임스탬프를 뽑지 않음.
  유일한 데이터 내부 시각 = 행사 시작/종료일(기간 fact) 또는 load_date(스냅샷).
- **소스 3분류**: 판정 불필요 3개(reservation·boxoffice·movie_boxoffice — load_date=신선도,
  기존 collected_at freshness가 커버) / proxy만 가능 6개(기간 fact — max(event_start_date)) /
  판정 불가 3개(sports seed·facility·space dim).
- **transit(#66) 선례는 구조만 이식**: transit event_at은 실시간 관측 시각이라 "미래 = 이상치
  → 차단"이 핵심. culture event_at은 행사 시작일이라 **미래가 정상** → 하드 게이트 금지, warn 계측만.
- **quality_status 선례 = traffic `source_location_quality`**: enum + schema.yml accepted_values
  + gold 카운트 집계. culture의 좌표→행정동 3단 폴백에 이식.

## 1. quality_status 컬럼 (주력)

### 값 체계 (geo 정밀도 3치)

최종 공간축 컬럼의 null 여부로 **순수 파생** — 새 조인·계산 없음:

```sql
case
  when admin_dong_code is not null then 'dong_precise'  -- 좌표 point-in-polygon 성공, 행정동까지
  when gu_code is not null          then 'gu_only'      -- 좌표 없어 구 레벨만(admin_dong null), 근사
  else                                   'unmatched'    -- 구도 미확정
end as quality_status
```

의미론: 기존 폴백 사슬 `coalesce(cd.gu_code[좌표→dim], cg.gu_code[라벨→dim], d.coord_gu_code
[boundary])` + `admin_dong_code`(좌표 point-in-polygon 산출)의 **결과 등급**을 노출. 값을
바꾸지 않고 "어느 정밀도로 채워졌나"만 표식한다(#48 오배정 계측과 같은 "계측 전용" 철학).

### 적용 범위 — 공간축 silver 10개

event · performance · festival · exhibition · sejong · kcisa_event · reservation · facility ·
space · sports_event. **제외 2개**: boxoffice · movie_boxoffice (공간축 면제 — area=시도뿐,
admin_dong_code/gu_code 컬럼 자체가 없음).

### 공통 매크로 (DRY)

`culture_axes.sql`에 매크로 추가 — 폴백 로직이 이미 `culture_admin_canon()` 한 곳에 모여
있으니 품질 표식도 같은 위치:

```sql
{% macro culture_quality_status(dong_col='admin_dong_code', gu_col='gu_code') -%}
case
  when {{ dong_col }} is not null then 'dong_precise'
  when {{ gu_col }}   is not null then 'gu_only'
  else                                'unmatched'
end
{%- endmacro %}
```

각 silver 최종 select에 `{{ culture_quality_status() }} as quality_status` 한 줄.
파라미터는 컬럼명이 다른 모델 대비(기본값이 표준명이라 대부분 인자 없이 호출).

### 계약

schema.yml 10개 모델에 (traffic 선례 그대로):
```yaml
- name: quality_status
  tests:
    - not_null
    - accepted_values: {values: [dong_precise, gu_only, unmatched]}
```

## 2. gold 전파

silver quality_status를 gold 집계로 롤업(traffic `gold_traffic_incident_summary` 선례).
gold별 그레인 특성에 맞춰:

| gold | 그레인 | 전파 방식 |
|---|---|---|
| `gold_culture_location_daily` | gu_code × event_date | **품질 분해 카운트 추가**: `dong_precise_count`(활동 중 동까지 정밀한 수). unmatched는 gu_code null이라 이 gold(gu_code 그레인)에 애초에 없음 → dong_precise vs gu_only 2분해 |
| `gold_culture_reservation_daily` | gu_code × snapshot_date | 동일 — `dong_precise_count` 추가 |
| `gold_culture_activity_by_dong` | admin_dong_code × event_date | **전파 아님, 특성 문서화**: admin_dong_code 그레인이라 정의상 dong_precise 활동만 포함. gu_only 활동은 이 gold에서 누락됨(설계 주석 + README 주의점에 명시) |
| `gold_culture_sports_schedule` | 경기 1행 | silver quality_status **그대로 노출**(집계 아님) |
| boxoffice·movie_boxoffice daily | — | 공간축 면제, 대상 아님 |

`location_daily`의 카운트는 activity_type별 카운트와 같은 UNNEST 전개 결과에 조건 카운트
추가라 비용 무증가(같은 스캔).

## 3. 미래 커버리지 계측 (freshness 대체)

기간 fact 6개(event·performance·festival·exhibition·sejong·kcisa)에 **singular test 1개**
(severity=warn, 계측 전용 — "error 하드 게이트" 금지):

```sql
-- assert_culture_future_event_coverage.sql (warn)
-- 각 소스의 미래 행사 재고가 마르는지 감시 — 소스가 신규 공급을 멈추면
-- max(event_start_date)가 current_date 로 다가온다. 등록일 부재의 유일한 proxy.
{{ config(severity='warn') }}
with sources as (
  select 'event' as src, max(event_start_date) as max_start from {{ ref('silver_culture_event') }}
  union all select 'performance', max(event_start_date) from {{ ref('silver_culture_performance') }}
  union all select 'festival',    max(event_start_date) from {{ ref('silver_culture_festival') }}
  union all select 'exhibition',  max(event_start_date) from {{ ref('silver_culture_exhibition') }}
  union all select 'sejong',      max(event_start_date) from {{ ref('silver_culture_sejong') }}
  union all select 'kcisa',       max(event_start_date) from {{ ref('silver_culture_kcisa_event') }}
)
select src, max_start
from sources
where max_start < date_add('day', {{ var('culture_future_coverage_days', 14) }}, current_date)
```

- **임계 14일**: `var('culture_future_coverage_days', 14)`. 2주 뒤 행사가 하나도 없으면 =
  등록 정체 의심 신호(warn만, 파이프 안 막음).
- **한계 정직 문서화**: 이미 등록된 미래 행사가 재고로 남아있으면 신규 등록 정체를 못 잡는다
  (proxy의 원천적 한계). 진짜 event-time 신선도는 소스가 등록 시각을 주기 전엔 불가.
- reservation·boxoffice·movie_boxoffice(스냅샷)는 기존 collected_at freshness가 커버 → 대상 아님.

## 4. 테스트 · 검증

- **generic**: quality_status accepted_values × 10 모델 (schema.yml)
- **singular**: 미래 커버리지 warn 1개
- **dev 실측 게이트**: (a) 각 소스 quality_status 분포(dong_precise/gu_only/unmatched 비율) —
  facility 100% dong_precise 예상(좌표 100%), event는 혼합 예상. (b) 미래 커버리지 현황 —
  14일 임계에 걸리는 소스 유무 실측(현재 7월, 대부분 통과 예상). (c) gold 카운트 합이 silver
  분포와 정합.
- 전체 `dbt build` PASS (기존 계약 무회귀).

## 5. 범위 밖 (후속)

- event-time 진짜 신선도(등록/수정 시각) — 소스가 필드를 주기 전엔 불가. 새 소스 편입 시 재검토.
- WAP 발행 게이트(#258) — 관측 표준 수렴 팀 논의 소관, quality_status와 독립.
- quality_status의 silver 격리 테이블화 — 팀 관례상 in-place 표식이 표준(격리 테이블 없음).
