# 주소·행정구역·좌표 보강 규약 — dbt/domains/commerce

silver 가 주소를 어떻게 보강·분해하고(지번 채움, 구/동 코드), 원천 X/Y 를 어떻게
WGS84 위경도로 변환하는지 정리한다. (조사·실측 근거: 2026-07-06, bronze 134만 행 실데이터.)

파이프라인 배선: ASAC-DAG `commerce_load_silver` —
`[enrich_admin_dong_ref, enrich_fill_jibun, ensure_silver_marker] → dbt run → notify_masked_address_summary → dbt test → mark_silver_done`.
보강 코드: `dags/domains/commerce/include/silver/{juso.py, enrich_tasks.py}`.

---

## 1. 지번주소 채움 (jibun_address / jibun_address_source)

원천 152종 중 일부(예: 숙박업 `lodging`)는 지번주소 필드명이 `SITEWHLADDR` 가 아니라
`LOTNO_ADDR` 다(실측: lodging 7,111행 중 7,103행이 LOTNO_ADDR 만 보유). 나머지 결측은
도로명주소로 Juso API 를 조회해 채운다(실측: 전 데이터셋 합계 유니크 도로명 ~450건).

**채움 우선순위** (첫 비결측 채택, `jibun_address_source` 에 계보 기록):

| 순위 | 소스 | jibun_address_source |
|---|---|---|
| 1 | 원천 `SITEWHLADDR` | `source` |
| 2 | 원천 `LOTNO_ADDR` (필드명 상이 업종군) | `lotno_addr` |
| 3 | Juso 보강 캐시(`bronze_address_enrichment`, status='filled') — `road_address_norm` 키 조인 | `juso_api` |
| — | 3계보 모두 없음 | null |

### Juso 보강 태스크 (enrich_fill_jibun)

- API: `https://business.juso.go.kr/addrlink/addrLinkApi.do` (resultType=json).
  승인키 env `JUSO_CONFM_KEY`(.env.commerce, 자동 마스킹). 참고문서:
  https://business.juso.go.kr/jst/jstRoadNmAddrApiSearch
- **정규화 래더**: 인허가 도로명주소는 상세·괄호 노이즈가 많아, 정규식 후보를 순서대로
  시도하고 첫 매치(totalCount≥1)에서 멈춘다 —
  `p1 괄호절단` → `p2 콤마(상세)절단` → `p3 도로명+번호 접두 추출` →
  `p4 '<구> <로> <번호>' 재조립` → `p5 시도 생략형`. 래더 개정 시 `LADDER_VERSION` +1
  → not_found 캐시가 새 래더로 자동 재시도된다.
- **감사 로그(요구 계약)**: 지번이 null 이었던 규모와 호출량은
  ① 태스크 로그의 `jibun_fill_run` 이벤트(단일 라인 JSON —
  `null_jibun_rows / distinct_addresses / cache_skipped / api_calls / filled / not_found / errors`),
  ② `bronze_address_enrichment` 행 단위(`pattern_id / attempts / api_calls / status`)로 남는다.
- **캐시(멱등·과호출 방지)**: filled 영구 스킵 · not_found 같은 래더판 스킵 · error 재시도.
  키 단위 delete-then-insert. 개발 캡: `JUSO_MAX_ADDRESSES`.
- Juso 응답의 `admCd` 는 **법정동코드 10자리** — enrichment 에 보존(검증용). silver 의
  동/코드 판정은 §2 참조 매핑으로 일원화한다.

---

## 2. 구/동 분해와 행정동↔법정동 매핑 (gu, gu_code, legal/admin_dong·code)

참조: `bronze_ref_admin_dong` — 행안부 행정동↔법정동 연계(원천은 전국 ~2.1만 행,
**서울만 적재** ~730행 — Iceberg INSERT 커밋 비용, `ADMIN_DONG_SIDO_FILTER` 로 조정)를
`raw/common/admin_dong/load_date=*/ingest_ts=*`(R2, 공용 수집물) 최신본으로 **전량 교체**
적재(enrich_admin_dong_ref). 코드는 문자열로 고정(자릿수 보존), `sgg_code` = 법정동코드 앞 5자리.
행정동코드와 법정동코드의 앞 5자리(시군구 코드)가 다르면 `admin_dong_sgg_prefix_mismatch`
이벤트를 **error** 레벨로 남기고 알림 인터페이스(`COMMERCE_NOTIFY_WEBHOOK_URL`)로 전달한다.

| 컬럼 | 파생 규칙 |
|---|---|
| `gu` | 주소 텍스트에서 `서울(?:특별시\|시)?\s*([가-힣]+?구)` 파싱(도로명 우선·지번 폴백). 구 `district` 를 rename |
| `gu_code` | 참조에서 `gu` 이름 매치 → 시군구 코드 5자리 |
| `dong` 토큰 | (채움 후) 지번주소에서 `서울…구\s*([가-힣]+\d*(?:동\|가))` — 지번 표기의 동은 원칙적으로 **법정동** |

**시도 접두 변형 대응**: 원천 주소는 `서울특별시`(표준, 공백) 외에 `서울시`·`서울`·**무공백
결합형**(`서울시노원구공릉1동`, `서울특별시마포구 공덕2동461`)이 섞여 있다. gu/동 regex 는
접두 `서울(?:특별시|시)?` + 공백 `\s*`(0개 이상)로 이들을 흡수하고, 구는 lazy `[가-힣]+?구`
(구로구구로동 같은 결합형에서 첫 '구'까지만), 동은 `[가-힣]+\d*(?:동|가)` 로 **번지 앞에서 정지**
(공덕2동461 → 공덕2동)한다. 비서울(경기도 등)·마스킹 주소(`당산동*가`)는 매치 안 됨 → null(정상).
| `legal_dong/legal_code` | 동 토큰이 (구, 법정동명)에 매치(**우선**) → 그 코드. 매치가 행정동뿐이면 행정동→법정동 매핑으로 보완 |
| `admin_dong/admin_dong_code` | 동 토큰이 행정동명에만 매치하면 그 코드. 법정동으로 확정된 행은 법정동→행정동 매핑으로 보완 |

**마스킹 주소 예외**: `road_address` 또는 `jibun_address` 에 `*` 가 포함된 행은 원천 주소가
마스킹된 것으로 보고 silver에서 동 토큰 추출과 법정동/행정동 매핑을 수행하지 않는다. `gu/gu_code`
수준 파싱은 유지할 수 있지만, `legal_dong/legal_code/admin_dong/admin_dong_code` 는 null 로 둔다.
`commerce_load_silver.notify_masked_address_summary` 는 이 조건의 발생 건수, 정산건수(점검 대상
전체 건수), 전체 대비 비율을 `warning` 레벨로 로그와 알림 인터페이스에 전달한다.

**다대다 주의(정직한 한계)**: 법정동 1개가 행정동 여러 개에 걸치고(예: 역삼동 → 역삼1·2동)
행정동 1개가 법정동 여러 개를 관할한다(예: 종로1.2.3.4가동). 번지 없이 정확한 배정은 불가 —
**결정적 근사**로 채운다: 숫자·구분점(`[0-9·.]`) 제거한 행정동명이 법정동명과 같은 것 우선,
동률이면 코드 오름차순. 정밀 배정이 필요해지면 Step 8(geocode, 번지 단위)에서 재산출한다.

**법정동 폐지/개편 대응**: 참조 테이블이 매 실행 최신 스냅샷으로 교체된다. 참조 로직 변경이나
과거 행 재해석이 필요하면 `dbt run --full-refresh --select silver_license_history+` 로 전체 백필해
소급 반영한다. 원천 주소 문자열 자체의 갱신은
지자체가 인허가 시스템을 고칠 때 U 증분으로 유입된다(2026-07-06 실증 — as-is→to-be 추적 가능).

---

## 3. 좌표 변환 — 중부원점 TM → WGS84 (latitude/longitude)

원천 `X`/`Y` 는 **EPSG:5174(보정 중부원점, Bessel1841)** 로 실측 판별했다.
외부 API 보정 없이 **순수 계산**으로 변환한다(silver 모델 geo_* CTE 체인).

- 판별(랜드마크 실좌표 대조, 2026-07-06):

| 랜드마크 | EPSG:2097(127°) 오차 | **EPSG:5174(127°0'10.405") 오차** |
|---|---|---|
| 서울시청(세종대로 110) | 230 m | **42 m** |
| 강남파이낸스센터(테헤란로 152) | 251 m | **90 m** |

  (잔차 수십 m 는 필지 대표점↔건물 실좌표 차이 수준 → 5174 채택.)
- 파라미터: TM lat0 38°, lon0 127°0′10.405″, k0=1, FE 200000, FN 500000, Bessel1841
  (a=6377397.155, 1/f=299.1528128). 데이텀 변환은 한국 표준 7-parameter Helmert
  (ΔX −115.80, ΔY 474.99, ΔZ 674.11, rx 1.16″, ry −2.31″, rz −1.63″, s 6.43ppm,
  position-vector) → WGS84, 위경도 복원은 Bowring 비반복식.
- **유효성 게이트**: X/Y 에 서울 밖·쓰레기 값 존재(실측: Y 음수 등) — 변환 결과가
  한반도 bbox(위도 33~39.5, 경도 124~132) 밖이면 null (원문 `source_coord_x/y` 는 보존).
  정밀 품질 판정(location_quality)은 Step 8 geocode 파이프라인의 책임.
- 회귀 가드: [tests/assert_silver_license_current_geo_landmark.sql](../tests/assert_silver_license_current_geo_landmark.sql)
  (시청 레코드 ±0.005° — warn).

---

## 4. 테이블 계약 (ASAC-DAG 가 적재, dbt 는 source 참조)

| 테이블 | 그레인 | 적재 방식 | 시각 컬럼 |
|---|---|---|---|
| `bronze_ref_admin_dong` | (행정동, 법정동) 연계 행 | 전량 교체(최신 스냅샷) | `loaded_at` — **UTC(naive)**, bronze 층 규약 |
| `bronze_address_enrichment` | `road_address_norm` | 키 단위 delete-then-insert(캐시) | `requested_at` — **UTC(naive)** |

- `road_address_norm` 정규화 규칙은 silver 의 `road_address_norm` 과 **반드시 동일**해야
  한다('(' 절단 → 공백 축약 → trim → 빈값 null) — 양쪽 구현: dbt 모델 / `juso.normalize_road_key`.
- 첫 dbt 실행 전에 두 테이블이 존재해야 한다(transform DAG 가 매 실행 ensure) —
  단독 `dbt run` 을 새 환경에서 돌리려면 DAG 를 먼저 1회 실행할 것.
