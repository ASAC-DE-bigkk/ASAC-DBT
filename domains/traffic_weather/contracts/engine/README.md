# Public Gold contract engine AI index

이 디렉터리는 Traffic/Weather public Gold의 선언 계약과 dbt artifact 증거를 검증한다.
아래 세 파일은 경로·CLI·import 호환성을 유지하는 stable facade다.

| Stable CLI facade | 책임 |
| --- | --- |
| `lint_schema_contract_source.py` | schema YAML의 안전한 subset, 설명, resource 선언을 lint |
| `validate_public_gold_manifest.py` | dbt manifest의 public Gold 선언을 검증하고 선언 catalog를 생성 |
| `compare_public_gold_catalog.py` | 선언 catalog와 dbt catalog의 물리 schema 증거를 비교 |

## 내부 책임과 의존

- `_schema_contract`: YAML lexing/parsing, 설명·resource 규칙, repository 탐색, report/CLI
- `_manifest_contract`: manifest metadata, publication, time/space/semantic/lineage 규칙과 report/CLI
- `_catalog_contract`: catalog parsing, 비교, evidence/report/CLI
- `artifact_io.py`: 실행 환경의 stdout encoding과 무관하게 결정적 UTF-8 bytes를 전달

계층 순서는 schema → manifest → catalog다. 코드 의존은 뒤 계층이 앞 계층만 사용하므로
`_catalog_contract` → `_manifest_contract` → `_schema_contract` 방향이며 facade를 우회한다.
private package에서 stable facade를 import하거나 도메인별 규칙을 복제하지 않는다.

## 호환 규칙

- 종료코드 `0 / 1 / 2`는 각각 PASS / 계약 FAIL / invocation·artifact ERROR다.
- JSON report의 stdout, 파일 output, argparse·I/O 진단의 stderr 배치는 각 facade의 기존
  계약이다. 하나의 공통 출력 정책으로 합치지 않는다.
- stdout JSON bytes와 파일 artifact는 UTF-8, 결정적 key/order/newline 규칙을 유지한다.
- 직접 실행과 `contracts.engine.<facade>` import surface를 모두 보존한다.

## 테스트

행동 oracle과 architecture gate는 `contracts/engine/tests`에 있다.

```bash
python -m pytest -q contracts/engine/tests --disable-warnings -p no:cacheprovider
```
