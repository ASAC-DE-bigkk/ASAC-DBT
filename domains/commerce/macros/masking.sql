{#- 마스킹 주소(도로명/지번에 '*') 행은 동 단위 값을 null 처리 — §19.1 masked_address 규칙.
    gu/sgg 파싱은 마스킹 토큰에 의존하지 않아 유지, 동 단위(legal/admin)만 무효화한다. -#}
{% macro null_if_masked_address(expr) -%}
case
    when coalesce(road_address, '') like '%*%' or coalesce(jibun_address, '') like '%*%'
        then null
    else {{ expr }}
end
{%- endmacro %}
