# DB/gold — 뷰 명세 (조회 인터페이스)

실질 조회는 **의미 단위 view**로 한다 — 물리 테이블(supertype/detail 분리)은 노출하지 않고, **도메인
view + API view**를 current/history 두 형태로 전부 제공한다. 목록·정의 근거:
[../../gold-catalog.csv](../../gold-catalog.csv) (`kind=view_*`).

## 1. 뷰 체계 (4종 × 카탈로그 기반 생성)

| 뷰 | 수 | grain | 정의 |
|---|---:|---|---|
| `commerce_v_<domain>` | 8 | (entity_seq) 현재 | entity ⋈ `<domain>_detail`(최신 버전) ⋈ dim(코드→이름 해석) |
| `commerce_v_<domain>_history` | 8 | (entity_seq, collected_at, content_hash) | entity_history ⋈ `<domain>_detail`(버전행) |
| `commerce_v_api_<short>` | 152 | (entity_seq) 현재 | 소속 detail 기준 — cluster 멤버=`where dataset='<short>'` 필터, single=1:1 |
| `commerce_v_api_<short>_history` | 152 | 버전 | 위와 동일, entity_history 기준 |

- **history 조인이 안전한 이유**: entity_history 와 detail 은 **같은 silver history 버전행**에서
  나오므로 `(entity_seq, collected_at, content_hash)` 로 1:1 정합한다.
- **생성 전략**: 320개 뷰를 손으로 만들지 않는다 — gold-catalog 를 dbt seed 로 올리고 jinja 루프로
  카탈로그 행마다 view 를 생성(카탈로그가 단일 소스, 수정=재생성).

## 2. 도메인 view 예 — commerce_v_food_sanitation_business (현재)

```sql
create or replace view commerce_v_food_sanitation_business as
select
    e.entity_seq, e.dataset, dd.name_ko as api_name,
    e.business_name, e.opened_at, e.closed_at,
    e.status_code, st.status_name,        -- 코드 + 이름(dim 해석) 둘 다 노출
    e.gu_code, e.admin_dong_code, e.legal_code,   -- ★ 위치 매핑 키(시군구·행정동) — 타 도메인 조인용
    r.gu_name, r.admin_dong_name, r.legal_dong_name,
    e.road_address, e.jibun_address, e.longitude, e.latitude,
    d.uptaenm, d.sntuptaenm, d.chaircnt, d.faciltotscp, d.wtrsplyfacilsenm,
    d.maneipcnt, d.wmeipcnt, d.homepage,  -- … payload(카탈로그 참조)
    e.updatedt, e.updatedt_ts,            -- ★ 업데이트 일자 — 시간 조건문 기준
    e.last_collected_at
from commerce_business_entity e
join commerce_food_sanitation_business_detail d
  on d.entity_seq = e.entity_seq
 and (d.collected_at, d.content_hash) = (            -- 최신 detail 버전
     select max(collected_at), max_by(content_hash, collected_at)
     from commerce_food_sanitation_business_detail
     where entity_seq = e.entity_seq)
left join commerce_dim_dataset dd on dd.dataset = e.dataset
left join commerce_dim_business_status st
  on st.fmt = dd.fmt and st.status_code = e.status_code
left join commerce_dim_region r on r.admin_dong_code = e.admin_dong_code;
```

> 이종 detail 을 한 view 로 합칠 때(예: 식품+숙박 통합 조회)는 사용자 예시의 **union all + 없는 컬럼
> null** 패턴을 그대로 쓴다 — 물리 테이블은 분리, 조회 인터페이스는 하나.

## 3. history view 예 — commerce_v_api_pharmacy_history (단독 API 이력)

```sql
create or replace view commerce_v_api_pharmacy_history as
select
    h.entity_seq, h.dataset, h.collected_at, h.content_hash,   -- 버전 키
    h.business_name, h.status_code, st.status_name, h.road_address,
    h.gu_code, h.admin_dong_code, h.legal_code,                -- 위치 매핑 키
    r.gu_name, r.admin_dong_name,
    h.updatedt, h.updatedt_ts,                                 -- 업데이트 일자(조건문 기준)
    d.pharmtrdar, d.asgnymd                                    -- pharmacy 고유 payload
from commerce_business_entity_history h
join commerce_pharmacy_detail d
  on d.entity_seq = h.entity_seq
 and d.collected_at = h.collected_at and d.content_hash = h.content_hash
left join commerce_dim_business_status st on st.fmt = 'v1' and st.status_code = h.status_code
left join commerce_dim_region r on r.admin_dong_code = h.admin_dong_code
where h.dataset = 'pharmacy';
-- 버전 순서 = collected_at desc (silver 암묵 버저닝과 동일). 값이 바뀔 때마다 행이 하나씩 —
-- "언제 무엇이 바뀌었나"를 이 view 하나로 추적한다.
```

## 4. 소비 규약

- **일반 분석/서빙 = view 만** 조회(도메인 우선, 필요 시 API view). detail 물리 테이블 직접 조회는
  파이프라인 내부용.
- 현재 상태 = `commerce_v_<domain>` / 변경 추적·감사 = `_history`.
- 코드 값(상태·행정동·API)은 view 가 dim 으로 해석해 주되, **코드 컬럼도 항상 함께 노출**한다:
  - **위치 매핑(크로스도메인)**: `gu_code`(시군구)·`admin_dong_code` 로 타 도메인 데이터와 조인
    (이름 아닌 **코드 기준** — 개편/표기 변형에 안전). 마스킹 주소는 동 코드 null → 조인 시 허용 설계.
  - **시간 조건**: `updatedt`(원천 업데이트 일자, `updatedt_ts` 파싱본) 기준으로 조건문을 건다.
    예) `where updatedt_ts >= date '2026-01-01'` · 최근 변경분 = `updatedt_ts >= now() - interval '7' day`.
    (수집시각 `collected_at` 은 파이프라인 계보용 — 업무 시간축은 updatedt.)
