# culture KBO 서울 야구 일정 seed 설계 (#90)

**이슈**: [ASAC-DBT#90](https://github.com/ASAC-DE-bigkk/ASAC-DBT/issues/90)
**작성일**: 2026-07-10 · **브랜치**: `feat/90-culture-kbo-schedule-seed` (dev 기준)
**범위**: seed 2개 + silver `silver_culture_sports_event` + gold `gold_culture_sports_schedule` + 계약/테스트 + 갱신 운영 규칙.
**배경**: ASAC-DAG#195 종결 — 미래 경기 fetch의 합법 경로 없음(잠실 robots 전면금지, 토토 API는 종료 14일 후, SportAPI는 대관 그레인). KBO 시즌 일정 = 시즌 초 확정·공개 사실(비저작물) → **dbt seed**.

## 목표 질의 (AC)

**"오늘 이후 가장 빠른 서울 야구 경기"** — gold에서
`where game_date >= current_date order by event_at limit 1` 로 답한다.

## 원칙

- **문화행사 축과 분리**: 야구는 공연·전시·영화와 그레인 이질 → sports 구분 모델로만.
  `gold_culture_location_daily`(문화행사 union) **무변경**.
- **bronze ingest 없음**: seed가 유일한 원천. culture 스키마 밖 미기재.
- **선례 정합**: 위치는 별도 seed(`sejong_location` 패턴), 축 정렬(dong_map·gu_code)은
  silver 소관, gold는 소비만.

## 데이터 소싱 (사용자 확정: 웹서치 초안 + 검수, 샘플 기간 우선)

- **초안**: 웹서치(뉴스·포털 등 공개 소스)로 작성 — KBO 공홈 직접 크롤은 robots 금지(#195 기준)라
  하지 않는다. 사람이 공개 일정을 옮겨 적는 것은 robots와 무관.
- **검수**: 사용자가 KBO 공홈/앱과 대조 스팟체크 후 확정.
- **범위**: **2026년 7월 잔여분**(~20경기)부터. 8~10월분은 첫 월간 갱신에서 추가.
- 학습 지식으로 일정을 쓰지 않는다(할루시네이션 방지) — 반드시 웹서치 결과에서만.

## Seeds (2개)

### `seeds/kbo_stadium_location.csv` — 구장 위치 차원 (2행)

```
stadium,gu,latitude,longitude
잠실야구장,송파구,<웹서치 실측>,<웹서치 실측>
고척스카이돔,구로구,<웹서치 실측>,<웹서치 실측>
```

좌표는 구현 시 웹서치로 확인해 기입(설계 문서에 박지 않음 — 초안 값 오염 방지).

### `seeds/kbo_seoul_schedule.csv` — 경기 일정 fact

```
game_date,game_time,stadium,home_team,away_team
2026-07-10,18:30,잠실야구장,LG,<원정팀>
...
```

- `game_date`: YYYY-MM-DD · `game_time`: HH:MM (KST) · `home_team`: 서울 연고(LG/두산/키움).
- `dbt_project.yml`: `kbo_seoul_schedule: {+column_types: {game_date: date}}`,
  `kbo_stadium_location: {+column_types: {latitude: double, longitude: double}}`.

## 계약 (schema.yml `seeds:` 섹션 + singular test)

- `kbo_seoul_schedule`: `game_date`·`game_time`·`stadium`·`home_team` not_null ·
  `stadium` accepted_values [잠실야구장, 고척스카이돔] ·
  `home_team` accepted_values [LG, 두산, 키움]
- `kbo_stadium_location`: `stadium` not_null·unique, `gu`·`latitude`·`longitude` not_null
- singular `assert_kbo_schedule_grain_unique.sql`:
  **grain = game_date × stadium × game_time** 중복 0 — 더블헤더(같은 날 2경기)가 있어
  시각까지 포함해야 유일.

## silver — `silver_culture_sports_event`

**그레인**: 경기 1행 (= seed grain).

- schedule ⨝ stadium(위치 seed) → `gu, latitude, longitude`
- `culture_dong_map` + `seoul_admin_dong_crosswalk` 로 `gu_code`·`admin_dong`·`admin_dong_code`
  (sejong silver 패턴).
- `event_at = cast(game_date + game_time as timestamp(6))` (KST, #48 `_at`=event time).
- 계보: 원천이 seed(내부 사실)라 bronze 계보 컬럼 없음 — `source_system='kbo_seed'` 상수만.
  문화행사 union(`gold_culture_location_daily`)에 **편입하지 않음**.

## gold — `gold_culture_sports_schedule`

**그레인**: 경기 1행. silver 통과(집계 없음 — 질의 표면).

컬럼: `game_date, event_at, game_time, stadium, home_team, away_team, gu, gu_code,
latitude, longitude, admin_dong, admin_dong_code`.

- AC 실측: `select * from gold_culture_sports_schedule where game_date >= current_date
  order by event_at limit 1` 이 다음 경기를 반환.
- schema.yml: `game_date`·`stadium`·`event_at` not_null.

## 갱신 운영 규칙 (월 1회 수동)

1. 매월 초(또는 편성 변경 인지 시): 웹서치 초안 → 사용자 KBO 공홈 대조 검수 → CSV 갱신.
2. 우천 취소·더블헤더 재편성은 이 루틴이 흡수. seed 전체 교체(append 아님) — dbt seed 는
   full-refresh 성격이라 CSV = 진실 원천.
3. **git diff = 변경 감사 로그** (누가·언제·무엇을 바꿨는지 PR로 남음).
4. 다음 갱신(8월 초)에서 8~10월 잔여 시즌 추가.

## 완료 조건 (이슈 AC 대응)

- [ ] dbt parse/compile 통과
- [ ] dbt test 통과 (seed 계약 + grain unique)
- [ ] culture 스키마 밖 미기재
- [ ] "오늘 이후 가장 가까운 서울 야구 경기" 질의 gold 실측 (dev)
