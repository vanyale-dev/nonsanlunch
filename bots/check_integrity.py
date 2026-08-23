"""무결성 감시 봇 — 배포물(데이터셋·index.html·news.json)의 불변식을 검사한다 (2026-08-23).

푸시마다 + 매일 아침 돌며, 깨지면 워크플로가 빨갛게 실패한다(깃허브가 메일로 알림).
네트워크 접근 없음 — 체크아웃된 배포물만 본다. 공식 재계산은 하지 않는다(공식의 집은
로컬 travel.py 하나 — 여기 사본을 두면 그 자체가 파편화 재발이다). 대신 필드 사이의
자기모순, 데이터셋↔웹앱 임베드 불일치, 신선도 썩음을 잡는다.

정책 상수(예: AI 휴면)는 정책이 바뀌면 이 파일도 함께 고쳐야 한다 — 실패 메시지에 명시.
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
errors = []


def check(ok, msg):
    if not ok:
        errors.append(msg)


def main():
    # ── 1. 데이터셋 기본 ──
    data = json.load(open(ROOT / "data" / "final_dataset.json", encoding="utf-8"))
    check(140 <= len(data) <= 200, f"수록 수 비정상: {len(data)}곳 (140~200 밖)")
    pids = [r.get("pid") for r in data]
    check(len(pids) == len(set(pids)), "pid 중복 존재")
    names = [r.get("name") for r in data]
    check(all(names) and len(names) == len(set(names)), "상호 공백 또는 중복")

    required = ("name", "lat", "lng", "move", "drive_min", "dist_summary", "naver_url", "category")
    for r in data:
        for k in required:
            check(r.get(k) not in (None, ""), f"{r.get('name', '?')}: 필수 필드 {k} 누락")

    # ── 2. 이동 필드 자기정합(공식 무관 — 표기끼리의 모순만) ──
    for r in data:
        mv, ds = r.get("move"), r.get("dist_summary", "")
        if mv == "원정":
            check(ds == f"논산 전역 · 차 약 {r['drive_min']}분", f"{r['name']}: 원정 표기 모순({ds})")
            check(r.get("expedition") is True, f"{r['name']}: 원정인데 expedition≠True")
        elif mv == "도보":
            check(isinstance(r.get("walk_min"), int) and ds == f"도보 {r['walk_min']}분",
                  f"{r['name']}: 도보 표기 모순({ds}/{r.get('walk_min')})")
        elif mv == "차량":
            check(ds == f"차 {r['drive_min']}분", f"{r['name']}: 차량 표기 모순({ds})")
        else:
            check(False, f"{r['name']}: 알 수 없는 move={mv}")

    # ── 3. 웹앱 임베드 ↔ 데이터셋 동기화 ──
    html = open(ROOT / "index.html", encoding="utf-8").read()
    m = re.search(r"const DATA = (\[.*?\]);\n", html, re.S)
    check(bool(m), "index.html에서 임베드 DATA를 찾지 못함")
    if m:
        embed = json.loads(m.group(1))
        check(len(embed) == len(data),
              f"임베드 {len(embed)}곳 ≠ 데이터셋 {len(data)}곳 — 재빌드 없이 데이터만 갱신된 배포")
        en = {e["name"] for e in embed}
        dn = set(names)
        check(en == dn, f"임베드/데이터셋 상호 차이: {sorted((en - dn) | (dn - en))[:5]}")

    # ── 4. 정책 불변식 (정책 변경 시 이 검사도 함께 갱신할 것) ──
    check('const AI_EP = "";' in html,
          "AI_EP가 휴면(빈값)이 아님 — 검색창 AI 재가동이 결정된 게 아니라면 사고. "
          "재가동이 맞다면 bots/check_integrity.py의 이 검사를 갱신할 것 (2026-08-20 보류 지시)")
    check('id="sikgaekOnly"' in html, "식객허영만 칩 소실")
    check('id="dockSummon"' in html, "발권기 소환 바 소실")
    # 쿠키 이미지는 CSS(.ck-img 배경)에 1회만 살고, 슬롯 3×반쪽 2 = 6개 <i>가 그걸 참조한다.
    # <img src="data:..."> 6중복 인라인(280KB 부풀림 사고, 2026-08-21)의 재발 감시.
    check(len(re.findall(r"\.ck-img \{[^}]*url\(data:image/png", html)) == 1,
          "포춘쿠키 CSS 배경 선언이 정확히 1회가 아님")
    check(html.count('class="ck-img"') == 6, "포춘쿠키 반쪽 요소가 6개가 아님")

    # ── 5. 신선도 ──
    news = json.load(open(ROOT / "news.json", encoding="utf-8"))
    nd = date.fromisoformat(news.get("updated", "2000-01-01"))
    check(date.today() - nd <= timedelta(days=3),
          f"news.json이 {nd}에서 멈춤(3일 초과) — 뉴스 봇 점검 필요")
    for r in data:
        fu = r.get("fresh_until")
        if fu:
            check(re.fullmatch(r"\d{4}-\d{2}-\d{2}", fu), f"{r['name']}: fresh_until 형식 이상({fu})")

    if errors:
        print(f"❌ 무결성 검사 실패 {len(errors)}건:")
        for e in errors[:30]:
            print("  -", e)
        sys.exit(1)
    print(f"✅ 무결성 검사 통과 — {len(data)}곳, 뉴스 {news.get('updated')}, 임베드 동기화 정상")


if __name__ == "__main__":
    main()
