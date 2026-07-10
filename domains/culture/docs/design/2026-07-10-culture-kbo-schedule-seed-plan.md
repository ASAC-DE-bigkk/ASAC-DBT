# culture KBO 서울 일정 seed 구현 계획 (#90)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2026-07 잔여 KBO 서울 홈경기를 dbt seed로 적재하고 silver/gold로 "가장 가까운 서울 야구 경기" 질의를 답하게 한다.

**Architecture:** seed 2개(일정 fact + 구장 위치 dim) → silver `silver_culture_sports_event`(축 정렬: gu_code·행정동, event_at) → gold `gold_culture_sports_schedule`(경기 1행 질의 표면). 문화행사 union 무변경, bronze 없음.

**Tech Stack:** dbt-core 1.10 · dbt-trino · Iceberg(iceberg_dev.culture) · 매크로 `culture_dong_map` · seed CSV.

## Global Constraints

- **작업 트리**: `C:/Users/Dell3571/ask-seoul/sample/dbt` 브랜치 `feat/90-culture-kbo-schedule-seed`. **완료 후 dev 복귀**.
- **일정 데이터는 반드시 웹서치 결과에서만** — 학습 지식 사용 금지(할루시네이션 방지). KBO 공홈 직접 크롤(WebFetch) 금지(robots, #195 기준) — 검색 결과 스니펫·뉴스·포털 공개 페이지만.
- **⛔ 사용자 스팟체크 게이트**: CSV 초안 완성 후 사용자 검수 승인 전에는 Task 2로 진행 금지.
- **이름 정확히**: seeds `kbo_seoul_schedule`·`kbo_stadium_location`, silver `silver_culture_sports_event`, gold `gold_culture_sports_schedule`.
- **stadium enum**: `잠실야구장` / `고척스카이돔` (이 표기 그대로). **home_team enum**: `LG` / `두산` / `키움`.
- **grain**: game_date × stadium × game_time (더블헤더 대비).
- **dbt 실행 헬퍼**(컨테이너, dev 타깃, `--no-partial-parse` 포함 — #86에서 신규 파일 캐시 이슈 실증):
  ```bash
  cd C:/Users/Dell3571/ask-seoul/sample
  docker compose exec -T airflow-scheduler bash -lc \
    'export DBT_PROFILES_DIR=/opt/airflow/dbt/domains/culture DBT_PROJECT_DIR=/opt/airflow/dbt/domains/culture; \
     /home/airflow/dbt-venv/bin/dbt <ARGS> --no-partial-parse --target dev --no-use-colors'
  ```
- **커밋 마지막 줄**: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` · **PR body 마지막 줄**: `🤖 Generated with [Claude Code](https://claude.com/claude-code)` · **셀프 머지 금지**.

---

### Task 1: 데이터 소싱 — 웹서치 초안 + 사용자 검수 게이트

**Files:**
- Create: `domains/culture/seeds/kbo_seoul_schedule.csv`
- Create: `domains/culture/seeds/kbo_stadium_location.csv`
- Modify: `domains/culture/dbt_project.yml` (seeds 섹션에 column_types 2건)

**Interfaces:**
- Produces: `ref('kbo_seoul_schedule')` — 컬럼 `game_date(date), game_time(varchar HH:MM), stadium, home_team, away_team` / `ref('kbo_stadium_location')` — 컬럼 `stadium, gu, latitude(double), longitude(double)`. Task 2~4가 소비.

- [ ] **Step 1: 웹서치 — 7월 잔여 서울 홈경기**

WebSearch로 "2026 KBO 7월 일정 잠실", "2026 KBO 7월 고척 키움 홈경기" 등 복수 질의. 수집 대상: 오늘(2026-07-10) 이후 7월 말까지 잠실(LG/두산 홈)·고척(키움 홈) 경기의 날짜·시각·홈팀·원정팀. 교차 확인: 최소 2개 독립 소스가 일치하는 경기만 채택, 불일치·미확인 경기는 CSV에 넣지 않고 검수 요청 시 목록으로 보고.

- [ ] **Step 2: 웹서치 — 구장 좌표**

"잠실야구장 좌표", "고척스카이돔 좌표" 검색, WGS84 십진수(위도 37.x, 경도 126~127.x) 확인. 잠실야구장=송파구, 고척스카이돔=구로구 소속 자치구 함께 확인.

- [ ] **Step 3: CSV 2개 작성**

`domains/culture/seeds/kbo_stadium_location.csv` (헤더+2행, 좌표는 Step 2 실측값):
```
stadium,gu,latitude,longitude
잠실야구장,송파구,<Step2 위도>,<Step2 경도>
고척스카이돔,구로구,<Step2 위도>,<Step2 경도>
```

`domains/culture/seeds/kbo_seoul_schedule.csv` (헤더+Step 1 채택 경기, 형식 예):
```
game_date,game_time,stadium,home_team,away_team
2026-07-10,18:30,잠실야구장,LG,롯데
2026-07-11,17:00,고척스카이돔,키움,SSG
```
game_date=YYYY-MM-DD, game_time=HH:MM(24h KST), 팀명은 소스 표기의 구단 약칭(LG/두산/키움/롯데/SSG/KIA/NC/KT/한화/삼성).

- [ ] **Step 4: dbt_project.yml column_types 추가**

`domains/culture/dbt_project.yml`의 `seeds: culture:` 아래(기존 sema/sejong 뒤)에 추가:
```yaml
    kbo_seoul_schedule:
      +column_types: {game_date: date}
    kbo_stadium_location:
      +column_types: {latitude: double, longitude: double}
```

- [ ] **Step 5: ⛔ 사용자 스팟체크 게이트 (STOP)**

CSV 전문(경기 목록 표)과 소스 요약(어떤 검색 결과에서 왔는지, 교차확인 여부, 미확인 경기 목록)을 사용자에게 제시하고 **KBO 공홈/앱 대조 검수를 요청**. 승인 전 Task 2 진행 금지. 수정 요청 시 CSV 반영 후 재확인.

- [ ] **Step 6: 커밋**

```bash
cd C:/Users/Dell3571/ask-seoul/sample/dbt
git add domains/culture/seeds/kbo_seoul_schedule.csv domains/culture/seeds/kbo_stadium_location.csv domains/culture/dbt_project.yml
git commit -m "feat(culture): #90 KBO 서울 일정·구장 seed CSV (7월 잔여분, 검수 완료)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: seed 적재 + 계약 (seeds/schema.yml + grain unique)

**Files:**
- Create: `domains/culture/seeds/schema.yml`
- Create: `domains/culture/tests/assert_kbo_schedule_grain_unique.sql`

**Interfaces:**
- Consumes: Task 1의 seed 2개.
- Produces: dev에 `iceberg_dev.culture.kbo_seoul_schedule`·`kbo_stadium_location` 테이블 + 계약 테스트 green.

- [ ] **Step 1: grain unique 테스트 작성**

`domains/culture/tests/assert_kbo_schedule_grain_unique.sql`:
```sql
-- KBO 일정 그레인 (game_date, stadium, game_time) 유일성 단언 — 더블헤더는 시각으로 구분.
select game_date, stadium, game_time, count(*) as n
from {{ ref('kbo_seoul_schedule') }}
group by game_date, stadium, game_time
having count(*) > 1
```

- [ ] **Step 2: seeds/schema.yml 작성**

`domains/culture/seeds/schema.yml`:
```yaml
version: 2

seeds:
  - name: kbo_seoul_schedule
    description: KBO 서울 홈경기 일정(잠실 LG/두산·고척 키움) — 수기 seed, 월 1회 갱신(git diff=감사 로그). 원천 = 공개 KBO 일정(비저작물 사실).
    columns:
      - name: game_date
        description: 경기일 (KST)
        tests: [not_null]
      - name: game_time
        description: 경기 시각 HH:MM (KST)
        tests: [not_null]
      - name: stadium
        description: 구장명
        tests:
          - not_null
          - accepted_values:
              values: ["잠실야구장", "고척스카이돔"]
      - name: home_team
        description: 홈팀(서울 연고)
        tests:
          - not_null
          - accepted_values:
              values: ["LG", "두산", "키움"]
      - name: away_team
        description: 원정팀
        tests: [not_null]
  - name: kbo_stadium_location
    description: 서울 KBO 구장 위치 차원 (2행) — silver 축 정렬용.
    columns:
      - name: stadium
        tests: [not_null, unique]
      - name: gu
        tests: [not_null]
      - name: latitude
        tests: [not_null]
      - name: longitude
        tests: [not_null]
```

- [ ] **Step 3: seed 적재 + 계약 테스트 실행**

Run (헬퍼):
```
dbt seed --select kbo_seoul_schedule kbo_stadium_location
dbt test --select kbo_seoul_schedule kbo_stadium_location assert_kbo_schedule_grain_unique
```
Expected: seed 2개 `INSERT` 성공, 테스트 전부 PASS (not_null·enum·unique·grain).

- [ ] **Step 4: 커밋**

```bash
cd C:/Users/Dell3571/ask-seoul/sample/dbt
git add domains/culture/seeds/schema.yml domains/culture/tests/assert_kbo_schedule_grain_unique.sql
git commit -m "feat(culture): #90 KBO seed 계약 — enum·not_null·grain unique(더블헤더 대비)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: silver_culture_sports_event

**Files:**
- Create: `domains/culture/models/silver/silver_culture_sports_event.sql`
- Modify: `domains/culture/models/schema.yml` (models 리스트 끝에 엔트리 추가)

**Interfaces:**
- Consumes: `ref('kbo_seoul_schedule')`, `ref('kbo_stadium_location')`, 매크로 `culture_dong_map`, `ref('seoul_admin_dong_crosswalk')`.
- Produces: `ref('silver_culture_sports_event')` — 컬럼 `game_date, game_time, stadium, home_team, away_team, event_at, longitude, latitude, gu, gu_code, admin_dong, admin_dong_code, source_system`. Task 4가 소비.

- [ ] **Step 1: silver 모델 작성**

`domains/culture/models/silver/silver_culture_sports_event.sql`:
```sql
-- silver: KBO 서울 홈경기 일정 fact (잠실 LG/두산·고척 키움). 원천 = seed(공개 일정 수기, 월 1회 갱신).
-- 그레인 = (game_date, stadium, game_time) — 더블헤더는 시각으로 구분.
-- 문화행사 축과 분리(sports 구분): gold_culture_location_daily union에 편입하지 않는다.
-- bronze 계보 없음 → source_system='kbo_seed' 상수만.

with placed as (
    select
        s.game_date,
        s.game_time,
        s.stadium,
        s.home_team,
        s.away_team,
        l.gu,
        l.latitude,
        l.longitude
    from {{ ref('kbo_seoul_schedule') }} s
    left join {{ ref('kbo_stadium_location') }} l on l.stadium = s.stadium
),

dong_map as {{ culture_dong_map('placed') }},

gu_codes as (select distinct gu, gu_code from {{ ref('seoul_admin_dong_crosswalk') }})

select
    p.game_date,
    p.game_time,
    p.stadium,
    p.home_team,
    p.away_team,
    try(cast(date_parse(cast(p.game_date as varchar) || ' ' || p.game_time, '%Y-%m-%d %H:%i') as timestamp(6))) as event_at,
    p.longitude, p.latitude, p.gu,
    coalesce(g.gu_code, d.coord_gu_code) as gu_code,
    d.admin_dong, d.admin_dong_code,
    'kbo_seed' as source_system
from placed p
left join dong_map d on p.longitude = d.longitude and p.latitude = d.latitude
left join gu_codes g on g.gu = p.gu
```

- [ ] **Step 2: schema.yml 엔트리 추가**

`domains/culture/models/schema.yml` models 리스트 맨 끝(`gold_culture_movie_boxoffice_daily` 뒤)에 추가:
```yaml
  - name: silver_culture_sports_event
    description: KBO 서울 홈경기 일정 fact (seed 원천, 그레인 game_date×stadium×game_time). 문화행사 축과 분리(sports).
    columns:
      - name: game_date
        tests: [not_null]
      - name: stadium
        tests: [not_null]
      - name: event_at
        description: 경기 시작 시각 (KST, event_time)
        tests: [not_null]
      - name: gu_code
        description: 자치구 코드 (#48 코드 축)
        tests: [not_null]
```

- [ ] **Step 3: 빌드 + 테스트**

Run (헬퍼):
```
dbt run  --select silver_culture_sports_event
dbt test --select silver_culture_sports_event
dbt show --inline "select game_date, game_time, stadium, home_team, away_team, gu, gu_code, admin_dong from {{ ref('silver_culture_sports_event') }} order by game_date" --limit 25
```
Expected: run/test PASS. 표본에서 잠실=송파구 gu_code·고척=구로구 gu_code, admin_dong 채워짐(dong_map 좌표 매칭), event_at not_null.

- [ ] **Step 4: 커밋**

```bash
cd C:/Users/Dell3571/ask-seoul/sample/dbt
git add domains/culture/models/silver/silver_culture_sports_event.sql domains/culture/models/schema.yml
git commit -m "feat(culture): #90 silver_culture_sports_event — seed→축 정렬(gu_code·행정동)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: gold_culture_sports_schedule + AC 실측 + PR

**Files:**
- Create: `domains/culture/models/gold/gold_culture_sports_schedule.sql`
- Modify: `domains/culture/models/schema.yml` (엔트리 추가)

**Interfaces:**
- Consumes: `ref('silver_culture_sports_event')` (Task 3).
- Produces: `gold_culture_sports_schedule` — 경기 1행 질의 표면.

- [ ] **Step 1: gold 모델 작성**

`domains/culture/models/gold/gold_culture_sports_schedule.sql`:
```sql
-- gold: 서울 야구 경기 일정 질의 표면 (경기 1행). "오늘 이후 가장 가까운 경기" =
--   where game_date >= current_date order by event_at limit 1
-- 문화행사 gold(location_daily)와 분리 — 시각·대진 그레인이 필요해 집계하지 않는다.

select
    game_date,
    event_at,
    game_time,
    stadium,
    home_team,
    away_team,
    gu,
    gu_code,
    latitude,
    longitude,
    admin_dong,
    admin_dong_code
from {{ ref('silver_culture_sports_event') }}
```

- [ ] **Step 2: schema.yml 엔트리 추가**

models 리스트 맨 끝(Task 3 silver 엔트리 뒤)에 추가:
```yaml
  - name: gold_culture_sports_schedule
    description: 서울 야구 경기 일정 질의 표면 (경기 1행). 최근접 미래 경기 = game_date>=current_date order by event_at.
    columns:
      - name: game_date
        tests: [not_null]
      - name: event_at
        tests: [not_null]
      - name: stadium
        tests: [not_null]
```

- [ ] **Step 3: 전체 빌드 + AC 실측**

Run (헬퍼):
```
dbt build --select kbo_seoul_schedule+ kbo_stadium_location+
dbt show --inline "select game_date, game_time, stadium, home_team, away_team, gu from {{ ref('gold_culture_sports_schedule') }} where game_date >= current_date order by event_at" --limit 5
```
Expected: build 전부 PASS. AC 질의 첫 행 = 오늘 이후 최근접 경기(검수된 일정과 일치). 이 출력을 PR 본문에 인용.

- [ ] **Step 4: 회귀 안전 확인**

```bash
cd C:/Users/Dell3571/ask-seoul/sample/dbt
git diff --name-only dev...HEAD
```
Expected: 신규 seed 2 + seeds/schema.yml + 테스트 1 + silver 1 + gold 1 + models/schema.yml + dbt_project.yml + 설계/계획 문서만. `gold_culture_location_daily.sql` 등 기존 모델은 목록에 없어야 함.

- [ ] **Step 5: 푸시 + PR 생성**

```bash
cd C:/Users/Dell3571/ask-seoul/sample/dbt
git push -u origin feat/90-culture-kbo-schedule-seed
gh pr create --repo ASAC-DE-bigkk/ASAC-DBT --base dev --head feat/90-culture-kbo-schedule-seed \
  --title "feat(culture): #90 KBO 서울 야구 일정 seed + sports silver/gold" \
  --body "$(cat <<'EOF'
## 요약
KBO 서울 홈경기 일정(7월 잔여분)을 dbt seed로 편입. Closes #90.

- seeds: `kbo_seoul_schedule`(경기 fact, 웹서치 초안→사용자 검수) + `kbo_stadium_location`(구장 위치 dim)
- `silver_culture_sports_event` — 축 정렬(gu_code·행정동), event_at(KST)
- `gold_culture_sports_schedule` — 경기 1행 질의 표면
- 계약: enum(구장/홈팀)·not_null·grain unique(game_date×stadium×game_time, 더블헤더 대비)
- 갱신 규칙: 월 1회 수동(웹서치 초안→검수→CSV 교체), git diff=감사 로그. 8~10월분은 첫 갱신 때 추가.

## 경계
문화행사 축과 분리(sports) — gold_culture_location_daily 무변경, bronze ingest 없음 (fetch 배제 근거: ASAC-DAG#195).

## dev 검증
- dbt build (seed+silver+gold+테스트) 전부 PASS
- AC 실측: "오늘 이후 최근접 서울 경기" 질의 결과 [실측 표 삽입]

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
Expected: PR URL. **머지는 사용자.**

- [ ] **Step 6: dev 복귀**

```bash
cd C:/Users/Dell3571/ask-seoul/sample/dbt
git checkout dev
```

---

## Self-Review

**Spec coverage**: seed CSV 2개+column_types=T1 · seeds yml 계약+grain unique=T2 · 축 정렬 silver=T3 · gold+AC 질의=T4 · 갱신 규칙=설계 문서+PR 본문 · 사용자 검수 게이트=T1 Step 5. 전 항목 커버.

**Placeholder scan**: `<Step2 위도>` 등은 실행 시 웹서치 실측값으로 채우는 소싱 마커(설계가 명시한 절차) — 코드/구조 placeholder 없음.

**Type consistency**: seed 컬럼(game_date date, game_time varchar, stadium, home_team, away_team / stadium, gu, latitude double, longitude double)을 T3 silver가 동일 이름으로 소비, T4 gold는 T3 출력 컬럼만 사용. grain 3컬럼 표기 일관(game_date×stadium×game_time).
