# Weather dbt AI index

이 디렉터리는 KMA Weather의 `normal` 변환과 승인된 `special` W1/W2 흐름을 소유한다.
컬럼 의미, generic test, public Gold metadata의 단일 source of truth는 각 SQL 옆 YAML이다.

## 입력과 구조

- Bronze source: [`sources.yml`](sources.yml)
- Weather seed 계약: [`../../seeds/weather/_weather_inputs.yml`](../../seeds/weather/_weather_inputs.yml)
- normal Silver/Gold/place mart: [`transform/`](transform/)
- special W1 bridge: [`special/w1/`](special/w1/)
- special W2 Silver/Gold: [`special/silver/`](special/silver/), [`special/gold/`](special/gold/)
- special W2 recovery 검증: [`special/recovery/`](special/recovery/)
- singular tests: [`../../tests/weather/`](../../tests/weather/)
- phase 설정: [`../../dbt_project.yml`](../../dbt_project.yml)

## 실행 tag

| 흐름 | direct tag |
| --- | --- |
| normal Silver | `ask_seoul_weather_transform_silver` |
| normal Gold | `ask_seoul_weather_transform_gold` |
| normal place mart | `ask_seoul_weather_transform_place_mart` |
| W1 bridge model/test | `ask_seoul_weather_w1_bridge` |
| W1 seed 5종 | `ask_seoul_weather_w1_inputs` |

`ask_seoul_weather_w1_inputs`는 asac_axes seed 3종과 Weather seed 2종만 소유한다.
W1 bridge tag는 bridge 모델과 지정된 singular test 5개에만 직접 부여한다.
나머지 special W2 모델·test는 이 두 W1 tag를 갖지 않는다.
W2 recovery workset은 `bounded_reconcile`과 dev target에서만 명시적으로 실행하는 내부 검증 산출물이다.

## Public producer

- `gold_weather_forecast_by_admin_dong`만 Weather의 `published_producer`다.
- SQL: [`special/gold/gold_weather_forecast_by_admin_dong.sql`](special/gold/gold_weather_forecast_by_admin_dong.sql)
- 계약: [`special/gold/gold_weather_forecast_by_admin_dong.yml`](special/gold/gold_weather_forecast_by_admin_dong.yml)
- normal 호환 Gold/place mart와 special Silver/W1 bridge는 도메인 내부 구현이다.

## cross-domain ref 규칙

다른 group·package는 `access: public`인 producer만 명시적 package ref로 소비한다.

```sql
{{ ref('asac_seoul', 'gold_weather_forecast_by_admin_dong') }}
```

Weather 내부 Silver, place mart, W1 bridge를 cross-domain ref 대상으로 사용하지 않는다.
공개 의미 계약과 검증 명령은 [`../../domains/weather/contracts/docs/public-gold-ai-contract-v1.md`](../../domains/weather/contracts/docs/public-gold-ai-contract-v1.md)를 따른다.
