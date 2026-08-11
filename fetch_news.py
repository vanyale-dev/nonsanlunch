import urllib.request, urllib.parse, re, json, html, datetime
from email.utils import parsedate_to_datetime
QUERIES = ["논산 맛집", "논산 식당", "논산 먹거리"]
BLOCK = ["재선", "선거", "후보", "시의회", "도의회", "부고", "인사", "채용", "공약",
         "살해", "흉기", "검거", "구속", "사망", "화재", "음주", "마약", "성폭", "폭행", "사기"]
def toks4(t):
    return {w for w in re.findall(r"[가-힣A-Za-z0-9]{4,}", t) if w not in ("논산시", "충청남도")}
def fetch():
    cand = []
    for q in QUERIES:
        url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(q) + "&hl=ko&gl=KR&ceid=KR:ko"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            x = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
        except Exception:
            continue
        for it in re.findall(r"<item>(.*?)</item>", x, re.S):
            t = re.search(r"<title>(.*?)</title>", it); l = re.search(r"<link>(.*?)</link>", it)
            d = re.search(r"<pubDate>(.*?)</pubDate>", it); s = re.search(r"<source[^>]*>(.*?)</source>", it)
            if not (t and l and d):
                continue
            title = html.unescape(re.sub(r"<[^>]+>", "", t.group(1))).strip()
            if any(b in title for b in BLOCK):
                continue
            try:
                dt = parsedate_to_datetime(d.group(1))
            except Exception:
                continue
            cand.append({"t": title[:90], "u": l.group(1).strip(),
                         "s": html.unescape(s.group(1)) if s else "", "d": dt.strftime("%Y-%m-%d")})
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
        print("  ·", i["d"], i["t"][:56])
