"""전국 점심 메뉴 트렌드 봇 — 네이버 데이터랩 검색어트렌드(공식 API)로 매일 갱신 (2026-08-23).

배경: '실시간×논산×메뉴' 신호원 전수 조사(2026-08-23) 결과 지역 단위 신호는 구조적으로
부재 → 사장 결정 "전국 단위면 돼". 데이터랩은 일간·전국·공식·무료(일 1,000회)로
세 조건 중 둘을 깨끗하게 만족하는 유일한 소스다.

방법: 점심 메뉴 44종을 4개씩 11요청으로 조회하되, 매 요청에 기준 키워드('점심')를
함께 실어 정규화한다 — 데이터랩 ratio는 요청 내 최댓값=100인 상댓값이라 요청 간
직접 비교가 불가능하고, 공통 기준어로 나눠야 비교 가능해진다.
'뜬다' 판정: 최신일 지수 ÷ 직전 4주 같은 요일 평균 — 점심 검색은 요일 패턴이 강해
같은 요일끼리 비교해야 정직하다.

키: 환경변수 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET (깃허브 시크릿).
없으면 조용히 건너뛴다(exit 0) — 키 발급 전 배포를 막지 않기 위해.
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
API = "https://openapi.naver.com/v1/datalab/search"
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
        "X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec,
        "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def series_map(result):
    return {d["period"]: d["ratio"] for d in result.get("data", [])}


def main():
    cid, sec = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    if not cid or not sec:
        print("NAVER_CLIENT_ID/SECRET 미설정 — 트렌드 수집 건너뜀(키 발급 후 자동 가동)")
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
    out = {
        "updated": latest, "baseline": BASELINE,
        "method": "네이버 데이터랩 일간·전국, '점심' 기준 정규화, 직전 4주 같은 요일 평균 대비",
        "top": [m["name"] for m in menus_out[:5] if m["momentum"] >= 1.15],
        "menus": menus_out,
    }
    json.dump(out, open(ROOT / "data" / "menu_trend.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"갱신 {latest} · 뜨는 메뉴: {out['top'] or '(문턱 1.15 이상 없음)'} · 전체 {len(menus_out)}종")


if __name__ == "__main__":
    main()
