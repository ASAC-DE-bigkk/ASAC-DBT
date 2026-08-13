# 현재 전망 기본 시간창 경계 보정 설계

## 목적

`weather_place_current_outlook.outlook_forecast_window`를 파라미터 없이 호출해도 매시 정각에 게시된 현재 전망 스냅샷을 반환하도록 한다.

## 문제와 증거

- Gold는 `snapshot_as_of_hour` 이상에서 가장 가까운 `forecast_at` 한 행을 장소별로 게시한다.
- Worker는 `{rel: "0d", as: datetime}`을 KST 호출 순간의 시·분·초로 해석한다.
- 02:19 KST 기본 호출에서는 `forecast_at=02:00`인 427행이 모두 하한 밖으로 밀려 0행이 됐다.
- 같은 게시본에 `from_at=2026-08-14` 또는 `from_at=2026-08-14 02:00:00`을 명시하면 100행이 반환됐다.

## 결정

- 이 패턴의 `from_at` 기본값만 `{rel: "0d", as: date}`로 바꾼다.
- 기본 하한은 KST 오늘 00:00이 되어 정각 스냅샷을 포함한다.
- 사용자가 명시적으로 넘긴 `from_at`은 Worker 기본값 해석을 거치지 않으므로 기존 분·초 단위 의미를 유지한다.
- 전역 Worker 상대시간 규칙과 다른 Weather·Traffic 패턴은 변경하지 않는다.

## 재발 방지

- Weather 계약 테스트에서 02:19 KST 기준으로 기본값을 해석하고 02:00 스냅샷 행이 실제 SQLite 실행에서 반환되는지 확인한다.
- `pattern_hygiene`가 `weather_place_current_outlook`의 미래 시간축 하한을 다시 `0d datetime`으로 생성하지 않도록 정책 테스트를 두고, `weather_grid_current_outlook`은 기존 datetime 정책을 유지하는지 함께 확인한다.
- 운영 재게시 후 인증된 기본 패턴 호출이 `row_count > 0`인지 확인한다.

## 영향과 롤백

- 변경 대상은 DBT serving metadata와 그 회귀 테스트뿐이다.
- Gold grain, D1 스키마, Worker, DAG 스케줄, Traffic, Compose와 캐시는 바뀌지 않는다.
- 문제가 생기면 해당 기본값 한 줄을 `as: datetime`으로 되돌리고 이전 last-known-good 게시본을 유지할 수 있다.
