"""새로오픈 봇 — 네이버 pcmap 목록의 newOpening 플래그로 논산 신규 개업 탐지.

식당/카페를 분리 수집·분류한다(2026-08-12 사장 지시). 보고 전용 — DB 반영은
가드(실체·점심영업·포장배달) 통과 + 사장 승인 후 별도 편입 절차로 한다.

출력: data/new_open_report.json + 콘솔 요약
"""
import json
import re
import time
import random
from datetime import date
from pathlib import Path
from urllib.parse import quote

from curl_cffi import requests

DATA = Path(__file__).resolve().parent.parent / "data"

# 수집 쿼리 — 식당군/카페군 분리. 넓게 긁고 주소로 논산만 남긴다.
QUERIES = {
    "식당": ["논산 식당", "논산 맛집", "강경 식당", "연무 식당"],
    "카페": ["논산 카페", "논산 디저트", "논산 베이커리"],
}
CAFE_CAT = r"카페|디저트|베이커리|빵|브런치카페|찻집|커피"
NONSAN = r"논산|강경|연무|은진|취암|내동|부적|가야곡|연산|상월|광석|노성|성동|벌곡|양촌|채운"


def apollo_items(html):
    m = re.search(r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\});", html, re.S)
    if not m:
        return []
    try:
        st = json.loads(m.group(1))
    except Exception:
        return []
    out = []
    for k, v in st.items():
        if isinstance(v, dict) and v.get("__typename", "").startswith("PlaceListBusinessesItem"):
            out.append(v)
        elif isinstance(v, dict) and "newOpening" in v and v.get("name"):
            out.append(v)
    return out


def main():
    s = requests.Session(impersonate="chrome131")
    s.headers.update({"Accept-Language": "ko-KR,ko;q=0.9", "Referer": "https://pcmap.place.naver.com/"})

    # 이미 아는 pid — 원장·큐레이션·최종본 전부
    known = set()
    for f in ("curated.json", "final_dataset.json"):
        p = DATA / f
        if p.exists():
            known |= {str(r["pid"]) for r in json.load(open(p, encoding="utf-8"))}
    raw = DATA / "naver_raw.jsonl"
    if raw.exists():
        for line in raw.read_text(encoding="utf-8").splitlines():
            try:
                pid = ((json.loads(line).get("place") or {}).get("id"))
                if pid:
                    known.add(str(pid))
            except Exception:
                pass

    found = {}
    total_parsed = 0  # 파싱 붕괴 카나리아 — '신규 없음'과 '파서 고장'을 구별한다
    for kind, qs in QUERIES.items():
        for q in qs:
            try:
                r = s.get(f"https://pcmap.place.naver.com/restaurant/list?query={quote(q)}", timeout=20)
                items = apollo_items(r.text)
                total_parsed += len(items)
            except Exception as e:
                print(f"  ! {q}: {str(e)[:50]}")
                continue
            new_cnt = 0
            for it in items:
                if it.get("newOpening") is not True:
                    continue
                pid = str(it.get("id") or "")
                name = it.get("name") or ""
                addr = it.get("roadAddress") or it.get("commonAddress") or it.get("address") or ""
                cat = it.get("category") or ""
                if not pid or not name:
                    continue
                # 지역 판정은 1차에서 하지 않는다 — 상호·짧은 도로명 모두 함정(부산 절영로,
                # 수원 연무로 실사례). 건수가 적으므로 전부 2차 검증(전체 주소)으로 확정한다.
                new_cnt += 1
                if pid in found:
                    continue
                found[pid] = {
                    "pid": pid, "name": name, "category": cat, "addr": addr,
                    "kind": "카페" if re.search(CAFE_CAT, cat) else "식당",
                    "known": pid in known,
                    "visitor_reviews": it.get("visitorReviewCount") or it.get("visitorReviewsTotal"),
                    "queries": [q],
                }
            print(f"  [{kind}] '{q}' → 신규개업 {new_cnt}건")
            time.sleep(random.uniform(1.0, 1.6))

    if total_parsed == 0:
        # '논산 식당' 검색이 0건일 수는 없다 — 마크업 변경·차단 의심. 조용한 빈 보고 대신 명시적 실패.
        raise SystemExit("파싱 0건 — 네이버 응답 구조 변경 또는 차단 의심. 보고 미작성(거짓 '신규 없음' 방지)")

    fresh = [v for v in found.values() if not v["known"]]

    # 2차 검증 — 개별 페이지의 전체 주소로 '충남 논산시' 확정 (동명 도로·상호 오염 차단)
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from naver_place import make_sessions, fetch_place
    _, mob = make_sessions()
    verified = []
    for c in fresh:
        try:
            p = fetch_place(mob, c["pid"])
            full = p.get("road_address") or p.get("address") or ""
            c["addr"] = full or c["addr"]
            c["visitor_reviews"] = p.get("visitor_reviews") or c["visitor_reviews"]
            if "논산" in full:
                verified.append(c)
            else:
                print(f"  ✗ 타지 제외: {c['name']} ({full[:24]})")
        except Exception:
            c["addr"] += " [주소 검증 실패 — 수동 확인]"
            verified.append(c)
        time.sleep(random.uniform(0.6, 1.0))
    fresh = verified
    report = {
        "scanned": date.today().isoformat(),
        "queries": QUERIES,
        "total_new_opening": len(found),
        "already_known": len(found) - len(fresh),
        "candidates": sorted(fresh, key=lambda x: (x["kind"], x["name"])),
    }
    json.dump(report, open(DATA / "new_open_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"\n=== 신규 개업 후보 (미수록 {len(fresh)} / 탐지 {len(found)}) ===")
    for kind in ("식당", "카페"):
        rows = [c for c in fresh if c["kind"] == kind]
        print(f"\n[{kind}] {len(rows)}곳")
        for c in rows:
            print(f"  · {c['name']:<20} [{c['category']}] {c['addr']}  리뷰{c['visitor_reviews']}")
    print("\n다음 단계: 가드(실체·점심영업·포장배달) 검증 → 사장 승인 → 편입 + '새로오픈' 배지")


if __name__ == "__main__":
    main()
