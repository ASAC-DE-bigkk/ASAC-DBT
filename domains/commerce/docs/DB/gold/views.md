# DB/gold — 뷰 명세 (조회 인터페이스)

실질 조회는 **의미 단위 view**로 한다 — 물리 테이블(supertype/detail 분리)은 노출하지 않고, **도메인
view + API view**를 current/history 두 형태로 전부 제공한다. 목록·정의 근거:
[../../gold-catalog.csv](../../gold-catalog.csv) (`kind=view_*`).

## 1. 뷰 체계 (4종 × 카탈로그 기반 생성)

| 뷰 | 수 | grain | 정의 |
|---|---:|---|---|
| `gold_v_<domain>` | 8 | (entity_id) 현재 | entity ⋈ `<domain>_detail`(최신 버전) ⋈ dim(코드→이름 해석) |
| `gold_v_<domain>_history` | 8 | (entity_id, collected_at, content_hash) | entity_history ⋈ `<domain>_detail`(버전행) |
| `gold_v_api_<short>` | 152 | (entity_id) 현재 | 소속 detail 기준 — cluster 멤버=`where dataset='<short>'` 필터, single=1:1 |
| `gold_v_api_<short>_history` | 152 | 버전 | 위와 동일, entity_history 기준 |

- **history 조인이 안전한 이유**: entity_history 와 detail 은 **같은 silver history 버전행**에서
  나오므로 `(entity_id, collected_at, content_hash)` 로 1:1 정합한다.
- **생성 전략**: 320개 뷰를 손으로 만들지 않는다 — gold-catalog 를 dbt seed 로 올리고 jinja 루프로
  카탈로그 행마다 view 를 생성(카탈로그가 단일 소스, 수정=재생성).

## 2. 도메인 view 예 — gold_v_food_sanitation_business (현재)

```sql
create or replace view gold_v_food_sanitation_business as
select
    e.entity_id, e.dataset, dd.name_ko as api_name,
    e.business_name, e.opened_at, e.closed_at,
    st.status_name,                       -- 코드 → 이름 (dim 해석)
    r.gu_name, r.admin_dong_name, r.legal_dong_name,
    e.road_address, e.jibun_address, e.longitude, e.latitude,
    d.uptaenm, d.sntuptaenm, d.chaircnt, d.faciltotscp, d.wtrsplyfacilsenm,
    d.maneipcnt, d.wmeipcnt, d.homepage,  -- … payload(카탈로그 참조)
    e.last_collected_at
from gold_business_entity e
join gold_food_sanitation_business_detail d
  on d.entity_id = e.entity_id
 and (d.collected_at, d.content_hash) = (            -- 최신 detail 버전
     select max(collected_at), max_by(content_hash, collected_at)
     from gold_food_sanitation_business_detail
     where entity_id = e.entity_id)
left join gold_dim_dataset dd on dd.dataset = e.dataset
left join gold_dim_business_status st
  on st.fmt = dd.fmt and st.status_code = e.status_code
left join gold_dim_region r on r.admin_dong_code = e.admin_dong_code;
```

> 이종 detail 을 한 view 로 합칠 때(예: 식품+숙박 통합 조회)는 사용자 예시의 **union all + 없는 컬럼
> null** 패턴을 그대로 쓴다 — 물리 테이블은 분리, 조회 인터페이스는 하나.

## 3. history view 예 — gold_v_api_pharmacy_history (단독 API 이력)

```sql
create or replace view gold_v_api_pharmacy_history as
select
    h.entity_id, h.dataset, h.collected_at, h.content_hash,   -- 버전 키
    h.business_name, st.status_name, h.road_address,
    r.gu_name, r.admin_dong_name,
    d.pharmtrdar, d.asgnymd                                    -- pharmacy 고유 payload
from gold_business_entity_history h
join gold_pharmacy_detail d
  on d.entity_id = h.entity_id
 and d.collected_at = h.collected_at and d.content_hash = h.content_hash
left join gold_dim_business_status st on st.fmt = 'v1' and st.status_code = h.status_code
left join gold_dim_region r on r.admin_dong_code = h.admin_dong_code
where h.dataset = 'pharmacy';
-- 버전 순서 = collected_at desc (silver 암묵 버저닝과 동일). 값이 바뀔 때마다 행이 하나씩 —
-- "언제 무엇이 바뀌었나"를 이 view 하나로 추적한다.
```

## 4. 소비 규약

- **일반 분석/서빙 = view 만** 조회(도메인 우선, 필요 시 API view). detail 물리 테이블 직접 조회는
  파이프라인 내부용.
- 현재 상태 = `gold_v_<domain>` / 변경 추적·감사 = `_history`.
- 코드 값(상태·행정동·API)은 view 가 dim 으로 해석해 주므로 소비자는 이름 컬럼을 그대로 쓴다.
