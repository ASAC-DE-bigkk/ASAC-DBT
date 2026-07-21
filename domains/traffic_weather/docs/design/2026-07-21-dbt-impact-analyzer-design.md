# dbt-impact-analyzer — 변경 영향 분석 Claude 스킬 (traffic_weather)

2026-07-21 · traffic_weather 도메인(weather+traffic) · 이슈 ASAC-DBT#129(멘토 발제, infra 스코프)의 traffic_weather 범위 프로토타입

## 배경 / 왜

dbt 모델 수정 시 downstream 영향을 수동 lineage 추적에 의존하거나 확인하지 않아,
컬럼 삭제/타입 변경/로직 변경의 전파로 downstream이 깨질 위험이 있다(#129 문제 정의).
manifest.json의 `child_map` 기반으로 수정 모델의 downstream을 자동 추적·분석하는
Claude 스킬을 만든다.

**프로토타입 전략**: #129의 도메인 필드는 infra — 레포 루트 `.claude/skills/` 배치는
공유 인프라 변경이라 멘토 게이트 대상. 따라서 **traffic_weather 소유 경로에 먼저
구현·검증**하고, 결과를 #129에 코멘트로 링크해 루트 승격을 제안한다. #129 자체는
닫지 않는다(멘토 소유).

traffic_weather 실측 근거(2026-07-21 manifest, dbt 1.10.22, 컨테이너 `dbt parse`):
- 자체 패키지(`asac_seoul`) 모델 59 + seed 2, 테스트 589 — 두터운 테스트 커버리지가
  downstream 참조 판정(attached_tests)의 신뢰도를 뒷받침한다.
- `child_map` 완비, fanout 최대 19(`silver_kma_vilage_fcst_observation`).
- manifest 소재: 컨테이너 빌드 산출물(`target/` gitignore) — 신선도 판정이 구조적으로
  필요하다.

## traffic_weather 스킬의 강점

1. **단일 프로젝트가 두 서브도메인을 함께 커버**: `domains/traffic_weather/`는
   `models/traffic/`과 `models/weather/`를 한 `dbt_project.yml`(=한 manifest)로 묶는다.
   즉 traffic 모델을 수정해도 weather gold까지, weather 모델을 수정해도 traffic gold까지
   **한 번의 스캔으로 downstream을 커버**한다 — 서브도메인 경계를 넘나드는 변경 영향을
   놓치지 않는다.
2. **임계값 게이트가 실사례로 자연 발동**: `silver_seoul_traffic_incident`(direct
   downstream 17개), `silver_kma_vilage_fcst_observation`(19개) 모두 threshold(10)를
   depth 확장 없이 1단계 fanout만으로 초과한다. 인위적으로 만든 시나리오가 아니라
   실제 운영 중인 모델로 게이트 동작을 검증할 수 있다.
3. **재현 가능한 breaking 시나리오를 실측으로 검증**: `silver_seoul_traffic_incident.acc_type`
   컬럼을 삭제하는 가정으로 downstream 17개 전체를 실제 판정한 결과 breaking 5건 —
   depth 1의 `silver_seoul_traffic_incident_current`(`select history.*` 전체 컬럼 전파)와
   depth 2~3에서 `acc_type`을 명시 참조하는 gold 4종(`gold_traffic_incident_active_latest`,
   `gold_traffic_incident_clearance_watchlist`, `gold_traffic_incident_type_mix_latest`,
   `gold_traffic_incident_x_flow`). 중간 모델의 select * 전파를 함께 추적해야 breaking을
   과소 집계하지 않는다는 것까지 실측으로 확인했다.
4. **크로스 도메인 조인 마트가 이미 풍부**: `gold_traffic_incident_x_citydata_*`,
   `gold_traffic_incident_x_culture_*`, `gold_weather_x_citydata_*`,
   `gold_weather_x_commerce_*`, `gold_weather_x_culture_*`, `gold_weather_x_transit_*` 등
   타 도메인을 조인하는 gold 마트를 다수 보유한다. 향후 크로스 도메인 lineage 확장(루트
   승격 논의)이 실제로 필요해질 실사용 사례가 풍부하다는 뜻이다.

## 결정 사항

1. **배치**: `domains/traffic_weather/.claude/skills/dbt-impact-analyzer/` — 레포 내
   traffic_weather 소유 경로. 커밋·PR로 팀에 공유 가능, Claude Code가 디렉토리 스코프
   스킬로 인식.
2. **엔진**: 스크립트+스킬 하이브리드 — Python 스크립트가 child_map BFS를 결정적으로
   수행, SKILL.md가 그 결과 위에서 sub-agent 의미 분석(실참조·breaking 판정)을 수행한다.
   순수 프롬프트 방식은 매번 대용량 manifest를 토큰으로 파싱해 누락 위험이 있고, 순수
   CLI만으로는 실참조 분석이 빠져 #129 AC를 충족하지 못한다.
3. **신선도**: 스크립트가 stale 판정(경고)만 하고, 재파싱은 SKILL이 컨테이너
   `dbt parse`(~10초, 빌드 아님)로 **제안 후** 진행한다. 무조건 재파싱은 컨테이너 기동을
   전제조건으로 만들어 배제한다.
4. **임계값**: `--threshold` 인자로 조정 가능한 게이트를 스크립트 코드 레벨에서 강제한다
   (기본값 10). 초과 시 SKILL이 자동 진행을 멈추고 사용자에게 범위 축소/depth 제한/전체
   진행 중 선택지를 제시한다.

## 산출물 구조

```
domains/traffic_weather/.claude/skills/dbt-impact-analyzer/
├── SKILL.md                     # 트리거 조건 + 6단계 분석 워크플로
└── scripts/
    ├── impact_map.py            # manifest child_map BFS 추출기 (stdlib only)
    └── test_impact_map.py       # pytest — 픽스처 미니 manifest
```

## 검증 시나리오 (실측 기반)

### 게이트 발동 (non-breaking, 임계값 초과)

`silver_seoul_traffic_incident` 또는 `silver_kma_vilage_fcst_observation` 대상 —
direct downstream이 각각 17/19개로 threshold(10)를 초과. `gate.exceeded=true` 발동을
실측 확인한다.

### Breaking 시나리오

`silver_seoul_traffic_incident.acc_type`(사고 유형 컬럼) 삭제 가정.
downstream 17개 전체를 판정해 breaking 5건 확인:
`silver_seoul_traffic_incident_current`(depth 1, `select history.*` 전파),
`gold_traffic_incident_active_latest`, `gold_traffic_incident_clearance_watchlist`,
`gold_traffic_incident_type_mix_latest`, `gold_traffic_incident_x_flow`(depth 2~3,
`acc_type` 명시 참조). 나머지 12개는 non-breaking/미참조로 판정됨을 검증했다.

### Non-breaking 시나리오

컬럼 추가 케이스 1건 — 항상 non-breaking으로 판정되는지 확인한다.

## 한계 (프로토타입)

- traffic_weather 프로젝트 한정 — 루트 승격은 #129 본안(멘토 게이트).
- **크로스 도메인 미탐지**: 도메인별 독립 dbt 프로젝트라 traffic_weather manifest 밖의
  참조(다른 도메인이 우리 마트를 참조하는 경우, 혹은 우리가 참조하는 타 도메인 소스가
  바뀌는 경우)는 downstream/upstream에 잡히지 않는다. 타 도메인까지 보려면 전 도메인
  manifest 순회가 필요하다(루트 승격 설계 논점).
- Contract enforced 모델이 0건이라, breaking 판정이 sub-agent 실참조 분석에만 의존한다.
  `contracts/traffic/`, `contracts/weather/`의 `public-gold-ai-contract-v1.md`는 문서
  수준 계약이며 dbt native contract가 아니다.
- raw SQL 기준 실참조 판정(compiled 미사용) — dbt_utils 매크로가 컬럼을 숨기는 경우
  sub-agent가 "매크로 경유 가능"으로 보고하고 사람 확인을 요청한다.
- exposure 노드 추적 없음.

## 다음 단계

- PR 본문에 `#129`를 참조로 명시해 진행 상황을 투명하게 남긴다.
- 검증 완료 후 #129에 코멘트로 링크해 루트 승격 논의 자료로 제공한다.
