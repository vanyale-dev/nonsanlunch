"""전국 점심 메뉴 트렌드 봇 — 네이버 데이터랩 검색어트렌드(공식 API)로 매일 갱신 (2026-08-23).

배경: '실시간×논산×메뉴' 신호원 전수 조사(2026-08-23) 결과 지역 단위 신호는 구조적으로
부재 → 사장 결정 "전국 단위면 돼". 데이터랩은 일간·전국·공식·무료(일 1,000회)로
세 조건 중 둘을 깨끗하게 만족하는 유일한 소스다.

방법: 점심 메뉴 44종을 4개씩 11요청으로 조회하되, 매 요청에 기준 키워드('점심')를
함께 실어 정규화한다 — 데이터랩 ratio는 요청 내 최댓값=100인 상댓값이라 요청 간
직접 비교가 불가능하고, 공통 기준어로 나눠야 비교 가능해진다.
'뜬다' 판정: 최신일 지수 ÷ 직전 4주 같은 요일 평균 — 점심 검색은 요일 패턴이 강해
같은 요일끼리 비교해야 정직하다.

키: 환경변수 NCP_APIGW_API_KEY_ID / NCP_APIGW_API_KEY (깃허브 시크릿).
없으면 조용히 건너뛴다(exit 0) — 키 발급 전 배포를 막지 않기 위해.

⚠ 경로 변경(2026-08-23): 개발자센터 데이터랩 API는 2026-07-31부로 신규 신청이 차단되고
NCP의 NAVER API HUB로 이관됐다(developers.naver.com/notice/article/32530, 2027-06-30 완전 종료).
엔드포인트·헤더를 API HUB 규격으로 작성. 요청 본문 규격은 동일. 무료 쿼터 월 5만 회
(이 봇은 일 11회 ≈ 월 330회). 현재 무료 요금제만 제공, 유료화 예고 있음.
출력: data/menu_trend.json {updated, baseline, top[], menus[]}
"""
import json
import os
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"
BASELINE = "점심"
MENUS = [
    "국밥", "순대국", "해장국", "감자탕", "설렁탕", "곰탕", "갈비탕", "삼계탕", "추어탕", "육개장",
    "김치찌개", "된장찌개", "부대찌개", "순두부찌개", "청국장",
    "칼국수", "잔치국수", "냉면", "막국수", "콩국수", "밀면", "쌀국수", "라멘", "우동", "소바",
    "돈까스", "제육볶음", "불고기", "쭈꾸미", "닭갈비",
    "백반", "비빔밥", "보쌈", "족발",
    "짜장면", "짬뽕", "마라탕",
    "초밥", "회덮밥", "물회",
    "파스타", "햄버거", "피자", "샐러드",
]


def call(cid, sec, keywords, start, end):
    groups = [{"groupName": BASELINE, "keywords": [BASELINE]}] + [
        {"groupName": k, "keywords": [k]} for k in keywords]
    body = json.dumps({"startDate": start, "endDate": end, "timeUnit": "date",
                       "keywordGroups": groups}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": sec,
        "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def series_map(result):
    return {d["period"]: d["ratio"] for d in result.get("data", [])}


def main():
    cid, sec = os.environ.get("NCP_APIGW_API_KEY_ID"), os.environ.get("NCP_APIGW_API_KEY")
    if not cid or not sec:
        print("NCP_APIGW_API_KEY_ID/KEY 미설정 — 트렌드 수집 건너뜀(NCP API HUB 키 발급 후 자동 가동)")
        return
    end = date.today() - timedelta(days=1)          # 데이터랩은 어제까지가 최신
    start = end - timedelta(days=42)                # 같은 요일 4주 비교분 확보
    idx = {}                                        # 메뉴 → {날짜: 기준어 대비 지수}
    for i in range(0, len(MENUS), 4):
        batch = MENUS[i:i + 4]
        res = call(cid, sec, batch, start.isoformat(), end.isoformat())
        by_name = {g["title"]: series_map(g) for g in res["results"]}
        base = by_name.get(BASELINE, {})
        for m in batch:
            sm = by_name.get(m, {})
            idx[m] = {d: v / base[d] for d, v in sm.items() if base.get(d, 0) > 0}
        time.sleep(0.4)

    latest = end.isoformat()
    menus_out, skipped = [], []
    for m, s in idx.items():
        today_v = s.get(latest)
        prior = [s.get((end - timedelta(days=7 * w)).isoformat()) for w in (1, 2, 3, 4)]
        prior = [p for p in prior if p]
        if today_v is None or len(prior) < 3:
            skipped.append(m)
            continue
        avg = sum(prior) / len(prior)
        if avg <= 0:
            skipped.append(m)
            continue
        menus_out.append({"name": m, "idx": round(today_v, 4), "avg4w": round(avg, 4),
                          "momentum": round(today_v / avg, 3)})
    if skipped:
        print(f"데이터 부족 제외 {len(skipped)}종: {skipped}")  # 침묵 절단 금지 — 무엇이 빠졌는지 남긴다
    menus_out.sort(key=lambda x: -x["momentum"])
    # 전일 top을 기억해 '새 진입' 표시의 근거로 쓴다 — 목록이 느리게 변하는 계절성 신호라
    # 매일의 변화는 수치(%)와 진입/이탈로 보여야 한다 (2026-08-23 사장 피드백).
    prev_top = []
    prev_path = ROOT / "data" / "menu_trend.json"
    if prev_path.exists():
        try:
            prev = json.load(open(prev_path, encoding="utf-8"))
            if prev.get("updated") != latest:
                prev_top = prev.get("top", [])
            else:
                prev_top = prev.get("prev_top", [])  # 같은 날 재실행이면 전일 기록 유지
        except Exception:
            pass
    out = {
        "updated": latest, "baseline": BASELINE,
        "method": "네이버 데이터랩 일간·전국, '점심' 기준 정규화, 직전 4주 같은 요일 평균 대비",
        "top": [m["name"] for m in menus_out[:5] if m["momentum"] >= 1.15],
        # 하락도 같은 자로 잰다(2026-08-23 사장 지시) — 문턱은 상승 1.15의 역수(≈0.87)
        "bottom": [m["name"] for m in sorted(menus_out, key=lambda x: x["momentum"])[:5]
                   if m["momentum"] <= 0.87],
        # 계절 그룹 평균 — 화면의 '한 줄 이야기'의 데이터 근거(작문이 아니라 집계값에서 도출)
        "groups": {
            "여름": round(sum(m["momentum"] for m in menus_out if m["name"] in
                            {"냉면", "막국수", "콩국수", "밀면", "물회", "삼계탕"}) /
                        max(1, sum(1 for m in menus_out if m["name"] in
                                   {"냉면", "막국수", "콩국수", "밀면", "물회", "삼계탕"})), 3),
            "국물": round(sum(m["momentum"] for m in menus_out if m["name"] in
                            {"국밥", "순대국", "해장국", "감자탕", "설렁탕", "곰탕", "갈비탕", "추어탕",
                             "육개장", "김치찌개", "된장찌개", "부대찌개", "순두부찌개", "청국장",
                             "칼국수", "잔치국수", "우동", "라멘"}) /
                        max(1, sum(1 for m in menus_out if m["name"] in
                                   {"국밥", "순대국", "해장국", "감자탕", "설렁탕", "곰탕", "갈비탕", "추어탕",
                                    "육개장", "김치찌개", "된장찌개", "부대찌개", "순두부찌개", "청국장",
                                    "칼국수", "잔치국수", "우동", "라멘"})), 3),
        },
        "prev_top": prev_top,
        "menus": menus_out,
    }
    json.dump(out, open(ROOT / "data" / "menu_trend.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"갱신 {latest} · 뜨는 메뉴: {out['top'] or '(문턱 1.15 이상 없음)'} · 전체 {len(menus_out)}종")


if __name__ == "__main__":
    main()
