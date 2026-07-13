{#- silver_license_history 산출 컬럼(단일 소스) — projected_new/prior_tail/최종 select 가 공유.
    union all 이 위치 기반이므로 목록이 갈라지면 무증상 오염 → 반드시 여기서만 수정한다.
    순서는 gold 적재(loader._HISTORY_SELECT)·기존 append 테이블(on_schema_change: fail)과의
    위치 정합이 걸려 있으므로 임의로 재정렬하지 말 것. -#}
{% macro silver_history_column_list() %}
{{ return([
    'dataset', 'opnsfteamcode', 'mgtno', 'record_json', 'bplcnm',
    'trdstategbn', 'trdstatenm', 'dtlstategbn', 'dtlstatenm',
    'apvpermymd', 'dcbymd', 'sitetel',
    'road_address', 'jibun_address', 'jibun_address_source',
    'road_address_norm', 'jibun_address_norm',
    'gu', 'gu_code', 'legal_dong', 'legal_code', 'admin_dong', 'admin_dong_code',
    'address_key_road', 'address_key_jibun',
    'source_coord_x', 'source_coord_y', 'latitude', 'longitude',
    'content_hash', 'updatedt', 'updatedt_ts', 'updatedt_sort',
    'lastmodts', 'lastmodts_ts', 'lastmodts_sort',
    'observed_date', 'collected_at', 'bronze_run_id', 'dag_run_id',
    'raw_object_key', 'load_date',
]) }}
{% endmacro %}
