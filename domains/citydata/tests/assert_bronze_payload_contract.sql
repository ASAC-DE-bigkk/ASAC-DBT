-- 계약(contract) 테스트: 최근 bronze payload가 기대한 핵심 필드를 갖는지 검증한다.
--
-- schema-on-read라 API가 필드명을 바꿔도 bronze는 통과한다(payload 통째 저장). 그러면
-- silver의 json_extract가 조용히 전부 null을 만든다. 이 테스트는 최근 1시간 bronze에서
-- AREA_NM / PPLTN_TIME이 파싱되지 않는 행을 찾아 **API 드리프트를 조기에** 드러낸다.
-- (반환 행이 있으면 = 계약 위반 → 테스트 실패)

select
    request_id,
    collected_at,
    json_extract_scalar(payload, '$.AREA_NM')    as area_nm,
    json_extract_scalar(payload, '$.PPLTN_TIME') as ppltn_time
from {{ source('bronze', 'bronze_seoul_ppltn') }}
where collected_at >= current_timestamp - interval '1' hour
    and (
        json_extract_scalar(payload, '$.AREA_NM') is null
        or json_extract_scalar(payload, '$.PPLTN_TIME') is null
    )
