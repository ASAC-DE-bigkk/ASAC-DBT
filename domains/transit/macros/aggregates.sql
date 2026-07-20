{#
  aggregates.sql — transit 집계 표현식 헬퍼 (#291 후속 리팩터)

  같은 의미의 표현식이 모델마다 복붙되면, 규칙이 바뀔 때(예: 원천 코드 체계 변경)
  일부만 고쳐져 같은 지표가 모델별로 달라진다. 특히 아카이브 계열은
  full_refresh=false 라 그렇게 어긋난 이력이 영구 고정된다 — 한 곳에서만 정의한다.
#}

{#
  transit_weighted_avg — 관측수 가중 평균.

    sum(val * weight) / sum(weight)  단, val 이 null 인 행의 weight 는 분모에서도 뺀다.

  단순 avg() 를 쓰면 15분/30분 버킷을 시간·요일로 접을 때 관측이 적은 버킷이
  관측 많은 버킷과 같은 무게를 갖는다(과대대표). 분모에서 null 행 weight 를 빼지
  않으면 값이 있는 관측만으로 계산해야 할 평균이 아래로 눌린다.
  weight 합이 0(전부 null)이면 null 을 돌려준다 — 0으로 나누지 않는다.

  사용처: dong_rhythm(2), x_weather(2), bus_route_comfort(3).
#}
{% macro transit_weighted_avg(val, weight) -%}
case when sum(case when {{ val }} is not null then {{ weight }} end) > 0
     then sum({{ val }} * {{ weight }})
          / sum(case when {{ val }} is not null then {{ weight }} end)
end
{%- endmacro %}

{#
  transit_bus_congestion_avg — 버스 혼잡도 평균(0='정보없음' 제외).

  원천 congetion 은 0/3/4/5 로 오는데 0 은 '값 없음'이지 '가장 안 붐빔'이 아니다(#67).
  포함하면 평균이 실제보다 낮게 눌린다. extra_predicate 로 tier 필터 등을 덧붙인다.

  사용처: dong_15min(2 — 전 티어·tier1), route_section_30min(1), dong_hourly(1).
#}
{% macro transit_bus_congestion_avg(col='congestion', extra_predicate='') -%}
avg(case when {{ col }} is not null and {{ col }} <> 0
         {%- if extra_predicate %} and {{ extra_predicate }}{% endif %}
         then cast({{ col }} as double) end)
{%- endmacro %}

{#
  transit_parking_occ_ratio — 주차 점유율(현재대수/총면수).

  총면수가 null·0 인 관측은 비율을 정의할 수 없어 null 로 흘린다(평균에서 자동 제외).
  ※ 이 두 컬럼은 원천이 소수 문자열("806.0")이라 정수 캐스트가 전건 실패했던 이력이
    있다 — silver 의 transit_int_from_numeric_str(#72)가 해소했고, 회귀는
    assert_silver_transit_parking_capacity_not_all_null 이 감시한다.

  사용처: dong_15min(1), parking_lot_15min(1), dong_hourly(1).
#}
{% macro transit_parking_occ_ratio(cnt='now_prk_vhcl_cnt', capacity='total_capacity') -%}
case
    when {{ cnt }} is not null
     and {{ capacity }} is not null
     and {{ capacity }} > 0
    then cast({{ cnt }} as double) / {{ capacity }}
end
{%- endmacro %}
