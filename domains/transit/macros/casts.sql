{#
  casts.sql — transit 도메인 수치 캐스트 헬퍼

  transit_int_from_numeric_str — 정수를 담은 문자열을 integer 로 캐스트하되,
    원천이 소수 표기("806.0", "1260.0")인 경우도 수용한다.

    배경(#72, 실측): 주차 원천 NOW_PRK_VHCL_CNT·TPKCT(및 마스터 tpkct)가 정수값을
    소수 문자열로 내보낸다("18.0", "1.0"). try(cast(x as integer)) 는 소수점 문자열을
    파싱하지 못해 전건 실패 → 컬럼이 조용히 전건 null 이 됐다(slv 46,107행·dim 850행).

    double 경유(cast(x as double) → integer)면 "806.0"·"806" 둘 다 수용한다.
    try() 래핑은 유지 — 비수치/공란은 예전처럼 null 로 흡수(전건 null 회귀는 별도
    singular 테스트 assert_slv_transit_parking_capacity_not_all_null 이 감시).
    소수부는 integer 캐스트가 반올림하나 대상 필드는 실측상 정수값(.0)이라 손실 없음.

    같은 위험은 parking 3개 캐스트에 국한됨을 실증(subway barvlDt/lstcarAt/trnsitCo,
    bus sectOrd/congetion/stopFlag/isFullFlag/islastyn 은 소수점 0건·캐스트 실패 0건).
#}
{% macro transit_int_from_numeric_str(expr) -%}
try(cast(cast({{ expr }} as double) as integer))
{%- endmacro %}
