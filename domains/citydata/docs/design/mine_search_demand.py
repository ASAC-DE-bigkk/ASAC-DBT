"""citydata QA 평가셋 — 검색 수요 앵커링 (출제≠채점을 만드는 외부 실측 단계).

우리가 골드를 보고 질문을 지어내면 자문자답(주작)이 된다. 이 스크립트는 "무엇을
많이 묻는지"를 우리 상상이 아니라 네이버 실측에서 가져온다:

  1) 발견(discovery)  — 네이버 자동완성으로 seed 접두어를 실제 검색 패턴으로 확장.
                        (사람들이 실제로 치는 말 → 후보 풀이 우리 상상이 아님)
  2) 랭킹(ranking)    — 데이터랩 검색어트렌드로 후보들의 상대 검색량을 실측.
                        앵커 키워드로 배치 간 정규화(데이터랩 ratio는 응답 단위 정규화라
                        공통 앵커로 나눠야 배치 교차 비교가 성립).
  3) 산출            — ranked_search_demand.json (수요 상위 주제) → 이후 페르소나가
                        이 주제를 자연어 질문으로 바꾸고(블라인드), 사후에 골드 매칭.

키: .env 의 NAVER_DATALAB_CLIENT_ID / NAVER_DATALAB_CLIENT_SECRET (무료 발급).
실행:  py dbt/domains/citydata/docs/design/mine_search_demand.py
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parents[4]  # .../sample
OUT = HERE / "ranked_search_demand.json"

# seed 접두어 — 서울 장소·혼잡·상권·이동 축. 자동완성이 여기서 실제 검색어로 확장한다.
# (citydata가 다루는 신호축과 정렬: 실시간혼잡/예측/상권/날씨/교통/충전)
SEED_PREFIXES = [
    "강남역", "홍대", "명동", "여의도", "잠실", "성수동", "이태원", "종로",
    "서울 축제", "서울 불꽃축제", "한강 ", "서울 지금", "서울 혼잡", "서울 붐빔",
    "강남 맛집", "서울 주차", "서울 전기차 충전", "서울 인구", "서울 상권",
]

# 배치 간 정규화용 앵커 — 계절/이벤트에 덜 흔들리는 고정 고수요어.
ANCHOR = {"groupName": "__anchor__", "keywords": ["서울"]}


def load_env() -> dict:
    env = {}
    envfile = REPO / ".env"
    if envfile.exists():
        for line in envfile.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    # 실제 환경변수가 있으면 우선
    for k in ("NAVER_DATALAB_CLIENT_ID", "NAVER_DATALAB_CLIENT_SECRET"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def autocomplete(prefix: str) -> list[str]:
    """네이버 자동완성 — 실제 사용자 검색어 추천. 비공식·공개 엔드포인트."""
    q = urllib.parse.quote(prefix)
    url = (f"https://ac.search.naver.com/nx/ac?q={q}&con=1&frm=nv&ans=2"
           f"&r_format=json&r_enc=UTF-8&r_unicode=0&t_koreng=1&run=2&rev=4&st=100")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"  ! 자동완성 실패 {prefix!r}: {e}")
        return []
    out = []
    for block in data.get("items", []):
        for item in block:
            if item and isinstance(item, list) and item[0]:
                out.append(item[0])
    return out


def datalab(env: dict, groups: list[dict]) -> dict:
    """데이터랩 검색어트렌드 — groups(<=5) 상대 검색량 시계열. ratio 는 응답 내 max=100 정규화."""
    end = date.today()
    start = end - timedelta(days=90)
    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "timeUnit": "month",
        "keywordGroups": groups,
    }
    req = urllib.request.Request(
        "https://openapi.naver.com/v1/datalab/search",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "X-Naver-Client-Id": env["NAVER_DATALAB_CLIENT_ID"],
            "X-Naver-Client-Secret": env["NAVER_DATALAB_CLIENT_SECRET"],
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def demand_score(env: dict, keywords: list[str]) -> dict[str, float]:
    """앵커 정규화로 배치 교차 비교 가능한 수요 점수. 앵커 합 대비 각 키워드 합의 비율."""
    scores: dict[str, float] = {}
    # 앵커(1) + 후보(<=4) 를 한 배치로 → 앵커로 나눠 정규화
    for i in range(0, len(keywords), 4):
        chunk = keywords[i:i + 4]
        groups = [ANCHOR] + [{"groupName": k, "keywords": [k]} for k in chunk]
        try:
            res = datalab(env, groups)
        except Exception as e:  # noqa: BLE001
            print(f"  ! 데이터랩 실패 배치 {i}: {e}")
            continue
        sums = {g["title"]: sum(p["ratio"] for p in g["data"]) or 0.0
                for g in res["results"]}
        anchor = sums.get("__anchor__", 0.0) or 1e-9
        for k in chunk:
            scores[k] = round(sums.get(k, 0.0) / anchor, 4)
        time.sleep(0.3)  # 레이트리밋 예의
    return scores


def main() -> None:
    env = load_env()
    if not env.get("NAVER_DATALAB_CLIENT_ID") or not env.get("NAVER_DATALAB_CLIENT_SECRET"):
        raise SystemExit(
            ".env 에 NAVER_DATALAB_CLIENT_ID / NAVER_DATALAB_CLIENT_SECRET 가 필요합니다.\n"
            "https://developers.naver.com/apps/#/register 에서 데이터랩 API 등록 후 발급하세요."
        )

    # 1) 발견 — 자동완성으로 후보 확장
    print("[1/3] 자동완성으로 후보 확장…")
    candidates: set[str] = set()
    for p in SEED_PREFIXES:
        sugg = autocomplete(p)
        candidates.update(sugg)
        print(f"  {p!r:20s} → {len(sugg)}개")
        time.sleep(0.2)
    candidates = {c for c in candidates if "서울" in c or any(
        s.split()[0] in c for s in SEED_PREFIXES)}  # 서울/장소 관련만
    cand_list = sorted(candidates)
    print(f"  총 후보 {len(cand_list)}개")

    # 2) 랭킹 — 데이터랩 실측 수요
    print("[2/3] 데이터랩으로 수요 랭킹…")
    scores = demand_score(env, cand_list)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

    # 3) 산출
    payload = {
        "generated_for": "citydata QA eval — 검색 수요 앵커(출제≠채점)",
        "method": "네이버 자동완성 발견 → 데이터랩 앵커정규화 랭킹, window=최근 90일 month",
        "anchor": ANCHOR["keywords"],
        "seed_prefixes": SEED_PREFIXES,
        "ranked": [{"keyword": k, "demand": v} for k, v in ranked],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[3/3] 저장: {OUT}  (상위 {min(20, len(ranked))}개)")
    for k, v in ranked[:20]:
        print(f"    {v:7.3f}  {k}")


if __name__ == "__main__":
    main()
