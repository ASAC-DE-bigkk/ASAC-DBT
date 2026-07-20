{#
  buckets.sql — transit 시간 버킷 헬퍼 (#286)

  transit_time_bucket — event_at(KST 벽시계)을 N분 버킷 시작 시각으로 절삭한다.
    date_trunc 는 분 단위 임의 간격을 지원하지 않아 minute 나머지를 빼는 방식.
    기반 아카이브 gold 의 grain 축(15분: 지하철 3분·주차 5분 대응, 30분: 버스
    티어링 #440 대응)이 모두 이 매크로를 거쳐야 버킷 경계 정의가 한 곳에 남는다.
    '_at' 계약(KST 벽시계 유지): 입력이 KST 벽시계이므로 절삭 결과도 KST 벽시계.
#}
{% macro transit_time_bucket(ts, minutes) -%}
date_add('minute', -(minute({{ ts }}) % {{ minutes }}), date_trunc('minute', {{ ts }}))
{%- endmacro %}
