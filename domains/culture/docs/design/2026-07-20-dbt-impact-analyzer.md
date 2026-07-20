# dbt-impact-analyzer — 변경 영향 분석 Claude 스킬 (culture 프로토타입)

2026-07-20 · culture 도메인 · 이슈 ASAC-DBT#129(멘토 발제, infra 스코프)의 culture 범위 프로토타입

## 배경 / 왜

dbt 모델 수정 시 downstream 영향을 수동 lineage 추적에 의존하거나 확인하지 않아,
컬럼 삭제/타입 변경/로직 변경의 전파로 downstream이 깨질 위험이 있다(#129 문제 정의).
manifest.json의 `child_map` 기반으로 수정 모델의 downstream을 자동 추적·분석하는
Claude 스킬을 만든다.

**프로토타입 전략**: #129의 도메인 필드는 infra — 레포 루트 `.claude/skills/` 배치는
공유 인프라 변경이라 멘토 게이트 대상. 따라서 **culture 소유 경로에 먼저 구현·검증**하고,
결과를 #129에 코멘트로 링크해 루트 승격을 제안한다. #129 자체는 닫지 않는다(멘토 소유).

culture 실측 근거(2026-07-20 manifest, dbt 1.10.22):
- 모델 31 + seed 8 + 테스트 221, `child_map` 완비, contract enforced 모델은 컬럼 메타 보유
- fanout 최대 9(`dim_admin_dong`), 대부분 2~5 — 임계값 게이트는 org 확장 대비 구현
- manifest 소재: `sample/dbt/domains/culture/target/manifest.json`(컨테이너 빌드 산출물).
  ASAC-DBT 워킹트리는 `target/` gitignore — **신선도 문제가 구조적으로 존재**

## 결정 사항 (사용자 확정)

1. **배치**: `domains/culture/.claude/skills/dbt-impact-analyzer/` — 레포 내 culture 소유
   경로. 커밋·PR로 팀에 공유 가능, Claude Code가 디렉토리 스코프 스킬로 인식.
2. **엔진**: 스크립트+스킬 하이브리드 — Python 스크립트가 child_map BFS를
   결정적(deterministic)으로 수행, SKILL.md가 그 결과 위에서 sub-agent 의미 분석.
   순수 프롬프트 방식은 600KB manifest를 매번 토큰으로 파싱해 누락 위험, 순수 CLI는
   실참조 분석(#129 AC 2)이 빠져 요구 미달.
3. **신선도**: 스크립트가 stale 판정(경고)만, 재파싱은 스킬이 컨테이너
   `dbt parse`(~10초, 빌드 아님)로 **제안 후** 진행. 무조건 재파싱은 컨테이너 기동을
   전제조건으로 만들어 배제.

## 산출물 구조

```
domains/culture/.claude/skills/dbt-impact-analyzer/
├── SKILL.md                     # 트리거 조건 + 분석 워크플로
└── scripts/
    ├── impact_map.py            # manifest child_map BFS 추출기 (stdlib only)
    └── test_impact_map.py       # pytest — 픽스처 미니 manifest
```

## 설계

### `impact_map.py` — 결정적 추출기

**입력(argparse)**:

| 인자 | 기본값 | 의미 |
|---|---|---|
| `--model NAME...` | (필수, 복수 허용) | 수정 대상 모델명(단순명 또는 unique_id) |
| `--project-dir PATH` | 스크립트 위치에서 상향 유도(`.claude/skills/…/scripts/` → `domains/culture`) | 신선도 비교 기준 워킹트리 |
| `--manifest PATH` | `<project-dir>/target/manifest.json` | manifest 경로. 표준 dbt 위치가 기본 — 이 환경처럼 target이 별도 체크아웃(sample/dbt)에 있으면 명시 전달 |
| `--max-depth N` | 무제한 | BFS 깊이 제한 |

스크립트는 **머신 고유 경로를 하드코딩하지 않는다**(루트 승격 시 그대로 재사용).
이 환경의 manifest 실경로(`…/sample/dbt/domains/culture/target/manifest.json`)는
SKILL.md의 환경 노트에만 기재하고 스킬이 `--manifest`로 전달한다.

**출력(stdout JSON)**:

```json
{
  "manifest": {"generated_at": "...", "stale": false, "stale_files": []},
  "targets": [{
    "name": "silver_culture_performance", "unique_id": "model.culture...",
    "found": true,
    "downstream": [{
      "name": "gold_culture_venue_profile", "unique_id": "...",
      "depth": 1, "layer": "gold", "materialization": "table",
      "contract_enforced": true, "columns": ["facility_id", "..."],
      "path": "models/gold/gold_culture_venue_profile.sql",
      "attached_tests": 6
    }],
    "summary": {"total_downstream": 5, "by_layer": {"int": 1, "gold": 4},
                "by_depth": {"1": 2, "2": 3}}
  }]
}
```

**규칙**:
- BFS는 `child_map` 순회, **테스트 노드는 downstream 카운트에서 제외**하되 모델별
  `attached_tests` 수로 별도 보고(임계값이 테스트 221개에 부풀려지는 것 방지).
  seed/모델만 순회 대상.
- `depth=1`이 직접 참조, `depth>=2`는 간접 전파.
- `layer`는 모델명 접두(`silver_`/`int_`/`gold_`/`dim_`)에서 유도, 그 외 `other`.
- **신선도**: manifest `generated_at`(UTC) vs `--project-dir`의
  `models/**/*.sql`·`models/**/*.yml`·`seeds/**` 최대 mtime 비교.
  mtime이 더 최신이면 `stale: true` + 어긋난 파일 목록(최대 10개).
- 모델명 미발견 시 `found: false` + 유사 이름 후보(부분일치) 제시, exit code 0
  (스킬이 리포트로 처리 — 스크립트 실패와 분석 결과를 구분).
- 의존성: Python stdlib만(json, argparse, pathlib, datetime, collections).

### `SKILL.md` — 워크플로 (#129 체크리스트 1:1 대응)

트리거: 사용자가 dbt 모델 수정을 요청/착수할 때, 또는 `/dbt-impact-analyzer` 명시 인보크.

1. **수정 대상 식별**: `git diff`(staged+unstaged, dev 대비)에서 변경된
   `models/**/*.sql`·yml 추출. diff가 없으면 사용자가 지목한 모델 사용.
2. **추출기 실행**: `python scripts/impact_map.py --model <names>`.
   `stale: true`면 경고 표시 + 컨테이너 재파싱 커맨드 제안:
   `docker exec elt-infra-airflow-scheduler-1 bash -c "cd /opt/airflow/dbt/domains/culture && /home/airflow/dbt-venv/bin/dbt parse --project-dir . --profiles-dir . --target dev"`
   — 사용자 승인 시 실행 후 재추출, 거절 시 stale 명시하고 진행.
3. **임계값 게이트**: `total_downstream`(테스트 제외) > **10**이면 자동 진행 금지 —
   AskUserQuestion으로 ①대상 모델 축소 ②`--max-depth` 제한 ③전체 계속 선택지 제시.
4. **변경 유형 분류**: 대상 모델의 SQL·yml diff를 읽어 컬럼 추가 / 컬럼 삭제 /
   타입 변경 / 로직 변경(스키마 불변) 구분. 삭제·타입 변경 컬럼명 목록을 확정.
5. **sub-agent 실참조 분석**: downstream 모델별 병렬 dispatch(Agent tool) —
   각 agent는 해당 모델 SQL(워킹트리)을 읽고 변경 컬럼의 실참조 여부를 판정:
   `명시 참조`(select/join/where에 등장) / `select * 전파`(간접 노출) / `미참조`.
   agent 입력은 (모델 경로, 변경 컬럼 목록, upstream 모델명)만 — 세션 히스토리 미전달.
6. **리포트 생성**: 아래 템플릿. breaking 존재 시 최상단에 ⚠️ 경고 블록.

### 판정 규칙 (governed — 정의로만 판정)

| 판정 | 조건 |
|---|---|
| **breaking** | 삭제/타입 변경된 컬럼을 downstream이 명시 참조 또는 `select *` 전파, 또는 대상 모델 자신이 contract enforced인데 계약 컬럼을 삭제/타입 변경 |
| **warn** | 로직 변경(스키마 불변, 값 변화 가능) — downstream 부착 테스트 수 첨부 |
| **non-breaking** | 컬럼 추가, 삭제/변경 컬럼을 downstream이 미참조 |

### 리포트 템플릿 (SKILL.md에 포함)

```markdown
## 영향 분석: <model> (<변경 유형>)
⚠️ BREAKING: <n>건 — <모델 목록>   ← breaking 있을 때만

| downstream | depth | 영향 유형 | 참조 방식 | 위험도 | 비고 |
|---|---|---|---|---|---|
| gold_x | 1 | 직접 참조 | 명시(col_a) | breaking | contract enforced |
| gold_y | 2 | 간접 전파 | select * | warn | 테스트 4개 |

manifest: <generated_at> (stale 여부) · downstream 합계 <n> (테스트 제외)
```

## 스코프 밖

- 레포 루트 승격·타 도메인 적용 — #129 코멘트로 제안만(멘토 게이트).
- compiled SQL 기반 분석 — 워킹트리 raw SQL로 충분(ref/컬럼 참조가 raw에 그대로 존재).
  compiled는 컨테이너 target에만 있고 stale 문제가 더 심함.
- 자동 수정·마이그레이션 생성 — 리포트까지만. 수정은 별도 작업.
- exposures·대시보드 소비자 추적 — culture manifest에 exposure 노드 없음(현행).

## 구현·검증 방식

1. culture 스코프 신규 이슈 발행(org 템플릿, #129 참조 명시) + 브랜치
2. TDD: `test_impact_map.py` 픽스처 미니 manifest(모델 5·테스트 3·seed 1로 구성한
   최소 child_map) → BFS·깊이·테스트 제외·stale 판정 테스트 → `impact_map.py` 구현
3. 실측 AC(아래) → SKILL.md 작성 → 스킬 라이브 E2E 1회 → PR(base dev) → dev 복귀

## AC (수용 기준)

- [ ] `impact_map.py --model dim_admin_dong` → **직접 참조(depth=1) 9개**(테스트 제외,
      IA-1 fanout 실측과 일치) + 전이 포함 전체 downstream, depth·layer·contract 메타 포함 (#129 AC 1)
      — 구현 중 실측: 전이 포함 20개(gold 9·silver 10·int 1)
- [ ] pytest 전부 PASS (BFS 정확성·중복 제거·테스트 제외·max-depth·stale 판정·미발견 처리)
- [ ] 실사례 E2E: `int_culture_activity_days`에 컬럼 추가 시나리오(7/20 PR#281 재현) →
      downstream `gold_culture_activity_by_dong` 식별 + non-breaking 판정 (#129 AC 2)
- [ ] 컬럼 삭제 시나리오(예: silver_culture_performance.genre 삭제 가정) →
      리포트 최상단 ⚠️ BREAKING 경고 + 실참조 downstream 명시 (#129 AC 4)
- [ ] stale manifest 상태에서 경고 + 재파싱 제안 동작 (#129 임계값 AC와 함께 3번 항목)
- [ ] 임계값 게이트: `--max-depth`/모델 축소 선택지 제시 로직이 SKILL.md에 명문화
      (culture 규모상 실발동 없음 — SKILL.md 검수로 갈음) (#129 AC 3)
- [ ] #129에 프로토타입 PR 링크 코멘트(루트 승격 제안 재료)
