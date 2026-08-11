"""네이버 플레이스 원장 수확기.

경로: search.naver.com SERP에서 플레이스 ID를 이름 대조로 해석한 뒤,
m.place.naver.com 상세 페이지의 __APOLLO_STATE__를 파싱한다.
(내부망 아님 — 공개 웹의 사용자 동일 접근. 요청 간 딜레이로 정중하게.)
"""
import difflib
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

from curl_cffi import requests

DATA = Path(__file__).resolve().parent.parent / "data"

PAIR_RE = re.compile(r'"id"\s*:\s*"(\d{6,})"\s*,\s*"name"\s*:\s*"([^"]+)"')
ANCHOR_RE = re.compile(r'href="[^"]*place/(\d{6,})[^"]*"[^>]*>(?:<[^>]+>)*([^<>]{2,25})<')
APOLLO_RE = re.compile(r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\});", re.S)
STATUS_RE = re.compile(r"(영업 중|영업 종료|오늘 휴무|곧 영업 시작|브레이크타임|휴무)")


def _norm(s: str) -> str:
    s = re.sub(r"[\s()\[\]·.,'\"-]", "", s)
    s = re.sub(r"(논산직영점|논산본점|논산점|논산|본점|직영점)$", "", s)
    return s


def make_sessions():
    pc = requests.Session(impersonate="chrome131")
    pc.headers.update({"Accept-Language": "ko-KR,ko;q=0.9", "Referer": "https://www.google.com/"})
    pc.get("https://www.naver.com/", timeout=15)
    pc.headers["Referer"] = "https://www.naver.com/"
    mob = requests.Session(impersonate="safari_ios")
    mob.headers.update({"Accept-Language": "ko-KR,ko;q=0.9", "Referer": "https://m.search.naver.com/"})
    return pc, mob


def resolve(pc, name: str, region: str = "논산") -> dict:
    """SERP에서 이름과 가장 비슷한 place id를 찾는다."""
    clean = re.sub(r"^논산\s*|\s*논산$", "", name).strip()
    q = f"{region} {clean}"
    r = pc.get(f"https://search.naver.com/search.naver?query={quote(q)}", timeout=20)
    if r.status_code != 200:
        return {"query": q, "status": r.status_code, "id": None}
    pairs = PAIR_RE.findall(r.text) + [(i, t.strip()) for i, t in ANCHOR_RE.findall(r.text) if t.strip()]
    target = _norm(clean)
    best, best_score = None, 0.0
    seen = set()
    for pid, cand in pairs:
        key = (pid, cand)
        if key in seen or not re.search(r"[가-힣A-Za-z]", cand):
            continue
        seen.add(key)
        score = difflib.SequenceMatcher(None, target, _norm(cand)).ratio()
        if score > best_score:
            best, best_score = (pid, cand), score
    if not best:
        return {"query": q, "status": 200, "id": None}
    return {"query": q, "status": 200, "id": best[0], "matched_name": best[1], "match_score": round(best_score, 3)}


def fetch_place(mob, pid: str) -> dict:
    """m.place 상세 페이지에서 원장 필드를 파싱한다."""
    html = None
    for kind in ("restaurant", "place", "cafe"):
        r = mob.get(f"https://m.place.naver.com/{kind}/{pid}/home", timeout=20)
        if r.status_code == 200 and "__APOLLO_STATE__" in r.text:
            html = r.text
            break
    if html is None:
        return {"id": pid, "error": f"no apollo (last status {r.status_code})"}
    m = APOLLO_RE.search(html)
    if not m:
        return {"id": pid, "error": "apollo regex miss"}
    ap = json.loads(m.group(1))
    base = next((v for k, v in ap.items() if k.startswith("PlaceDetailBase")), None)
    if not base:
        return {"id": pid, "error": "no PlaceDetailBase"}

    coord = base.get("coordinate") or {}
    menus = [
        {"name": v.get("name"), "price": v.get("price")}
        for k, v in ap.items()
        if k.startswith("Menu:") and v.get("name")
    ]
    fsas = [
        {"title": v.get("title"), "date": v.get("date"), "type": v.get("type")}
        for k, v in ap.items()
        if k.startswith("FsasReview") and v.get("date")
    ]
    # 현재 영업 상태 (요일 의존 스냅샷 — 참고용)
    sm = STATUS_RE.search(html)
    return {
        "id": pid,
        "name": base.get("name"),
        "category": base.get("category"),
        "category_codes": base.get("categoryCodeList"),
        "road_address": base.get("roadAddress"),
        "address": base.get("address"),
        "lng": float(coord["x"]) if coord.get("x") else None,
        "lat": float(coord["y"]) if coord.get("y") else None,
        "phone": base.get("phone") or base.get("virtualPhone"),
        "score": base.get("visitorReviewsScore"),
        "visitor_reviews": base.get("visitorReviewsTotal"),
        "visitor_text_reviews": base.get("visitorReviewsTextReviewTotal"),
        "blog_reviews": base.get("cafeBlogReviewsTotal"),
        "conveniences": base.get("conveniences"),
        "micro_reviews": base.get("microReviews"),
        "is_good_store": base.get("isGoodStore"),
        "road_desc": base.get("road"),
        "opening_hours": base.get("openingHours"),
        "today_status": sm.group(1) if sm else None,
        "menus": menus[:15],
        "recent_mentions": sorted(fsas, key=lambda x: x["date"] or "", reverse=True)[:6],
    }


def harvest(candidates_path: str, out_path: str, start: int = 0, limit: int = 10000):
    cands = json.load(open(candidates_path, encoding="utf-8"))
    out = Path(out_path)
    done_names = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                done_names.add(json.loads(line)["candidate_name"])
            except Exception:
                pass
    pc, mob = make_sessions()
    n_ok = n_miss = 0
    with out.open("a", encoding="utf-8") as f:
        for i, c in enumerate(cands[start : start + limit], start):
            name = c["name"]
            if name in done_names:
                continue
            rec = {"candidate_name": name, "candidate": c}
            try:
                res = resolve(pc, name)
                rec["resolve"] = res
                if res.get("id"):
                    time.sleep(random.uniform(0.4, 0.8))
                    rec["place"] = fetch_place(mob, res["id"])
                    n_ok += 1
                else:
                    n_miss += 1
            except Exception as e:
                rec["error"] = repr(e)
                n_miss += 1
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{i+1}/{len(cands)}] {name} -> {rec.get('resolve', {}).get('matched_name')} "
                  f"(score {rec.get('resolve', {}).get('match_score')})", flush=True)
            time.sleep(random.uniform(0.5, 0.9))
    print(f"done: resolved {n_ok}, missed {n_miss}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "resolve":
        pc, mob = make_sessions()
        print(json.dumps(resolve(pc, sys.argv[2]), ensure_ascii=False, indent=1))
    elif cmd == "fetch":
        pc, mob = make_sessions()
        print(json.dumps(fetch_place(mob, sys.argv[2]), ensure_ascii=False, indent=1))
    elif cmd == "probe":  # resolve + fetch
        pc, mob = make_sessions()
        r = resolve(pc, sys.argv[2])
        print(json.dumps(r, ensure_ascii=False))
        if r.get("id"):
            print(json.dumps(fetch_place(mob, r["id"]), ensure_ascii=False, indent=1))
    elif cmd == "harvest":
        harvest(str(DATA / "candidates.json"), str(DATA / "naver_raw.jsonl"))
