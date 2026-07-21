---
name: dbt-impact-analyzer
description: Use when modifying dbt models in domains/traffic_weather (weather 또는 traffic 서브도메인, 또는 사용자가 change-impact analysis를 요청할 때) — manifest child_map에서 downstream lineage를 결정적으로 추출한 뒤, sub-agent가 컬럼별 breaking 위험을 판정한다. ASAC-DBT#129 traffic_weather 프로토타입.
---

# dbt-impact-analyzer (traffic_weather)

dbt 모델 수정 **전에** downstream 영향을 파악한다. 추출은 스크립트가 결정적으로,
판정은 sub-agent가 SQL 실참조 기준으로 수행한다. 설계:
`domains/traffic_weather/docs/design/2026-07-21-dbt-impact-analyzer-design.md`
(이슈 #129 참조).

`domains/traffic_weather/`는 `models/traffic/`과 `models/weather/` 두 서브도메인을
한 `dbt_project.yml`(=한 manifest)로 묶는다. 따라서 traffic 모델을 수정해도 weather
gold까지, weather 모델을 수정해도 traffic gold까지 **한 번의 스캔으로 downstream이
잡힌다** — 서브도메인 경계는 이 스킬의 추출 범위에 영향을 주지 않는다.

## 환경 노트

- manifest는 dbt 빌드 산출물(`target/` gitignore) — 스크립트가 스킬 위치에서
  traffic_weather 프로젝트 루트를 자동 유도해 `<project-dir>/target/manifest.json`을
  기본 사용한다. 다른 체크아웃의 manifest를 분석할 때만 `--manifest`로 지정.
- 재파싱(빌드 아님, ~1분) — Airflow scheduler 컨테이너에서 실행.
  컨테이너명은 `docker ps --filter name=scheduler`로 확인:
  `docker exec <scheduler-컨테이너> bash -c "cd /opt/airflow/dbt/domains/traffic_weather && /home/airflow/dbt-venv/bin/dbt parse --project-dir . --profiles-dir . --target dev"`
  (Windows Git Bash에서는 경로 변환 방지로 `MSYS_NO_PATHCONV=1` 접두 필요.)
  실행 후 워킹트리가 dev 기준이면 그대로, 다른 브랜치 검증 중이면 해당 브랜치
  파일 기준으로 재생성됨에 유의.

## 워크플로 (순서 고정)

1. **수정 대상 식별**: `git diff --name-only dev` + unstaged에서
   `domains/traffic_weather/models/**/*.sql|yml` 추출. diff가 없으면 사용자가 지목한
   모델을 사용(가정 시나리오 분석 허용 — 이때 리포트에 "가정" 명시).
2. **추출**: `PYTHONIOENCODING=utf-8 python <이 스킬 디렉토리>/scripts/impact_map.py
   --model <names>` (manifest는 기본 경로 자동 사용 — 환경 노트 참조).
   `manifest.stale == true`면: 경고 표시(stale_files 목록) → 사용자에게 재파싱
   (환경 노트 커맨드) 승인을 물은 뒤, 승인 시 재파싱+재추출, 거절 시
   리포트에 "stale manifest 기준" 명시하고 진행.
3. **임계값 게이트**: 리포트 `gate.exceeded == true`(대상 모델 downstream
   union·테스트 제외 > **10**, `--threshold`로 조정 가능)면 자동 진행 금지 —
   AskUserQuestion으로 ①대상 모델 축소 ②`--max-depth` 제한
   ③전체 계속 중 선택받는다. 실측: `silver_seoul_traffic_incident`(17)와
   `silver_kma_vilage_fcst_observation`(19)은 direct fanout만으로도 게이트가
   발동한다(union 35, depth 확장 불필요).
4. **변경 유형 분류**: 대상 모델 SQL·yml diff(가정 시나리오면 사용자 서술)에서
   컬럼 추가 / 컬럼 삭제 / 타입 변경 / 로직 변경(스키마 불변)을 구분하고,
   삭제·타입 변경된 컬럼명 목록을 확정한다.
5. **sub-agent 실참조 분석** (컬럼 삭제·타입 변경이 있을 때만): downstream 모델별로
   Agent tool 병렬 dispatch. 각 agent 입력은 (모델 SQL 워킹트리 경로, 변경 컬럼
   목록, upstream 모델명)만 — 세션 히스토리 전달 금지. agent는 SQL을 읽고
   컬럼별 판정만 반환: `명시 참조`(select/join/where/group by에 등장) /
   `select * 전파` / `미참조`.
6. **리포트**: 아래 템플릿. breaking 1건이라도 있으면 ⚠️ 블록 최상단.

## 판정 규칙 (governed)

| 판정 | 조건 |
|---|---|
| breaking | 삭제/타입 변경 컬럼을 downstream이 명시 참조 또는 `select *` 전파 |
| warn | 로직 변경(스키마 불변, 값 변화 가능) — downstream `attached_tests` 수 첨부(전체 589개로 두터움) |
| non-breaking | 컬럼 추가, 삭제/변경 컬럼을 downstream이 미참조 |

traffic_weather는 dbt native contract enforced 모델이 0건이다(`contracts/traffic/`,
`contracts/weather/`의 `public-gold-ai-contract-v1.md`는 문서 수준 계약). 따라서
breaking 판정은 sub-agent 실참조 분석에만 의존한다 — `contract_enforced` 필드는
항상 False로 나오며 판정에 영향을 주지 않는다.

## 실측 예시 (검증 완료)

`silver_seoul_traffic_incident.acc_type`(사고 유형) 삭제 가정 시, 명시 참조로
확인된 downstream 4종: `gold_traffic_incident_active_latest`,
`gold_traffic_incident_clearance_watchlist`, `gold_traffic_incident_type_mix_latest`,
`gold_traffic_incident_x_flow` — 전부 ⚠️ BREAKING. 나머지 downstream 13개는
`acc_type`을 참조하지 않아 non-breaking.

## 리포트 템플릿

    ## 영향 분석: <model> (<변경 유형>)
    ⚠️ BREAKING: <n>건 — <모델 목록>        ← breaking 있을 때만, 최상단

    | downstream | depth | 영향 유형 | 참조 방식 | 위험도 | 비고 |
    |---|---|---|---|---|---|
    | gold_traffic_incident_active_latest | 1 | 직접 참조 | 명시(acc_type) | breaking | - |
    | gold_traffic_incident_x_flow | 2 | 간접 전파 | select * | warn | 테스트 4개 |

    manifest: <generated_at> (stale 여부) · downstream 합계 <n> (테스트 제외)

- 영향 유형: depth=1 → 직접 참조, depth>=2 → 간접 전파
- 비고: attached_tests 수, 가정 시나리오 여부

## 한계 (프로토타입)

- traffic_weather 프로젝트 한정 — 루트 승격은 #129 본안(멘토 게이트)
- **크로스 도메인 미탐지**: 도메인별 독립 dbt 프로젝트라 traffic_weather manifest 밖의
  참조는 downstream에 잡히지 않는다. 우리 도메인은 반대로 **자체 gold 레이어가 타
  도메인을 조인**하는 마트를 다수 보유한다(`gold_traffic_incident_x_citydata_*`,
  `gold_traffic_incident_x_culture_*`, `gold_weather_x_citydata_*`,
  `gold_weather_x_commerce_*`, `gold_weather_x_culture_*`, `gold_weather_x_transit_*`).
  즉 우리가 참조하는 타 도메인 소스가 바뀌어도 그 변경은 우리 manifest 밖이라
  탐지되지 않는다. 타 도메인까지 보려면 전 도메인 manifest 순회가 필요(루트 승격
  설계 논점).
- raw SQL 기준 실참조 판정(compiled 미사용) — dbt_utils 매크로가 컬럼을 숨기는
  경우 sub-agent가 `매크로 경유 가능`으로 보고하고 사람 확인 요청
- exposure 노드 추적 없음
