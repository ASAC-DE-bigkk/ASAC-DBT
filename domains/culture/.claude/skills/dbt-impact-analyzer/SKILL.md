---
name: dbt-impact-analyzer
description: Use when modifying dbt models in domains/culture (or when the user asks for change-impact analysis) — extracts downstream lineage from manifest child_map deterministically, then judges breaking risk per column via sub-agents. ASAC-DBT#129 culture prototype.
---

# dbt-impact-analyzer (culture 프로토타입)

dbt 모델 수정 **전에** downstream 영향을 파악한다. 추출은 스크립트가 결정적으로,
판정은 sub-agent가 SQL 실참조 기준으로 수행한다. 설계:
`domains/culture/docs/design/2026-07-20-dbt-impact-analyzer.md` (이슈 #129·#294 참조).

## 환경 노트 (이 레포 전용)

- manifest는 컨테이너 빌드 산출물 — 이 환경 실경로:
  `C:/Users/Dell3571/ask-seoul/sample/dbt/domains/culture/target/manifest.json`
  (ASAC-DBT 워킹트리는 `target/` gitignore). 반드시 `--manifest`로 전달.
- 재파싱(빌드 아님, ~10초):
  `MSYS_NO_PATHCONV=1 docker exec elt-infra-airflow-scheduler-1 bash -c "cd /opt/airflow/dbt/domains/culture && /home/airflow/dbt-venv/bin/dbt parse --project-dir . --profiles-dir . --target dev"`
  실행 후 sample/dbt 체크아웃이 dev 기준이면 그대로, 다른 브랜치 검증 중이면 해당 브랜치 파일 기준으로 재생성됨에 유의.

## 워크플로 (순서 고정)

1. **수정 대상 식별**: `git diff --name-only dev` + unstaged에서
   `domains/culture/models/**/*.sql|yml` 추출. diff가 없으면 사용자가 지목한
   모델을 사용(가정 시나리오 분석 허용 — 이때 리포트에 "가정" 명시).
2. **추출**: `PYTHONIOENCODING=utf-8 python <이 스킬 디렉토리>/scripts/impact_map.py
   --model <names> --manifest <환경 노트 경로>`.
   `manifest.stale == true`면: 경고 표시(stale_files 목록) → 사용자에게 재파싱
   (환경 노트 커맨드) 승인을 물은 뒤, 승인 시 재파싱+재추출, 거절 시
   리포트에 "stale manifest 기준" 명시하고 진행.
3. **임계값 게이트**: 대상 모델 합산 `total_downstream`(테스트 제외) > **10**이면
   자동 진행 금지 — AskUserQuestion으로 ①대상 모델 축소 ②`--max-depth` 제한
   ③전체 계속 중 선택받는다.
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
| breaking | 삭제/타입 변경 컬럼을 downstream이 명시 참조 또는 `select *` 전파, 또는 대상 모델이 contract enforced인데 계약 컬럼을 삭제/타입 변경 |
| warn | 로직 변경(스키마 불변, 값 변화 가능) — downstream `attached_tests` 수 첨부 |
| non-breaking | 컬럼 추가, 삭제/변경 컬럼을 downstream이 미참조 |

## 리포트 템플릿

    ## 영향 분석: <model> (<변경 유형>)
    ⚠️ BREAKING: <n>건 — <모델 목록>        ← breaking 있을 때만, 최상단

    | downstream | depth | 영향 유형 | 참조 방식 | 위험도 | 비고 |
    |---|---|---|---|---|---|
    | gold_x | 1 | 직접 참조 | 명시(col_a) | breaking | contract enforced |
    | gold_y | 2 | 간접 전파 | select * | warn | 테스트 4개 |

    manifest: <generated_at> (stale 여부) · downstream 합계 <n> (테스트 제외)

- 영향 유형: depth=1 → 직접 참조, depth>=2 → 간접 전파
- 비고: contract enforced 여부, attached_tests 수, 가정 시나리오 여부

## 한계 (프로토타입)

- culture 프로젝트 한정 — 루트 승격은 #129 본안(멘토 게이트)
- raw SQL 기준 실참조 판정(compiled 미사용) — dbt_utils 매크로가 컬럼을 숨기는
  경우 sub-agent가 `매크로 경유 가능`으로 보고하고 사람 확인 요청
- exposure 노드 추적 없음(culture manifest에 현행 exposure 없음)
