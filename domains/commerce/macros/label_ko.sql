{#-
  gold 서빙 한글 라벨 매크로 — code/영문 값 → 한글(사용자 요청 2026-07-16).
  저·중카디널리티는 CASE(join 불필요·전 모델 일관). 고카디널리티(dataset 152)는
  commerce_dataset_taxonomy 시드의 name_ko(=dataset_ko), 지역명(gu/admin_dong/legal_dong)은
  silver_license_entity 원천을 쓴다. 정본: run_report.py MAJOR_KO/CATEGORY_KO/SUB_KO, PROJECT.md §1.
-#}

{% macro label_major_ko(col) -%}
case {{ col }} when 'health' then '보건' when 'culture' then '문화'
     when 'industry' then '산업' when 'environment' then '환경' else {{ col }} end
{%- endmacro %}

{% macro label_category_ko(col) -%}
case {{ col }} when 'food' then '식품' when 'livestock' then '축산'
     when 'health_medical' then '의료' when 'pharmacy' then '약국' when 'animal' then '동물'
     when 'hygiene_beauty' then '위생·미용' when 'optical_dental' then '안경·치과' when 'lodging' then '숙박'
     when 'culture' then '문화' when 'industry' then '산업' when 'environment' then '환경' else {{ col }} end
{%- endmacro %}

{% macro label_event_type_ko(col) -%}
case {{ col }} when 'opened' then '개업' when 'closed' then '폐업' else {{ col }} end
{%- endmacro %}

{% macro label_age_band_ko(col) -%}
case {{ col }} when '0_lt1y' then '1년 미만' when '1_1to3y' then '1~3년' when '2_3to5y' then '3~5년'
     when '3_5to10y' then '5~10년' when '4_10to20y' then '10~20년' when '5_ge20y' then '20년+' else {{ col }} end
{%- endmacro %}

