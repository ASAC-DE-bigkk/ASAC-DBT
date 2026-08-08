"""commerce usage_patterns 규약 린트 — dbt 저장소 자체 완결(CI 게이트용).

표기 규약 정본: docs/DB/gold/usage-patterns-convention.md (ASAC-DBT#471,
Serving#178·#179 재발 방지). 이 린트는 dbt 저장소만 체크아웃한 CI 에서 돌므로
dags 코드를 임포트하지 않는다 — 테이블 allowlist 는 이 yml 이 스스로 선언한
d1_table 집합에서 유도한다(외부 목록 없음). 게시 시점 정본 감사는 ASAC-DAG
`gold/pattern_audit.py`(SERVING_SPEC 파생)가 한 번 더 수행한다.

검사(ERROR = exit 1):
  E1  pattern_id 슬러그 `^[a-z0-9_]{1,64}$` (하이픈 금지 — Serving#178)
  E2  (d1_table, pattern_id) 유일
  E3  주석 제거 후 SELECT/WITH 단일문
  E4  쓰기/DDL/PRAGMA/ATTACH 금지 토큰
  E5  FROM/JOIN 대상 ⊆ (이 yml 이 선언한 d1_table 전체 ∪ CTE 이름)
  E6  값 박힘 표식 `/* :name */` 금지 (Serving#179 — 바인딩처럼 보이는 주석)
  E7  `LIMIT :name` 은 n/limit/top_n 이름만 (게이트웨이 상한 clamp 대상)
경고(비차단):
  W1  requires 어휘 밖 항목 (기존 어휘: select_columns sort aggregate group_by
      filter_range having subquery window join filter_set filter_null)
  W2  파라미터 있는 패턴에 예시값 주석 부재(검증 스크립트 관용 추출 실패 예상 —
      dags _PARAM_OVERRIDES 로 보완된 패턴이 있어 비차단)

실행: python domains/commerce/scripts/lint_usage_patterns.py [--yml <path>]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml

SLUG_RE = re.compile(r"^[a-z0-9_]{1,64}$")
COMMENT_RE = re.compile(r"--[^\n]*|/\*[\s\S]*?\*/")
BAKED_MARK_RE = re.compile(r"/\*\s*:[a-z_]")
PLACEHOLDER_RE = re.compile(r":([a-z_][a-z0-9_]*)")
ALLOWED_TABLE_FUNCS = {"json_each"}   # 배열 IN 관용구(실 D1 검증) — pragma_* 는 계속 차단
LIMIT_NAMES = {"n", "limit", "top_n"}
REQUIRES_VOCAB = {"select_columns", "sort", "aggregate", "group_by", "filter_range",
                  "having", "subquery", "window", "join", "filter_set", "filter_null"}

# 토크나이저 기반 테이블 추출 — 정본은 ASAC-DAG gold/pattern_audit.py. 여기(dbt 저장소)는
# dags 를 임포트할 수 없어 같은 로직을 복제한다(두 저장소 게이트가 동일 규칙을 강제). 정규식
# ("FROM 뒤 첫 식별자")은 콤마 조인(FROM d1_ok, _keys)의 2번째 테이블을 놓쳐 폐기(레드팀 확증).
_TOKEN_RE = re.compile(
    r"""(?P<ws>\s+)
      | (?P<line_comment>--[^\n]*)
      | (?P<block_comment>/\*[\s\S]*?\*/)
      | (?P<string>'(?:[^']|'')*')
      | (?P<dquote>"(?:[^"]|"")*")
      | (?P<bquote>`(?:[^`]|``)*`)
      | (?P<bracket>\[[^\]]*\])
      | (?P<param>:[a-zA-Z_][a-zA-Z0-9_]*)
      | (?P<number>\d+\.?\d*)
      | (?P<ident>[a-zA-Z_][a-zA-Z0-9_]*)
      | (?P<punct>[(),.;])
      | (?P<other>[^\s])""",
    re.VERBOSE)
FORBIDDEN = {"attach", "detach", "insert", "update", "delete", "drop", "alter",
             "create", "replace", "vacuum", "reindex", "analyze", "load_extension"}
FORBIDDEN_PREFIX = ("pragma",)
BOUNDARY_KW = {"where", "group", "order", "having", "limit", "window", "union",
               "except", "intersect", "on", "using", "returning", "values"}
JOINMOD_KW = {"cross", "inner", "left", "right", "full", "outer", "natural"}


def _tokenize(sql):
    out = []
    for m in _TOKEN_RE.finditer(sql or ""):
        if m.lastgroup not in ("ws", "line_comment", "block_comment"):
            out.append((m.lastgroup, m.group()))
    return out


def _strip_ident(v):
    return v.strip('"`[]')


def _cte_names(toks):
    names, depth = set(), 0
    for i, (kind, val) in enumerate(toks):
        if kind == "punct" and val == "(":
            depth += 1
        elif kind == "punct" and val == ")":
            depth = max(0, depth - 1)
        if kind == "ident" and val.lower() == "as" and i >= 2 and i + 1 < len(toks):
            prev, nxt, pp = toks[i - 1], toks[i + 1], toks[i - 2]
            pp_with = pp[0] == "ident" and pp[1].lower() == "with"
            if (prev[0] in ("ident", "dquote", "bquote", "bracket") and nxt == ("punct", "(")
                    and (pp_with or pp == ("punct", ",")) and depth == 0):
                names.add(_strip_ident(prev[1]).lower())
    return names


def _table_refs(toks):
    refs, depth, in_list, list_depth, expect = [], 0, False, 0, False
    i, n = 0, len(toks)
    while i < n:
        kind, val = toks[i]
        low = val.lower() if kind == "ident" else val
        if kind == "punct" and val == "(":
            if expect:
                expect = False
            depth += 1; i += 1; continue
        if kind == "punct" and val == ")":
            depth -= 1
            if in_list and depth < list_depth:
                in_list, expect = False, False
            i += 1; continue
        if kind == "ident" and (low == "from" or low == "join"):
            in_list, list_depth, expect = True, depth, True; i += 1; continue
        if in_list and kind == "punct" and val == "," and depth == list_depth:
            expect = True; i += 1; continue
        if in_list and kind == "ident" and low in BOUNDARY_KW:
            in_list, expect = False, False; i += 1; continue
        if in_list and kind == "ident" and low in JOINMOD_KW:
            i += 1; continue
        if in_list and kind == "ident" and low == "as":
            i += 1; continue
        if expect and kind in ("ident", "dquote", "bquote", "bracket"):
            name, j = _strip_ident(val), i + 1
            while (j + 1 < n and toks[j] == ("punct", ".")
                   and toks[j + 1][0] in ("ident", "dquote", "bquote", "bracket")):
                name += "." + _strip_ident(toks[j + 1][1]); j += 2
            refs.append(name); expect = False; i = j; continue
        i += 1
    return refs


def lint(yml_path: Path) -> tuple[list[str], list[str]]:
    d = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    warns: list[str] = []
    declared_tables: set[str] = set()
    entries: list[tuple[str, str, dict]] = []   # (effective_table, pattern_id, pattern)
    for m in d.get("models", []):
        sv = m.get("config", {}).get("meta", {}).get("serving", {})
        dt = sv.get("d1_table")
        for t in (dt if isinstance(dt, list) else [dt] if dt else []):
            declared_tables.add(str(t).lower())
        default_table = dt if isinstance(dt, str) else None
        for p in (sv.get("usage_patterns") or []):
            table = str(p.get("d1_table") or default_table or "?")
            entries.append((table, str(p.get("pattern_id")), p))

    seen: set[tuple[str, str]] = set()
    for table, pid, p in entries:
        where = f"{table}/{pid}"
        if not SLUG_RE.match(pid):
            errors.append(f"E1 {where}: pattern_id 슬러그 위반(^[a-z0-9_]{{1,64}}$)")
        if (table, pid) in seen:
            errors.append(f"E2 {where}: (d1_table, pattern_id) 중복")
        seen.add((table, pid))

        sql = str(p.get("sql") or "")
        body = COMMENT_RE.sub(" ", sql).strip()
        toks = _tokenize(sql)
        if not toks or not (toks[0][0] == "ident" and toks[0][1].lower() in ("select", "with")):
            errors.append(f"E3 {where}: SELECT/WITH 로 시작하지 않음")
        semis = [k for k in range(len(toks)) if toks[k] == ("punct", ";")]
        if semis and not (len(semis) == 1 and semis[0] == len(toks) - 1):
            errors.append(f"E3 {where}: 복수 문장(세미콜론) 의심")
        for kind, val in toks:
            if kind == "ident":
                lw = val.lower()
                if lw in FORBIDDEN or any(lw.startswith(pre) for pre in FORBIDDEN_PREFIX):
                    errors.append(f"E4 {where}: 금지 토큰 '{lw}'")
                    break
        ctes = _cte_names(toks)
        refs = {r.lower() for r in _table_refs(toks)}
        external = sorted(r for r in refs if r not in declared_tables and r not in ctes
                          and r not in ALLOWED_TABLE_FUNCS)
        if external:
            errors.append(f"E5 {where}: 선언 밖 테이블 참조 {external}")
        if BAKED_MARK_RE.search(sql):
            errors.append(f"E6 {where}: 값 박힘 표식(/* :name */) — 실바인딩으로 바꿀 것")
        for k in range(len(toks) - 1):
            if toks[k][0] == "ident" and toks[k][1].lower() == "limit" and toks[k + 1][0] == "param":
                pname = toks[k + 1][1][1:]
                if pname not in LIMIT_NAMES:
                    errors.append(f"E7 {where}: LIMIT :{pname} — n/limit/top_n 만 상한 적용")

        extra_req = [r for r in (p.get("requires") or []) if r and r not in REQUIRES_VOCAB]
        if extra_req:
            warns.append(f"W1 {where}: requires 어휘 밖 {extra_req}")
        params = set(PLACEHOLDER_RE.findall(body))
        if params:
            comment_text = " ".join(COMMENT_RE.findall(sql))
            missing = sorted(n for n in params
                             if not re.search(rf":{n}\s*=\s*('[^']*'|[0-9])", comment_text))
            if missing:
                warns.append(f"W2 {where}: 예시값 주석 없는 파라미터 {missing}")
    return errors, warns


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default_yml = Path(__file__).resolve().parents[1] / "models" / "gold" / "_commerce_gold__models.yml"
    ap.add_argument("--yml", default=str(default_yml))
    args = ap.parse_args()
    errors, warns = lint(Path(args.yml))
    for w in warns:
        print(f"  warn  {w}")
    for e in errors:
        print(f"  ERROR {e}")
    print(f"lint: errors={len(errors)} warnings={len(warns)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
