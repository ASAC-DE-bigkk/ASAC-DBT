# culture 공간축 bronze canonical 전환 — silver 정렬 + 행정동-grain gold

- 배경 근거: 팀 공통축 합의 [ASAC-DBT#48](https://github.com/ASAC-DE-bigkk/ASAC-DBT/issues/48) (CLOSED) — 시간=where필터·공간=행정동/법정동 조인축(행안부10 canonical), **seed→source dim 전환·seed 폴백**(codingpoppy #154 코멘트).
- bronze 원천: `axes_bronze.admin_dong_master`(ASAC-DAG#154, codingpoppy 적재, 행안부 MODS 행정동 연계) → asac_axes 공용 view `dim_admin_dong`(서울 행정동 grain ~426행).
- 브랜치: `feat/culture-space-axis-canonical` (sample/dbt, dev 기준)

## 목적

culture를 **bronze 행정동 canonical(`dim_admin_dong`)을 소비하는 첫 도메인**으로 전환한다.
현재 전 도메인(culture 포함)은 seed(`seoul_admin_dong_boundary`·`_crosswalk`)로만 공간축을 해석하고
bronze 파생 `dim_admin_dong`은 orphan(소비 0건)이다. culture가 first-consumer 레퍼런스가 된다.

## 아키텍처 (하이브리드 — #48 (a): source dim + seed 폴백)

```
좌표 ──[boundary seed · point-in-polygon(ST_Contains)]──▶ admin_dong_code   (조인키 · geometry는 seed)
                                                              │  admin_dong_code로 조인
                                                              ▼
                                      dim_admin_dong (bronze canonical)
                                        → gu · gu_code · admin_dong(명칭) · stat_region_cd
                              ┌────────────────────────────────┴───────────────────┐
                              ▼                                                     ▼
                   silver (canonical stamp)                    gold_culture_activity_by_dong
                                                               (admin_dong_code × event_date, dim=left base)
```

- **좌표→행정동**: bronze엔 geometry가 없으므로 **boundary seed point-in-polygon 유지**(타 도메인 정합). 산출 = `admin_dong_code`(조인키).
- **코드·명칭·gu**: `admin_dong_code`로 `dim_admin_dong` 조인 → canonical `gu`·`gu_code`·`admin_dong`·`stat_region_cd`. **bronze가 진실원천**.
- **seed 격하**: `seoul_admin_dong_crosswalk`의 gu라벨→gu_code 역할을 dim이 대체. crosswalk는 좌표 보조·폴백으로만(#48 방침). `seoul_admin_dong_boundary`는 geometry(point-in-polygon)로 존치.

## 변경 1 — silver canonical 정렬 (8개 + facility 경유 2개)

대상(현재 `culture_dong_map` + crosswalk `gu_codes` 패턴 사용): `silver_culture_event`·`_exhibition`·`_reservation`·`_sejong`·`_sports_event`·`_kcisa_event`·`_facility`·`_space`. `performance`·`festival`은 facility 경유라 facility 전환 시 자동 반영.

- boundary seed point-in-polygon **유지** → `admin_dong_code` 획득.
- 현재 `gu_codes as (select distinct gu, gu_code from crosswalk)` + `coalesce(g.gu_code, d.coord_gu_code)` 를
  **`dim_admin_dong` 조인(admin_dong_code 기준)**으로 교체:
  - `gu_code` = `coalesce(dim[admin_dong_code].gu_code, dim[gu라벨].gu_code, boundary coord_gu_code)` —
    **좌표→dim 우선, 라벨→dim 폴백, boundary 최후 폴백**. crosswalk seed 완전 은퇴(양 경로 dim 사용).
  - `admin_dong` = `coalesce(dim.admin_dong, boundary dong)` — canonical 명칭 우선.
  - `stat_region_cd` = dim (신규 노출, 통계청 alias 다리 — 선택).
  - **회귀 방지(중요)**: `facility`는 좌표 커버리지 낮음(detail 캡 admin_dong_code ~12%) → 순수 좌표-우선이면
    좌표 없는 시설 gu_code가 null 폭락(~100%→~12%). **라벨→dim 폴백이 좌표 없는 행을 방어**한다.
    라벨 폴백 = `select distinct gu, gu_code from dim_admin_dong`(25 자치구) ⨝ 소스 gu 라벨.
- **`gu`(원본 자치구 라벨)는 보존** — 소스 자기신고 값(GUNAME/AREANM/gugunnm)은 오배정 테스트의 정답 라벨이므로 유지. canonical과 별개 컬럼.
- **설계 결정 — gu_code 유래 전환**: 현재는 라벨-우선(crosswalk[gu라벨]), 전환 후 **좌표-우선(dim[admin_dong_code←좌표])**. 라벨↔좌표 불일치 행에서 gu_code가 바뀔 수 있음 → 아래 drift/오배정 테스트가 규모를 계측. 좌표-우선이 #48 "조인은 공간축(좌표 유래 행정동)으로" 취지에 부합.
- 편집 격리: 8개 모델의 `gu_codes` CTE 소스만 교체(공통 패턴). 가능하면 공유 CTE/매크로로 DRY.

## 변경 2 — 신규 `gold_culture_activity_by_dong`

- grain: **`admin_dong_code` × `event_date`**.
- **`dim_admin_dong`을 LEFT BASE**(426개 행정동 전량) → 활동 0건 동도 행 존재(지도 빈칸 방지 — dim 문서 권장 패턴).
- 활동 소스: `gold_culture_location_daily`와 동일 union(performance·event·festival·exhibition·sejong·kcisa) 을 **admin_dong_code로 재집계**(기간→일자 전개는 동일 방식).
- **date_spine 바운드**: `[current_date-90, current_date+365]` — 무제한이면 활동이 2000~2027년(9,185일)에 걸쳐 426동×27년 = 3.9M행·96% 0(실측). 최근 창으로 제한해 ~18만행 유지, "0건 동 표현"은 현재~근미래 지도에만 유의미.
- 컬럼: `admin_dong_code`·`admin_dong`·`gu_code`·`gu`·`stat_region_cd`(dim) + `event_date` + `activities_count`·type별 count. **snake_case**(팀 합의 2026-07-10).
- 기존 `gold_culture_location_daily`(gu_code×일자)는 **존치** — 구 단위 롤업 표면 유지.

## 변경 3 — 테스트·계약

- **기존** `assert_gu_label_vs_coord_mismatch`(#48 약속 오배정률, 이미 존재) — crosswalk seed 참조를 **`dim_admin_dong`으로 갱신**(canonical gu 대조).
- **신규** `assert_culture_admin_dong_in_canonical` — 공간 silver의 `admin_dong_code`가 전부 `dim_admin_dong`에 존재하는지(boundary seed vs bronze revision **drift 감지**). severity **warn**(재편 3개 동 등 알려진 미스 허용).
- gold 계약(`schema.yml`): `admin_dong_code`+`event_date` grain unique, `admin_dong_code` not_null, gu_code axis_coverage(실측−5%p, warn).
- 기존 silver 공간 계약(gu_code/admin_dong_code axis_coverage)은 전환 후 **실측 재보정**.

## 변경 4 — config·배선

- culture가 `dim_admin_dong`을 `ref('asac_axes', 'dim_admin_dong')`로 소비(asac_axes는 이미 packages.yml 의존).
- `axes_bronze` 소스 스키마 = `var('axes_bronze_schema', env_var('DEV_SMOKE_SCHEMA','dev_local'))` → culture `dbt_project.yml`의 `vars`로 **공용 dev 스키마** 주입(안착 확정 후). 설계는 스키마 무관(파라미터화).

## 구현 게이트 (중요)

- bronze `admin_dong_master`가 현재 **팀원 개인 dev 스키마(`dev_codingpoppy94`)에만** 존재. 공용 dev 스키마 안착은 codingpoppy와 **미협의**.
- 방향은 #48 합의됐으나 "어느 스키마"는 미확정 → **dev 검증은 임시로 `dev_codingpoppy94` 타깃**으로 수행하되, **머지는 공용 dev 안착 합의 후**.
- 개인 스키마에 프로덕션 의존을 박지 않는다(설계는 var 주입으로 위치 독립).

## AC (구현 시)

- dbt parse/compile/build 통과(컨테이너 dev, `--no-partial-parse`).
- silver 공간축: gu_code/admin_dong_code가 `dim_admin_dong` canonical에서 유래(실측 조인율).
- `gold_culture_activity_by_dong`: 426개 행정동 전량 존재(활동 0 동 포함), grain unique.
- drift/오배정 테스트 통과(warn 수준, 계측치 기록).
- 기존 gu-grain gold·타 모델 회귀 없음(culture 전체 build PASS).

## 범위 밖

- 좌표·경계(WKT)를 bronze로 적재(seed 완전 제거) — 별도 인프라 프로젝트(팀원 파이프라인+asac_axes 수정=멘토 게이트).
- 법정동(beop_dong) 축 편입 — dim_beop_admin_link 소비는 후속(culture는 주소 기반 아님, 우선순위 낮음).
- 행정동 개편 감지 센티널(#48 내 제안) — 패키지 레벨 운영 작업, 별도.
