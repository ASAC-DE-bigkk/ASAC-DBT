{#-
  LOCALDATA v1(구형)·v2(신형) 컬럼 표준 대응 매크로.
  같은 개념이 표준마다 다른 이름으로 온다(예: MGTNO=MNG_NO, TRDSTATEGBN=SALS_STTS_CD).
  record_json 에서 **정본(v1) 우선, 없으면 v2 별칭**으로 추출해 silver 를 하나의 스키마로 정규화한다.
  원본 record_json 은 그대로 silver 에 보존(비공통 필드 포함) — gold 가 API별로 table화.
  결측 규약: 원본 '' → null (nullif+trim).
-#}
{% macro lf(v1, v2=none) -%}
{%- if v2 -%}
coalesce(nullif(trim(json_extract_scalar(record_json, '$.{{ v1 }}')), ''), nullif(trim(json_extract_scalar(record_json, '$.{{ v2 }}')), ''))
{%- else -%}
nullif(trim(json_extract_scalar(record_json, '$.{{ v1 }}')), '')
{%- endif -%}
{%- endmacro %}
