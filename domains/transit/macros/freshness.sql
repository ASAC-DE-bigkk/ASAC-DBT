{#
  freshness.sql — transit silver 신선도(상한) 게이트 (#66)

  배경(실측): subway_arrival 원천이 전일 막차 안내를 잔존시켜 event_at(KST 벽시계)이
  수집시각보다 미래인 행이 존재(예: ingested 11:40 KST 런에 event_at 23:59). 이대로
  gold(#67) 시간대 집계에 들어가면 오염되므로 silver 에서 상한 필터로 차단한다.
  하한은 두지 않는다(과거 수신은 정상 — 지연/재수신).

  event_at 은 KST 벽시계(tz 없는 timestamp), ingested_at 은 UTC timestamp 이므로
  asac_axes.utc_to_kst 로 ingested_at 을 KST 로 환산해 같은 시간대에서 비교한다.
  허용 오차(수집 파이프 클럭 스큐 감안)는 var transit_freshness_skew_minutes 한 곳
  (dbt_project.yml)에서만 정의 — 모델 3종과 감시 테스트가 이 매크로를 통해 동일 임계를
  공유한다(각 모델에 리터럴 중복 금지). var() 에 fallback 인자를 주지 않는다:
  var 이름이 바뀌거나 누락되면 조용히 구값으로 돌아가는 대신 컴파일이 실패해야 한다(fail fast).

  운영 주의 — 스큐 var 변경 시: 임계를 좁게 잘못 잡았다가 넓히는 경우, 그 사이 필터로
  드랍된 행 중 incremental lookback(-2h) 밖의 것은 자동 재유입되지 않는다.
  넓힌 뒤에는 silver 3종 `--full-refresh` 로 1회 재생성해야 소급 복구된다.
#}

{#
  transit_future_bound — event_at 이 이보다 크면 '미래(수집시각+스큐 초과)'로 간주하는 상한.
    = utc_to_kst(ingested_at) + skew.
#}
{% macro transit_future_bound(ingested_at_col) -%}
({{ asac_axes.utc_to_kst(ingested_at_col) }} + interval '{{ var("transit_freshness_skew_minutes") }}' minute)
{%- endmacro %}

{#
  transit_event_at_not_future — 모델 WHERE 용. silver 에 '남길' 행(미래가 아닌 행) 술어.
    event_at NULL 은 미래 여부를 판정할 수 없어 여기서 드랍하지 않고 보존한다.
    (파싱 실패는 event_at not_null 테스트가 별도로 감시 — 이 상한 필터가 그 신호를 가리지 않게.)
#}
{% macro transit_event_at_not_future(event_at_col, ingested_at_col) -%}
({{ event_at_col }} is null or {{ event_at_col }} <= {{ transit_future_bound(ingested_at_col) }})
{%- endmacro %}

{#
  transit_event_at_is_future — 감시 테스트에서 '미래 행'을 셀 때 사용.
  not_future 의 부정으로 정의해 상보 쌍의 수동 유지에 따른 드리프트를 차단한다.
    not(e is null or e <= bound): e NULL → not(true)=false, bound NULL → not(null)=null 로,
    수동 전개 (e is not null and e > bound) 와 3치 논리까지 동일(필터/count_if 에서 둘 다 미집계).
#}
{% macro transit_event_at_is_future(event_at_col, ingested_at_col) -%}
(not {{ transit_event_at_not_future(event_at_col, ingested_at_col) }})
{%- endmacro %}

{# ------------------------------------------------------------------------
  event_at 도출식 공유 (#66 리뷰): silver 모델과 감시 테스트가 '같은 식'을 재도록
  도출식을 한 곳에 정의한다. 인라인 중복이면 silver 도출식이 바뀔 때 모니터가
  다른 것을 재게 된다.
------------------------------------------------------------------------ #}

{# transit_subway_event_at — bronze_subway_arrival.raw(JSON) → event_at(recptnDt KST). #}
{% macro transit_subway_event_at(raw_col) -%}
{{ asac_axes.kst_at("json_extract_scalar(" ~ raw_col ~ ", '$.recptnDt')") }}
{%- endmacro %}

{# transit_parking_event_at — bronze_parking.raw(JSON) → event_at(NOW_PRK_VHCL_UPDT_TM KST). #}
{% macro transit_parking_event_at(raw_col) -%}
{{ asac_axes.kst_at("json_extract_scalar(" ~ raw_col ~ ", '$.NOW_PRK_VHCL_UPDT_TM')") }}
{%- endmacro %}

{#
  transit_bus_position_items — bronze_bus_position.raw(XML) → itemList 조각 배열(UNNEST 용).
  (?s): Trino 정규식의 '.' 는 기본적으로 개행에 매치되지 않는다. itemList 조각이
        개행을 포함하면 매치가 조용히 0건이 되므로 DOTALL 플래그로 개행을 포함시킨다.
#}
{% macro transit_bus_position_items(raw_col) -%}
regexp_extract_all({{ raw_col }}, '(?s)<itemList>(.*?)</itemList>')
{%- endmacro %}

{# transit_bus_data_tm — itemList 조각 → dataTm(yyyyMMddHHmmss 문자열). #}
{% macro transit_bus_data_tm(item_expr) -%}
regexp_extract({{ item_expr }}, '<dataTm>([^<]*)</dataTm>', 1)
{%- endmacro %}

{# transit_bus_event_at — dataTm 문자열 → event_at(KST). #}
{% macro transit_bus_event_at(data_tm_expr) -%}
{{ asac_axes.kst_at(data_tm_expr) }}
{%- endmacro %}
