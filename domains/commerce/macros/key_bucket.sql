{#- 저메모리 seed 서브청크 — 대형 dataset(단일 스냅샷 run 이 노드 메모리를 넘길 때, 예: mail_order_sale
    934K)을 record_json 을 한 번에 다 읽지 못하는 노드에서도 빌드하도록 **싼(비-json) 컬럼 필터**로
    행을 K 버킷 분할한다. record_json 을 읽어야 하는 무거운 변환/출력을 버킷당 1/K 로 바운드한다.

    - history: `content_bucket`([b,K]) — bronze `content_hash`(비-json 컬럼) 해시로 분할. **같은
      content_hash(=동일 레코드) 는 같은 버킷** → adjacent-dedup 보존. 서로 다른 버전(다른 content_hash)이
      한 키에서 비연속으로 같은 값으로 되돌아오는 경우(A→B→A)만 이론적 손실인데, 실측(스냅샷은 키당
      content 유일) 0건 → 무손실. seed 완주 후 총행수를 목표치와 대조해 검증한다.
    - current: `key_bucket`([b,K]) — grain 키(opnsfteamcode|mgtno, history 컬럼)로 분할. **키의 전 버전이
      한 버킷** → latest-1-row(row_number) 정확. 컬럼 기반이라 json 파싱 없이 싸다.

    var 없으면 필터 미생성(동작·컴파일 SQL 불변 → compile diff 보존). chunked_run(seed)이 dataset 이
    배치 예산을 넘으면 history(content_bucket)·current(key_bucket)를 분리 단계로 사용. §6 rebuild-and-ops. -#}

{% macro content_bucket_filter(hash_col) -%}
{%- set cb = var('content_bucket', none) -%}
{%- if cb %}
        and mod(from_base(substr({{ hash_col }}, 1, 8), 16), {{ cb[1] | int }}) = {{ cb[0] | int }}
{%- endif -%}
{%- endmacro %}

{% macro key_bucket_filter(key_expr) -%}
{%- set kb = var('key_bucket', none) -%}
{%- if kb %}
        and mod(from_base(substr(to_hex(xxhash64(to_utf8({{ key_expr }}))), 1, 8), 16), {{ kb[1] | int }}) = {{ kb[0] | int }}
{%- endif -%}
{%- endmacro %}
