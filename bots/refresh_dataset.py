"""유지보수 봇 — 수록 전체를 네이버 라이브로 재실측해 노후화를 보고한다.

점검 항목: 접속실패(폐업 의심) · 상호 변경 · 별점 변동 · 방문리뷰 증감 ·
별점 '공개 표시' 변화(2·3딸기 검증가능성 관문 영향) · 최근 언급 최신일.
보고 전용 — 데이터 반영은 사장 확인 후(visibility 스냅샷 갱신 제안 포함).

출력: data/refresh_report.json + 콘솔 요약. 실행 약 3~5분(정중한 딜레이).
"""
import json
import re
import sys
import time
import random
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from naver_place import make_sessions, APOLLO_RE  # noqa: E402


def visible_star(html):
    t = re.sub(r"<!--.*?-->", "", html)
    t = re.sub(r"<[^>]+>", " ", t)
    m = re.search(r"별점\s*([0-9]\.[0-9]{1,2})", t)
    return float(m.group(1)) if m else None


def main():
    D = json.load(open(DATA / "final_dataset.json", encoding="utf-8"))
    # 표시 여부 기준선: 전회 실행의 전수 기준선(baseline) 우선, 없으면 논슐랭 관문 스냅샷으로 폴백.
    base_path = DATA / "star_visibility_baseline.json"
    if base_path.exists():
        was_visible = {k for k, v in json.load(open(base_path, encoding="utf-8"))["visible"].items() if v}
        first_run = False
    else:
        vis_path = DATA / "naver_star_visibility.json"
        vis = json.load(open(vis_path, encoding="utf-8")) if vis_path.exists() else {"visible": {}}
        was_visible = set(vis.get("visible", {}))
        first_run = True  # 첫 실행 — '숨김→표시' 대량 표시는 기준선 확립 잡음
    measured = {}

    _, mob = make_sessions()
    dead, renamed, drift, vis_changed, surges = [], [], [], [], []
    checked = 0

    for r in D:
        pid = str(r["pid"])
        try:
            h = mob.get(f"https://m.place.naver.com/restaurant/{pid}/home", timeout=20).text
            m = APOLLO_RE.search(h)
            if not m:
                dead.append({"name": r["name"], "why": "페이지 파싱 실패(폐업/이전 의심)"})
                continue
            ap = json.loads(m.group(1))
            base = next((v for k, v in ap.items() if k.startswith("PlaceDetailBase")), None)
            if not base or not base.get("name"):
                dead.append({"name": r["name"], "why": "플레이스 정보 없음(폐업 의심)"})
                continue
            checked += 1
            live_name = base.get("name")
            if live_name != r["name"]:
                renamed.append({"name": r["name"], "now": live_name})
            new_score = base.get("visitorReviewsScore")
            old_score = r.get("naver_score")
            if new_score and old_score and abs(new_score - old_score) >= 0.05:
                drift.append({"name": r["name"], "old": old_score, "new": new_score})
            nv = base.get("visitorReviewsTotal") or 0
            ov = r.get("visitor_reviews") or 0
            if ov and nv >= ov * 1.3 and nv - ov >= 50:
                surges.append({"name": r["name"], "old": ov, "new": nv})
            v = visible_star(h)
            measured[r["name"]] = v
            now_vis = v is not None
            if r["name"] in was_visible and not now_vis:
                vis_changed.append({"name": r["name"], "change": "표시→숨김", "nc": r.get("nc", 0),
                                    "note": "2·3딸기면 강등 재심 필요" if r.get("nc", 0) >= 2 else ""})
            elif r["name"] not in was_visible and now_vis:
                vis_changed.append({"name": r["name"], "change": "숨김→표시", "value": v, "nc": r.get("nc", 0),
                                    "note": "상위 등급 재심 후보" if r.get("nc", 0) == 1 else ""})
        except Exception as e:
            dead.append({"name": r["name"], "why": f"요청 실패: {str(e)[:40]}"})
        time.sleep(random.uniform(0.55, 0.95))

    if checked < len(D) * 0.7:
        # 30% 이상 접속 실패 = 실측이 아니라 차단·장애다. 이대로 기준선을 덮으면 다음 달
        # '숨김→표시' 대량 오탐이 터진다 — 보고·기준선 모두 쓰지 않고 명시적으로 실패한다.
        raise SystemExit(f"실측 실패 {len(D) - checked}/{len(D)} — 차단·장애 의심. 기준선 보호를 위해 중단")

    report = {
        "checked_at": date.today().isoformat(), "total": len(D), "reached": checked,
        "dead_suspect": dead, "renamed": renamed, "score_drift": drift,
        "review_surge": surges, "visibility_changed": vis_changed,
    }
    if first_run:
        report["note"] = "첫 실행 — visibility_changed는 기준선 확립 잡음(실변화 아님). 다음 실행부터 순수 diff."
    json.dump(report, open(DATA / "refresh_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 전수 기준선 저장(측정 기록 — 자동 갱신). 2·3딸기 '관문' 파일은 사장 승인으로만 수정한다.
    json.dump({"measured_at": date.today().isoformat(), "visible": measured},
              open(base_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"\n=== 유지보수 점검 {report['checked_at']} — {checked}/{len(D)} 응답 ===")
    def sect(title, rows, fmt):
        print(f"\n[{title}] {len(rows)}건")
        for x in rows[:15]:
            print("  ·", fmt(x))
    sect("폐업·접속실패 의심", dead, lambda x: f"{x['name']} — {x['why']}")
    sect("상호 변경", renamed, lambda x: f"{x['name']} → {x['now']}")
    sect("별점 변동(±0.05↑)", drift, lambda x: f"{x['name']} {x['old']} → {x['new']}")
    sect("리뷰 급증(+30%·50건↑)", surges, lambda x: f"{x['name']} {x['old']} → {x['new']}")
    sect("별점 표시 변화(딸기 관문 영향)", vis_changed,
         lambda x: f"{x['name']} {x['change']} {x.get('note','')}")
    print("\n반영은 보고 검토 후 — visibility 스냅샷·강등/승급은 사장 승인으로.")


if __name__ == "__main__":
    main()
