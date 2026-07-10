# culture 공간축 bronze canonical 전환 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** culture silver의 gu_code/admin_dong 명칭을 seed(crosswalk) 대신 bronze canonical `dim_admin_dong`에서 stamp하고, 행정동-grain gold(`gold_culture_activity_by_dong`)를 신설한다.

**Architecture:** 좌표→행정동 point-in-polygon은 boundary seed 유지(admin_dong_code 조인키), 코드·명칭·gu는 admin_dong_code로 `dim_admin_dong` 조인해 stamp(좌표-우선·라벨-폴백·boundary 최후폴백). gold는 dim을 date_spine과 cross join한 scaffold에 활동을 left join해 0건 동도 표현.

**Tech Stack:** dbt-trino(dev=iceberg_dev.culture), asac_axes 패키지(`dim_admin_dong` view + seeds), culture 매크로.

## Global Constraints

- 설계 정본: `domains/culture/docs/design/2026-07-10-culture-space-axis-canonical.md`. 근거: [ASAC-DBT#48](https://github.com/ASAC-DE-bigkk/ASAC-DBT/issues/48).
- 워킹트리 `C:\Users\Dell3571\ask-seoul\sample\dbt`(컨테이너 `/opt/airflow/dbt` 마운트), 브랜치 `feat/culture-space-axis-canonical`.
- **dim_admin_dong 원천(`axes_bronze`)이 공용 dev 스키마 미적재** → dev 검증은 팀원 스키마 `dev_codingpoppy94`를 **`--vars`로 임시 주입**. 개인 스키마를 git에 커밋하지 않는다. **머지는 공용 dev 안착(codingpoppy 합의) 후 보류.**
- 컨테이너 dbt 헬퍼(이 계획 전용 — `--vars`로 bronze 스키마 지정):

  ```powershell
  cd C:\Users\Dell3571\ask-seoul\sample
  docker compose exec -T airflow-scheduler bash -lc 'export DBT_PROFILES_DIR=/opt/airflow/dbt/domains/culture DBT_PROJECT_DIR=/opt/airflow/dbt/domains/culture; cd /opt/airflow/dbt/domains/culture; /home/airflow/dbt-venv/bin/dbt <ARGS> --vars "{axes_bronze_schema: dev_codingpoppy94}" --no-partial-parse --target dev --no-use-colors'
  ```
- Trino 직접 조회 헬퍼: `docker compose exec -T trino trino --output-format TSV --execute "<SQL>"`.
- 자기 도메인(culture) 스키마 밖 미기록. 커밋 마지막 줄 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- gold table/column = **snake_case**(팀 합의). 시간축 컬럼 `_at`/`_date`만.
- 종료 시 sample/dbt를 dev로 복귀.

---

### Task 1: culture_admin_canon 매크로 + dim 접근 검증

**Files:**
- Modify: `domains/culture/macros/culture_axes.sql` (파일 끝)

**Interfaces:**
- Produces: `{{ culture_admin_canon() }}` — `with` 절 안에서 `canon as (admin_dong_code, gu_code, admin_dong)`, `canon_gu as (distinct gu, gu_code)` 두 CTE를 방출(선행 CTE 뒤 콤마 다음에 배치). Task 2의 8개 silver가 소비.

- [ ] **Step 1: 매크로 추가** — `culture_axes.sql` 파일 끝에 append:

```sql
{#
  culture_admin_canon — bronze 행정동 canonical(dim_admin_dong) stamp용 두 CTE(#48).
  - canon    : admin_dong_code 로 조인(좌표→행정동 결과에 canonical 코드·명칭 stamp)
  - canon_gu : gu 라벨로 조인(좌표 없는 행 gu_code 폴백 — facility 커버리지 방어)
  `with ... , {{ culture_admin_canon() }}` 형태로 선행 CTE 뒤에 배치.
#}
{% macro culture_admin_canon() -%}
canon as (
    select admin_dong_code, gu_code, admin_dong
    from {{ ref('asac_axes', 'dim_admin_dong') }}
),
canon_gu as (
    select distinct gu, gu_code
    from {{ ref('asac_axes', 'dim_admin_dong') }}
)
{%- endmacro %}
```

- [ ] **Step 2: parse 게이트** — Run(헬퍼):

```
dbt parse
```

Expected: 에러 0으로 정상 종료.

- [ ] **Step 3: dim_admin_dong 접근·행수 검증** — Run(헬퍼):

```
dbt build --select asac_axes.dim_admin_dong
```

Expected: 모델 1 PASS. 이어 Trino로 행수 확인:

```powershell
cd C:\Users\Dell3571\ask-seoul\sample
docker compose exec -T trino trino --output-format TSV --execute "select count(*), count(distinct gu_code) from iceberg_dev.culture.dim_admin_dong"
```

Expected: ~426행, gu_code 25종. (실패 시 = bronze 미접근 → `--vars` 스키마 확인. 계속 실패면 STOP·게이트 미충족 보고.)

- [ ] **Step 4: 커밋**

```powershell
cd C:\Users\Dell3571\ask-seoul\sample\dbt
git add domains/culture/macros/culture_axes.sql
git commit -m @'
feat(culture): #48 culture_admin_canon 매크로 — dim_admin_dong stamp CTE

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 2: 8개 silver를 dim canonical stamp로 전환

**Files (Modify):**
- `domains/culture/models/silver/silver_culture_event.sql`
- `domains/culture/models/silver/silver_culture_exhibition.sql`
- `domains/culture/models/silver/silver_culture_reservation.sql`
- `domains/culture/models/silver/silver_culture_sejong.sql`
- `domains/culture/models/silver/silver_culture_sports_event.sql`
- `domains/culture/models/silver/silver_culture_kcisa_event.sql`
- `domains/culture/models/silver/silver_culture_facility.sql`
- `domains/culture/models/silver/silver_culture_space.sql`

**Interfaces:**
- Consumes: `{{ culture_admin_canon() }}`(Task 1). 출력 컬럼 계약 **불변**(gu·gu_code·admin_dong·admin_dong_code 유지), 값 유래만 crosswalk→dim.

각 모델은 동일한 3-처 편집. **공통 편집(7개 모델: event·exhibition·reservation·sejong·sports_event·facility·space — dong_map 별칭 `d`):**

- [ ] **Step 1: gu_codes CTE 교체 (8개 모델 공통)** — 각 파일에서:

old:
```sql
gu_codes as (select distinct gu, gu_code from {{ ref('seoul_admin_dong_crosswalk') }})
```
new:
```sql
{{ culture_admin_canon() }}
```

- [ ] **Step 2: coalesce·admin_dong·join 교체 (dong_map 별칭 `d`인 7개 모델)** — 각 파일에서:

old:
```sql
    coalesce(g.gu_code, d.coord_gu_code) as gu_code,
    d.admin_dong, d.admin_dong_code,
```
new:
```sql
    coalesce(cd.gu_code, cg.gu_code, d.coord_gu_code) as gu_code,
    coalesce(cd.admin_dong, d.admin_dong) as admin_dong, d.admin_dong_code,
```

그리고 각 파일 말미의 gu_codes 조인을 canon 2개 조인으로 교체. 모델별 base 별칭(`<X>`)이 다르므로 아래 표대로:

| 모델 | old 조인 라인 | new 조인 라인 |
|---|---|---|
| event | `left join gu_codes g on g.gu = l.gu` | `left join canon cd on cd.admin_dong_code = d.admin_dong_code`<br>`    left join canon_gu cg on cg.gu = l.gu` |
| exhibition | `left join gu_codes g on g.gu = p.gu`(→ best/ placed 별칭 `p`) | `left join canon cd on cd.admin_dong_code = d.admin_dong_code`<br>`    left join canon_gu cg on cg.gu = p.gu` |
| reservation | `left join gu_codes g on g.gu = l.gu` | `left join canon cd on cd.admin_dong_code = d.admin_dong_code`<br>`    left join canon_gu cg on cg.gu = l.gu` |
| sejong | `left join gu_codes g on g.gu = p.gu` | `left join canon cd on cd.admin_dong_code = d.admin_dong_code`<br>`    left join canon_gu cg on cg.gu = p.gu` |
| sports_event | `left join gu_codes g on g.gu = p.gu` | `left join canon cd on cd.admin_dong_code = d.admin_dong_code`<br>`    left join canon_gu cg on cg.gu = p.gu` |
| facility | `left join gu_codes g on g.gu = j.gu` | `left join canon cd on cd.admin_dong_code = d.admin_dong_code`<br>`    left join canon_gu cg on cg.gu = j.gu` |
| space | `left join gu_codes g on g.gu = l.gu` | `left join canon cd on cd.admin_dong_code = d.admin_dong_code`<br>`    left join canon_gu cg on cg.gu = l.gu` |

- [ ] **Step 3: kcisa 전용 편집 (dong_map 별칭 `m`, base `d`)** — `silver_culture_kcisa_event.sql`:

Step 1의 gu_codes 교체는 동일 적용. 그 외:

old:
```sql
    coalesce(g.gu_code, m.coord_gu_code) as gu_code,
    m.admin_dong, m.admin_dong_code,
```
new:
```sql
    coalesce(cd.gu_code, cg.gu_code, m.coord_gu_code) as gu_code,
    coalesce(cd.admin_dong, m.admin_dong) as admin_dong, m.admin_dong_code,
```
old:
```sql
left join gu_codes g on g.gu = d.gu
```
new:
```sql
left join canon cd on cd.admin_dong_code = m.admin_dong_code
    left join canon_gu cg on cg.gu = d.gu
```

- [ ] **Step 4: 8개 빌드** — Run(헬퍼):

```
dbt build --select silver_culture_event silver_culture_exhibition silver_culture_reservation silver_culture_sejong silver_culture_sports_event silver_culture_kcisa_event silver_culture_facility silver_culture_space
```

Expected: 8 모델 + 기존 계약 테스트 PASS(coverage warn 허용, ERROR 0).

- [ ] **Step 5: 회귀 검증 — gu_code 커버리지 매트릭스** — Run:

```powershell
cd C:\Users\Dell3571\ask-seoul\sample
foreach ($t in @('silver_culture_event','silver_culture_exhibition','silver_culture_reservation','silver_culture_sejong','silver_culture_sports_event','silver_culture_kcisa_event','silver_culture_facility','silver_culture_space')) { $r = docker compose exec -T trino trino --output-format TSV --execute "select round(1.0*count(gu_code)/count(*),4) from iceberg_dev.culture.$t" 2>$null; "$t`t$r" }
```

Expected: **facility 포함 전 모델 gu_code 커버리지가 전환 전 대비 유지/개선**(라벨 폴백이 좌표 없는 시설 방어). facility가 급락(예: <0.9)하면 STOP — 라벨 폴백(canon_gu) 조인 확인. admin_dong_code 커버리지는 boundary seed 그대로라 불변.

- [ ] **Step 6: 커밋**

```powershell
cd C:\Users\Dell3571\ask-seoul\sample\dbt
git add domains/culture/models/silver/silver_culture_event.sql domains/culture/models/silver/silver_culture_exhibition.sql domains/culture/models/silver/silver_culture_reservation.sql domains/culture/models/silver/silver_culture_sejong.sql domains/culture/models/silver/silver_culture_sports_event.sql domains/culture/models/silver/silver_culture_kcisa_event.sql domains/culture/models/silver/silver_culture_facility.sql domains/culture/models/silver/silver_culture_space.sql
git commit -m @'
feat(culture): #48 silver 공간축 dim canonical stamp — crosswalk→dim_admin_dong

좌표→admin_dong_code(boundary seed)로 dim 조인해 gu_code·admin_dong canonical stamp.
좌표-우선·라벨-폴백(canon_gu)·boundary 최후폴백. gu 원본 라벨 보존.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 3: gold_culture_activity_by_dong + 계약

**Files:**
- Create: `domains/culture/models/gold/gold_culture_activity_by_dong.sql`
- Modify: `domains/culture/models/schema.yml` (파일 끝)

**Interfaces:**
- Consumes: Task 2 silver들의 `admin_dong_code`·`event_start_date`·`event_end_date`, `ref('asac_axes','dim_admin_dong')`.
- Produces: `gold_culture_activity_by_dong` — grain `admin_dong_code × event_date`, 컬럼 `admin_dong_code·admin_dong·gu_code·gu·stat_region_cd·event_date·activities_count·performances_count·events_count·festivals_count·exhibitions_count·sejong_count·kcisa_count`.

- [ ] **Step 1: gold 모델 작성** — `gold_culture_activity_by_dong.sql`:

```sql
-- gold: 행정동(admin_dong) × 일자 문화활동 집계 — bronze canonical 소비 첫 gold(#48).
-- dim_admin_dong(426동)을 활동 일자 spine과 cross join한 scaffold에 활동을 left join →
-- 활동 0건 행정동도 0으로 행 존재(지도 빈칸 방지, dim 문서 권장 패턴).
-- sports(야구)는 문화활동 축 아님 → 제외(gold_culture_location_daily 관례 유지).

with dim as (
    select admin_dong_code, admin_dong, gu_code, gu, stat_region_cd
    from {{ ref('asac_axes', 'dim_admin_dong') }}
),

raw_activities as (
    select admin_dong_code, cast(performance_id as varchar) as activity_id, 'performance' as activity_type, event_start_date, event_end_date
    from {{ ref('silver_culture_performance') }}
    union all
    select admin_dong_code, event_key, 'event', event_start_date, event_end_date
    from {{ ref('silver_culture_event') }}
    union all
    select admin_dong_code, cast(festival_id as varchar), 'festival', event_start_date, event_end_date
    from {{ ref('silver_culture_festival') }}
    union all
    select admin_dong_code, cast(exhibition_id as varchar), 'exhibition', event_start_date, event_end_date
    from {{ ref('silver_culture_exhibition') }}
    union all
    select admin_dong_code, cast(sejong_id as varchar), 'sejong', event_start_date, event_end_date
    from {{ ref('silver_culture_sejong') }}
    union all
    select admin_dong_code, 'kcisa:' || event_id, 'kcisa', event_start_date, event_end_date
    from {{ ref('silver_culture_kcisa_event') }}
),

activities as (
    select * from raw_activities
    where admin_dong_code is not null
      and event_start_date is not null
      and event_end_date is not null
      and event_end_date >= event_start_date
      and date_diff('day', event_start_date, event_end_date) <= 400
),

expanded as (
    select a.admin_dong_code, a.activity_id, a.activity_type, d.activity_date
    from activities a
    cross join unnest(sequence(a.event_start_date, a.event_end_date, interval '1' day)) as d(activity_date)
),

date_spine as (select distinct activity_date as event_date from expanded),

scaffold as (
    select dim.admin_dong_code, dim.admin_dong, dim.gu_code, dim.gu, dim.stat_region_cd, ds.event_date
    from dim
    cross join date_spine ds
),

agg as (
    select
        admin_dong_code,
        activity_date as event_date,
        count(distinct activity_id) as activities_count,
        count(distinct case when activity_type = 'performance' then activity_id end) as performances_count,
        count(distinct case when activity_type = 'event'       then activity_id end) as events_count,
        count(distinct case when activity_type = 'festival'    then activity_id end) as festivals_count,
        count(distinct case when activity_type = 'exhibition'  then activity_id end) as exhibitions_count,
        count(distinct case when activity_type = 'sejong'      then activity_id end) as sejong_count,
        count(distinct case when activity_type = 'kcisa'       then activity_id end) as kcisa_count
    from expanded
    group by admin_dong_code, activity_date
)

select
    s.admin_dong_code, s.admin_dong, s.gu_code, s.gu, s.stat_region_cd,
    s.event_date,
    coalesce(a.activities_count, 0)   as activities_count,
    coalesce(a.performances_count, 0) as performances_count,
    coalesce(a.events_count, 0)       as events_count,
    coalesce(a.festivals_count, 0)    as festivals_count,
    coalesce(a.exhibitions_count, 0)  as exhibitions_count,
    coalesce(a.sejong_count, 0)       as sejong_count,
    coalesce(a.kcisa_count, 0)        as kcisa_count
from scaffold s
left join agg a on a.admin_dong_code = s.admin_dong_code and a.event_date = s.event_date
```

- [ ] **Step 2: schema.yml 계약 추가** — 파일 끝(마지막 모델 엔트리 뒤)에 append:

```yaml
  - name: gold_culture_activity_by_dong
    description: 행정동(admin_dong_code) × 일자 문화활동 집계(#48). dim_admin_dong 426동 scaffold라 활동 0건 동도 0으로 존재. sports 제외.
    columns:
      - name: admin_dong_code
        tests: [not_null]
      - name: event_date
        tests: [not_null]
      - name: gu_code
        tests: [not_null]
```

- [ ] **Step 3: 빌드 + grain 검증** — Run(헬퍼):

```
dbt build --select gold_culture_activity_by_dong
```

Expected: 모델 1 + 계약 3 PASS. 이어 grain unique + 행수 확인:

```powershell
cd C:\Users\Dell3571\ask-seoul\sample
docker compose exec -T trino trino --output-format TSV --execute "select count(*) rows, count(distinct admin_dong_code) dongs, count(*) - count(distinct (admin_dong_code, event_date)) dup from iceberg_dev.culture.gold_culture_activity_by_dong"
```

Expected: `dongs = 426`(전 행정동 존재), `dup = 0`(grain unique). rows = 426 × 활동일수(0 정상).

- [ ] **Step 4: AC 실측 — 활동 있는 동 vs 0건 동** — Run:

```powershell
docker compose exec -T trino trino --output-format TSV --execute "select sum(case when activities_count>0 then 1 else 0 end) active_rows, sum(case when activities_count=0 then 1 else 0 end) zero_rows from iceberg_dev.culture.gold_culture_activity_by_dong"
```

Expected: active_rows > 0 그리고 zero_rows > 0(0건 동 표현 확인 = 이 gold의 핵심 가치).

- [ ] **Step 5: 커밋**

```powershell
cd C:\Users\Dell3571\ask-seoul\sample\dbt
git add domains/culture/models/gold/gold_culture_activity_by_dong.sql domains/culture/models/schema.yml
git commit -m @'
feat(culture): #48 gold_culture_activity_by_dong — 행정동 grain, dim scaffold

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 4: 테스트 2종 + 전체 빌드 + PR

**Files:**
- Modify: `domains/culture/tests/assert_gu_label_vs_coord_mismatch.sql`
- Create: `domains/culture/tests/assert_culture_admin_dong_in_canonical.sql`

**Interfaces:**
- Consumes: Task 2 silver들, `ref('asac_axes','dim_admin_dong')`.

- [ ] **Step 1: 오배정 테스트를 dim 참조로 갱신** — `assert_gu_label_vs_coord_mismatch.sql`의 `cw` CTE 교체:

old:
```sql
with cw as (select distinct gu_code, gu from {{ ref('seoul_admin_dong_crosswalk') }}),
```
new:
```sql
with cw as (select distinct gu_code, gu from {{ ref('asac_axes', 'dim_admin_dong') }}),
```

(나머지 로직 불변 — 좌표 유래 admin_dong_code 앞5자리 → dim canonical gu 대조. 주석의 "crosswalk"를 "dim_admin_dong canonical"로 갱신.)

- [ ] **Step 2: drift 테스트 신규** — `assert_culture_admin_dong_in_canonical.sql`:

```sql
-- #48: 공간 silver 의 admin_dong_code 가 bronze canonical(dim_admin_dong)에 존재하는지.
-- 미존재 = boundary seed(좌표→코드) 가 bronze 개정과 어긋남(재편/drift). warn — 알려진
-- 재편 동(신설동/상일1·2동 등) 소수 미매칭 수용, 규모만 계측.
{{ config(severity = 'warn') }}

with silver_codes as (
    select admin_dong_code from {{ ref('silver_culture_event') }}
    union select admin_dong_code from {{ ref('silver_culture_exhibition') }}
    union select admin_dong_code from {{ ref('silver_culture_reservation') }}
    union select admin_dong_code from {{ ref('silver_culture_sejong') }}
    union select admin_dong_code from {{ ref('silver_culture_kcisa_event') }}
    union select admin_dong_code from {{ ref('silver_culture_facility') }}
    union select admin_dong_code from {{ ref('silver_culture_space') }}
),

canon as (select admin_dong_code from {{ ref('asac_axes', 'dim_admin_dong') }})

select s.admin_dong_code
from silver_codes s
where s.admin_dong_code is not null
  and s.admin_dong_code not in (select admin_dong_code from canon)
```

- [ ] **Step 3: 테스트 실행** — Run(헬퍼):

```
dbt test --select assert_gu_label_vs_coord_mismatch assert_culture_admin_dong_in_canonical
```

Expected: 둘 다 PASS 또는 WARN(warn severity — 계측치 기록). ERROR 0.

- [ ] **Step 4: culture 전체 빌드** — Run(헬퍼):

```
dbt build --exclude package:asac_axes source:axes_bronze
```

Expected: 전 culture 모델·테스트 PASS/WARN, ERROR 0. (asac_axes 패키지 자체 테스트·axes_bronze 소스 freshness는 제외 — 공용 인프라 소관.)

- [ ] **Step 5: PR 생성 (머지 보류)** — 본문에 **구현 게이트 명시**:

```powershell
cd C:\Users\Dell3571\ask-seoul\sample\dbt
git push -u origin feat/culture-space-axis-canonical
gh pr create --repo ASAC-DE-bigkk/ASAC-DBT --base dev --head feat/culture-space-axis-canonical --title "feat(culture): #48 공간축 bronze canonical 전환 — silver dim stamp + 행정동 gold" --body-file <본문파일>
```

PR 본문 필수 항목: 요약 / 변경(silver 8 + gold 1 + 테스트 2 + 매크로) / AC 실측(gu_code 커버리지 매트릭스·gold 426동·drift 계측) / **⚠️ 머지 게이트: dim_admin_dong bronze가 공용 dev 스키마 안착 후 머지(현재 dev_codingpoppy94 임시 검증)** / `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. PR은 생성만 — 머지는 사용자.

- [ ] **Step 6: dev 복귀**

```powershell
cd C:\Users\Dell3571\ask-seoul\sample\dbt
git checkout dev
```

---

## Self-Review

- **Spec 커버리지**: silver dim stamp(T2, 8모델) / 신규 행정동 gold(T3) / 오배정 테스트 dim 갱신 + drift 테스트(T4) / 매크로·config(T1, `--vars`) — 설계 4개 변경 전부 매핑. stat_region_cd는 silver 미노출(YAGNI), gold만 dim 직접 취득.
- **타입 일관성**: `culture_admin_canon()` → `canon(admin_dong_code,gu_code,admin_dong)`·`canon_gu(gu,gu_code)` (T1 정의 = T2 사용). gold union activity_id 프리픽스 `kcisa:`(T3) = 기존 gold_culture_location_daily 관례. gold grain admin_dong_code×event_date = 계약(T3 Step 2).
- **회귀 방지**: facility 좌표 커버리지 낮음 → 라벨 폴백(canon_gu) 명시, T2 Step 5 매트릭스로 검증. kcisa dong_map 별칭 `m` 예외 T2 Step 3 별도.
- **게이트**: bronze 개인 스키마 의존 → `--vars` 임시 검증·머지 보류(T4 Step 5) 명문화. git에 개인 스키마 미커밋.
- **placeholder**: 없음(PR 본문파일 경로만 실행 시 생성).
