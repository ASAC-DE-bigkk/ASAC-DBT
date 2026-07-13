# Traffic canonical Gold·freshness dev 실행 회고 (#172)

## 결론

Traffic 사용자용 canonical Gold
`gold_traffic_incident_current_by_admin_dong_hourly`를 회사 로컬 dev
Docker/Airflow/Trino/Iceberg 환경의 격리 schema에서 실행했다. 최신 complete publishable
snapshot 1개를 고정해 `admin_dong_code × hour_at` 426행을 게시했고, 실제 snapshot의 사고
6건과 canonical 행정동 426개를 fan-out 없이 대사했다. 정상 0건은 complete 근거가 있는
`complete_zero`에서만 0으로 게시됐고, partial·API failure·missing에서는 사고 건수를 null로
유지했다.

이 문서의 시간·row·byte 수치는 **실제 클라우드 비용 또는 청구액이 아니라 dev 실행 비용
대리 지표**다. 기존 source-level 요약 Gold와 새 사용자용 canonical Gold는 grain과 역할이
달라 완전한 동종 비교가 아니며, 수치는 상대적인 실행 특성을 파악하는 용도로만 해석한다.

Issue #172의 dbt Traffic 범위는 검증했지만, 실행 중인 DAG checkout의 환경변수 계약과
Weather 소유 테스트 정리는 이 저장소의 Traffic 전용 파일 경계 밖이어서 후속 blocker로
남겼다. 따라서 이 PR은 Issue #172를 자동 종료하지 않는다.

## 검증한 계약

- Gold grain은 `admin_dong_code × hour_at`이다. `hour_at`은 사고 발생 시각이 아니라 서울
  기준 snapshot 평가 시각의 hour bucket이다.
- 변환 시작 시 `traffic_snapshot_dag_run_id`로 고정한 최신 complete publishable snapshot만
  사용자 사고 건수의 근거로 사용한다.
- 행정동 universe, 이름, 구 코드·이름, revision stamp는 외부 canonical
  `asac_axes.dim_admin_dong`만 사용한다. 이름 추정, 좌표 추정, self-copy fallback은 없다.
- GRS80 TM 원천 좌표를 WGS84 위경도로 해석하지 않는다. Gold는 Silver의 canonical
  행정동 코드 후보만 exact join한다.
- `complete`와 `complete_zero`에서만 `incident_count`와 `has_incident`를 게시한다.
  `missing`, `partial`, `api_failure`, `current_mismatch`,
  `spatial_mapping_incomplete`에서는 두 필드를 null로 둔다.
- 기존 `gold_traffic_incident_summary`와 recovery 모델의 의미·materialization·결과를
  변경하지 않는다.
- freshness는 `collection_run_manifest.event_at`에만 적용한다. incident와 request-audit
  source freshness는 계속 null이다.
- 기본 freshness는 warn 15분 / error 30분이며,
  `ASK_SEOUL_REPORT_TRAFFIC_FRESHNESS_WARN_MINUTES`와
  `ASK_SEOUL_REPORT_TRAFFIC_FRESHNESS_ERROR_MINUTES`로 DAG와 같은 override 계약을 사용한다.
  검증은 raw YAML 문자열 비교가 아니라 `dbt parse`의 resolved manifest를 대상으로 한다.

## 실행 환경과 증적 ledger

| 항목 | 값 |
| --- | --- |
| 실행일 | 2026-07-14 KST |
| branch | `fix/172-traffic-freshness-slo-contract` |
| base | `dev` |
| dbt | dbt-core 1.10.22 / dbt-trino 1.10.2 |
| Trino | 482 |
| catalog | `iceberg_dev` |
| 실제 데이터 격리 schema | `dev_masondev1024_traffic_contract_test_710e380aac8649f394088889` |
| fixture target schema | `dev_masondev1024_traffic_contract_test_73bff83545c34f11b95e2123` |
| fixture source schema | `dev_masondev1024_traffic_fixture_src_7a69c9a56e584b00bd7d0060` |
| 고정 snapshot DAG run | `scheduled__2026-07-13T18:20:00+00:00` |
| snapshot manifest 근거 | expected/actual row 6/6, expected/actual object 1/1 |
| public evidence id | `traffic172-20260714-actual-710e380a` |
| canonical Gold dbt invocation | `22f90998-c5bd-4baf-aaa1-453bc36f12c3` |
| 기존 Gold dbt invocation | `36179181-919c-4285-b85a-1a9e3c8073f9` |
| docs catalog invocation | `f24200f4-7d7b-4306-929f-e1715c294f07` |

실행 전 세 격리 schema가 존재하지 않음을 확인했다. prod catalog, prod schema, prod bucket,
prod schedule은 사용하지 않았다. 검증 schema teardown은 destructive delete 금지 원칙에 따라
실행하지 않았으며 수동 정리 대상으로 보존했다.

## 명령 및 판정

| 영역 | 실행 명령 또는 검증 | 결과 | 판정 |
| --- | --- | --- | --- |
| dependency | `dbt deps` | local `asac_axes` dependency 해석 | PASS |
| 기본 설정 | `dbt parse --target dev --no-partial-parse` | warn 15분 / error 30분, incident·audit freshness null | PASS |
| override | warn 21분 / error 42분 환경변수로 fresh parse | resolved manifest 21/42분 | PASS |
| graph 계약 | `validate_singular_test_dependency_manifest.py` | singular test 의존성·selector 계약 충족 | PASS |
| source 계약 | Traffic source linter·YAML uniqueness·description coverage | 20/20 description, 중복 0 | PASS |
| public manifest | public manifest validator | evidence ledger와 invocation 일치 | PASS |
| compile | 대상 Gold `dbt compile --target dev` | 고정 snapshot 변수로 compile | PASS |
| freshness | dev `dbt source freshness` | `collection_run_manifest` freshness 통과 | PASS |
| Python 계약 | ephemeral Airflow 컨테이너 `pytest` | 최초 120 passed / 266 subtests, 최종 fresh Linux 120 passed / 266 subtests | PASS |
| Windows 보조 실행 | Windows host에서 같은 `pytest` | symlink 생성 권한 오류 11건, 109 passed / 253 subtests | FAIL (환경) |
| seed | boundary 423 / crosswalk 420 / gu 25 | 동일 evidence ledger로 seed 완료 | PASS |
| upstream run | dim + Silver + current | Silver 6행, current 6행 | PASS |
| 기존 Gold run | `gold_traffic_incident_summary` | 1행, incident 6건 | PASS |
| canonical Gold run | `gold_traffic_incident_current_by_admin_dong_hourly` | 426행, incident 합계 6건 | PASS |
| current 가용성 | current availability selector | 1/1 | PASS |
| 기존 Silver selector | DAG parity selector | 35/35 | PASS |
| 기존 Gold selector | 기존 Traffic Gold selector | 8/8 | PASS |
| canonical Gold test | fresh parse artifact와 동일 target로 대상 test | 25/25 | PASS |
| Weather 소유 교차 테스트 | `pytest domains/weather/tests/test_source_freshness_slo.py -q` | raw YAML literal assertion 1건 실패 | FAIL (범위 blocker) |
| physical catalog | `dbt docs generate` + approved catalog 비교 | 선언·physical contract 차이 0 | PASS |
| recovery run/test | recovery selector | Silver 7행, metadata 1행, Gold 1행; 17/17 | PASS |
| fixture 상태 | partial / complete_zero / api_failure / missing | 각 상태 run 및 snapshot·zero test 통과 | PASS |
| stale 음성 검증 | stale fixture `dbt source freshness` | 의도한 `ERROR STALE`, non-zero exit 확인 | PASS |
| scope | tracked diff와 untracked 회고를 합산한 범위 검사 | 변경 21개, Traffic 밖 0개 | PASS |
| whitespace | `git diff --check` | 오류 0 | PASS |
| secret 휴리스틱 | 변경 파일의 private key·provider token·literal secret 패턴 검사 | hit 파일 0개, 값 출력 없음 | PASS |
| 전용 secret scanner | `gitleaks`, `trufflehog` | 로컬 실행 파일 없음 | NOT_RUN |
| prod/full refresh/backfill | prod 접근, `--full-refresh`, 대량 backfill | 안전 정책상 실행하지 않음 | NOT_RUN |
| merge | PR merge | 사용자 검토 전 실행하지 않음 | NOT_RUN |

### 재시도와 실패 이력

최종 판정만으로 실행 마찰을 숨기지 않기 위해 재시도도 기록한다.

- source linter 첫 실행은 출력 parent directory가 없어 실패했다. Traffic 내부
  `domains/traffic/target/contracts`를 만든 뒤 같은 검사로 PASS했다.
- ephemeral 컨테이너 pytest는 첫 실행의 shell quoting 오류와 두 번째 실행의 14초 command
  timeout 뒤, 올바른 quoting과 timeout으로 세 번째 실행에서 PASS했다. pytest는 ephemeral
  컨테이너에만 설치했고 repo 또는 실행 image를 변경하지 않았다.
- PR 직전 fresh Windows host 실행은 symlink 생성마다 `WinError 1314`가 발생해 11건이
  실패했고 109건은 통과했다. 같은 commit의 같은 전체 suite를 Linux ephemeral 컨테이너로
  다시 실행해 120 passed, 266 subtests passed를 확인했다. 최초 Linux 증적은 63.05초,
  fresh 최종 증적은 199.60초였다. Windows 실패는 assertion 결과가 아니라 host의 symlink
  권한 제약이며 코드로 우회하지 않았다.
- fresh Linux 컨테이너 첫 시도는 Airflow image의 기본 entrypoint 때문에 `/bin/bash`가
  Airflow subcommand로 해석됐다. `--entrypoint /bin/bash`를 명시한 다음 실행에서 전체
  suite가 PASS했다.
- seed 첫 실행은 shell timeout 이후 2개 seed가 생성된 상태였다. relation을 확인하고 같은
  격리 schema·같은 evidence ledger로 명시 재실행해 PASS했다.
- `dbt test --select <canonical-model>`을 fresh target에 바로 실행하면 dbt 1.10.22가
  `Nothing to do`를 반환했고 wildcard generic selection은 dependency inference compile error
  17건을 냈다. `dbt parse --no-partial-parse`로 authoritative graph를 만든 뒤 **같은 target
  path**를 재사용한 동일 모델 selection은 25/25 PASS했다. 데이터 실패가 아니라 parse
  artifact/selection command shape 문제이며 배포 통합 위험으로 남긴다.
- 기존 Silver selector도 진단용 `--no-partial-parse` 직접 조합에서 dependency inference
  compile error가 났지만, 실제 DAG와 같은 parse/selector command shape는 35/35 PASS했다.
- PR 직전 fresh dbt chain의 첫 compile은 Compose와 달리 `docker run --env-file`이 catalog의
  따옴표를 보존해 `""iceberg_dev""`라는 잘못된 identifier를 만든 탓에 실패했다. 실행 중인
  dev scheduler의 비밀이 아닌 Trino 식별자 설정만 명시해 이 환경 차이를 제거했다.
- 다음 compile은 PowerShell→Docker→bash 경계에서 `--vars` JSON 따옴표가 손실되어 필수
  var가 잘못 해석됐다. script를 base64로 전달해 인자 원문을 보존한 세 번째 fresh chain에서
  `dbt deps`, no-partial parse, 대상 compile, 대상 test 25/25가 연속 PASS했다.
- 최종 읽기 전용 대사 SQL의 첫 실행은 dim revision과 기존 summary count 컬럼명을 잘못
  추정해 실패했다. `DESCRIBE`로 실제 컬럼을 확인한 뒤 재조회해 canonical 426행, 사고 6건,
  invalid zero 0, stamp mismatch 0, 기존 summary·recovery 각 6건을 재확인했다.

## canonical Gold 데이터 결과

실제 dev snapshot 결과는 다음과 같다.

| 검증 항목 | 결과 |
| --- | ---: |
| Gold row | 426 |
| distinct grain | 426 |
| distinct `product_row_id` | 426 |
| 평가 hour bucket | 1 |
| canonical dimension exact match | 426 |
| canonical stamp mismatch | 0 |
| `incident_count` 합계 | 6 |
| current incident row | 6 |
| complete 상태 0건 cell | 420 |
| complete 근거 없는 0건 | 0 |
| complete 외 non-null count | 0 |
| unmapped current incident | 0 |
| `snapshot_as_of_at` | `2026-07-14 03:20:19.210554` KST |
| `status_observed_at` | `2026-07-14 03:20:56.622213` KST |

`Gold row = distinct grain = distinct product_row_id = canonical 행정동 수`이고 사고 합계가
current 6행과 일치하므로 행정동 scaffold join의 누락·중복·fan-out은 없었다.

## 상태별 fixture 결과

| 시나리오 | Gold 상태 | 행 수 | count 결과 | 해석 |
| --- | --- | ---: | --- | --- |
| 최신 complete, 사고 6건 | `complete` | 426 | 합계 6, 0건 cell 420 | 게시 가능 |
| complete, 정상 사고 0건 | `complete_zero` | 426 | 전 행 0 | complete 근거가 있을 때만 0 허용 |
| partial audit | `partial` | 426 | 전 행 null | 0건으로 오해하지 않음 |
| API failure | `api_failure` | 426 | 전 행 null | 실패를 사용자 수치로 게시하지 않음 |
| manifest 부재 | `missing` | 426 | 전 행 null | 데이터 부재를 정상 0건과 분리 |
| stale manifest | source freshness error | 해당 없음 | `ERROR STALE` | freshness gate가 실패를 드러냄 |

fixture incremental history가 남은 상태에서도 complete-zero, API failure, missing의 최신 상태가
각각 정확히 선택됐다.

## 비용 대리 지표

비교 기준은 기존 source-level 운영 요약 Gold와 새 canonical Gold의 각각 1회 dev run이다.
두 모델은 역할과 grain이 다르므로 아래 증가는 회귀 비용 판정이 아니라 canonical dimension
scaffold와 완전성 대사에 필요한 상대적 작업량을 설명하는 지표다.

| 대리 지표 | 기존 source summary | 새 canonical Gold | 차이/비율 |
| --- | ---: | ---: | ---: |
| 외부 측정 dbt run wall time | 15.081초 | 22.818초 | +7.737초 / 1.51배 |
| dbt 전체 elapsed | 9.46초 | 17.76초 | +8.30초 / 1.88배 |
| dbt model elapsed | 8.682초 | 16.854초 | +8.172초 / 1.94배 |
| Trino query elapsed | 8.53초 | 16.68초 | +8.15초 / 1.96배 |
| Trino execution time | 6.26초 | 10.95초 | +4.69초 / 1.75배 |
| Trino processed row | 5,507 | 175,231 | 31.82배 |
| Trino processed byte | 543,071 B | 11,826,782 B | 21.78배 |
| Trino physical input row | 5,507 | 175,227 | 31.82배 |
| Trino physical input byte | 1,146,840 B | 23,901,499 B | 20.84배 |
| 최종 Gold row | 1 | 426 | 426배 |
| spill | 0 B | 0 B | 동일 |
| peak memory | 670,262 B | 1,716,927 B | 2.56배 |

기존 모델의 Trino query id는 `20260713_184419_02116_bg647`, 새 모델은
`20260713_184445_02121_bg647`이다. 새 Gold는 426개 canonical 행정동 scaffold, snapshot
완전성 대사, current mapping 대사를 수행하고 426행을 게시하므로 scan·row 수 증가 방향은
예상과 일치한다. spill은 두 실행 모두 0이고 wall time은 약 23초였다. 실패 후 모델 자체를
재실행한 횟수는 0회이며, 앞 절의 재시도는 test orchestration·shell timeout·selector
artifact 문제였다.

## 회귀와 데이터 영향

- 기존 `gold_traffic_incident_summary`: 1행, `incident_count = 6` 유지.
- recovery Gold: 1행, `incident_count = 6` 유지.
- canonical Gold: 격리 dev schema에 426행 신규 생성.
- 원천·Silver 운영 table과 prod table은 변경하지 않았다.
- `--full-refresh`, 대량 backfill, destructive delete는 실행하지 않았다.

## 남은 blocker와 후속 작업

1. Weather 테스트에 남아 있는 Traffic assertion 제거는 다른 도메인 파일 수정 금지 경계 때문에
   이 PR에서 수행하지 않았다. 해당 테스트는 Jinja 환경변수 표현을 raw YAML로 읽은 뒤 정수
   literal 15/30과 비교하므로 focused 실행에서 1건 실패했다. Traffic 소유 resolved manifest
   검증은 통과했지만, Weather 소유자가 별도 변경하거나 명시적인 gate waiver가 필요하다.
2. 현재 실행 중인 로컬 DAG checkout은 단일
   `ASK_SEOUL_REPORT_TRAFFIC_FRESHNESS_MINUTES` 계약을 사용한다. `dags/origin/dev`에는 dbt와
   같은 warn/error 두 key가 있으므로 DAG dev 배포 checkout 동기화가 필요하다.
3. 현재 DAG selector는 새 canonical Gold의 run/test를 schedule하지 않는다. DAG 저장소의
   Traffic selector 갱신과 fresh parse artifact 재사용을 포함한 통합이 필요하다.
4. dbt 1.10.22에서 대상 모델 test selection이 fresh parse artifact 없이 다르게 해석되는
   문제가 있어 DAG command shape를 명시적으로 고정해야 한다.
5. manifest의 자유문자열 `RuntimeError`만으로는 구조적인 API failure를 안전하게 단정할 수
   없다. 구조화된 failure type이 없으면 보수적으로 `partial`로 분류한다.
6. 사고 episode는 현재 snapshot 계약만으로 실제 종료 시각, snapshot 사이 재등장,
   source ID 재사용을 안전하게 판정할 수 없다. observation history와 명시적 종료 규칙을
   먼저 정의한 뒤 별도 모델로 진행한다.
7. 전용 secret scanner는 로컬에 없어 실행하지 못했다. 변경 파일 대상 값 비노출 휴리스틱
   검사는 통과했으며 CI의 전용 scanner 결과를 추가 확인해야 한다.
8. 검증용 격리 schema 3개는 삭제하지 않고 남겼다. 사용자 확인 후 dev 운영 절차에 따라
   수동 정리해야 한다.
