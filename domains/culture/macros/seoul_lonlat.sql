{#
  좌표 정규화 매크로 — 데이터셋별 축이 달라(경도/위도 필드가 제각각) 호출부에서
  lon_raw·lat_raw를 명시 매핑해 넘긴다. WGS84 십진도 가정.
  - 서울범위 가드: lon 126.6~127.3 / lat 37.3~37.75 벗어나면 NULL
  - 0·빈값·비수치는 try(cast)에서 NULL → 가드에서도 NULL
  출력: `... as longitude, ... as latitude` (호출부에서 뒤에 콤마 추가)
#}
{% macro seoul_lonlat(lon_raw, lat_raw) %}
    case when try(cast({{ lon_raw }} as double)) between 126.6 and 127.3
         then try(cast({{ lon_raw }} as double)) end as longitude,
    case when try(cast({{ lat_raw }} as double)) between 37.3 and 37.75
         then try(cast({{ lat_raw }} as double)) end as latitude
{% endmacro %}
