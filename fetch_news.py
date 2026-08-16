import urllib.request, urllib.parse, re, json, html, datetime
from email.utils import parsedate_to_datetime
QUERIES = ["논산 맛집", "논산 식당", "논산 먹거리"]
BLOCK = ["재선", "선거", "후보", "시의회", "도의회", "부고", "인사", "채용", "공약",
         "살해", "흉기", "검거", "구속", "사망", "화재", "음주", "마약", "성폭", "폭행", "사기"]
# 논산 밖 동네의 '논산' 상호 기사 차단 (실사례: 서울 전농동 '논산골')
OTHER_REGION = ["서울", "부산", "인천", "대구", "광주", "울산", "수원", "성남", "전농동", "동대문"]
# 논산시 공식 블로그는 행정 공지가 대부분 — 먹거리 관련만 통과
CITY_BLOG = "https://rss.blog.naver.com/nscity.xml"
FOOD = ["맛집", "먹거리", "축제", "식당", "카페", "음식", "미식", "특산", "딸기", "젓갈",
        "외식", "농산물", "빵", "디저트", "전통시장", "장터", "국수", "막걸리", "과일", "수확"]
# 주의: '시장' 단독은 금지 — 市長(백성현 시장) 기사가 전부 통과하는 동음이의 함정(2026-08-12 실측)


def toks4(t):
    return {w for w in re.findall(r"[가-힣A-Za-z0-9]{4,}", t) if w not in ("논산시", "충청남도")}


def clean_cdata(raw):
    return re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", raw or "", flags=re.S).strip()


def clean_title(raw):
    return html.unescape(re.sub(r"<[^>]+>", "", clean_cdata(raw))).strip()


def parse_items(xml):
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        t = re.search(r"<title>(.*?)</title>", it, re.S)
        l = re.search(r"<link>(.*?)</link>", it)
        d = re.search(r"<pubDate>(.*?)</pubDate>", it)
        s = re.search(r"<source[^>]*>(.*?)</source>", it)
        if not (t and l and d):
            continue
        try:
            dt = parsedate_to_datetime(d.group(1))
        except Exception:
            continue
        link = clean_cdata(l.group(1))  # 네이버 블로그 RSS는 링크도 CDATA 포장(2026-08-16 404 실사고)
        if not link.startswith("http"):
            continue  # 주소 형태가 아니면 명단에 올리지 않는다
        yield clean_title(t.group(1)), link, \
            (html.unescape(s.group(1)) if s else ""), dt.strftime("%Y-%m-%d")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        return urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
    except Exception:
        return ""


def fetch():
    cand = []
    for q in QUERIES:
        x = get("https://news.google.com/rss/search?q=" + urllib.parse.quote(q) + "&hl=ko&gl=KR&ceid=KR:ko")
        for title, link, src, day in parse_items(x):
            if any(b in title for b in BLOCK) or any(r in title for r in OTHER_REGION):
                continue
            cand.append({"t": title[:90], "u": link, "s": src, "d": day})
    # 논산시 공식 블로그 — 축제·특산물 등 원천 소식(언론 보도 전/미보도 건 커버)
    for title, link, _, day in parse_items(get(CITY_BLOG)):
        if not any(f in title for f in FOOD):
            continue
        if any(b in title for b in BLOCK):
            continue
        cand.append({"t": title[:90], "u": link, "s": "논산시 공식 블로그", "d": day})
    cand.sort(key=lambda x: x["d"], reverse=True)
    items = []
    for c in cand:
        tt = toks4(c["t"])
        # 같은 사건 중복: 같은 날짜에 4글자+ 핵심 토큰을 공유하면 한 건만
        if any(k["d"] == c["d"] and (toks4(k["t"]) & tt) for k in items):
            continue
        if any(re.sub(r"\\W", "", k["t"])[:14] == re.sub(r"\\W", "", c["t"])[:14] for k in items):
            continue
        items.append(c)
        if len(items) >= 8:
            break
    return {"updated": datetime.date.today().isoformat(), "items": items}


if __name__ == "__main__":
    out = fetch()
    json.dump(out, open("news.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for i in out["items"]:
        print("  ·", i["d"], f"[{i['s']}]", i["t"][:52])
