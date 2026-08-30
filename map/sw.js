/* 논산런치 · 점심 지도 — 서비스워커
   목적은 하나다: 네트워크가 끊겼을 때 흰 화면(또는 브라우저 오류 페이지) 대신
   방금 보던 화면이 그대로 뜨게 하는 것.

   규칙
   1. 외부 호스트(네이버 SDK·타일)는 **절대 가로채지 않는다** — 그대로 통과시킨다.
   2. 같은 출처는 네트워크 우선 + 실패 시 캐시(오래된 데이터를 조용히 굳히지 않는다).
   3. 미리 담기(precache)는 페이지가 "첫 타일 그린 뒤"에 보내는 메시지로만 한다 —
      첫 화면의 대역폭을 뺏지 않기 위해서다. 지금 페이지가 보내는 목록은
      [location.pathname, "./data/places.json", "./img/branch.png", "./img/me.png",
       "./img/fresh.png", "./img/sel.png", "./img/cafe.png"] 일곱이고, 그게 배포 파일 전부다.
      data/dong.geojson·zone_labels.json 은 파일로는 남아 있으나 페이지가 부르지
      않으므로 담지 않는다(2026-08-28 동네 보기 제거).
      마커 그림 두 장이 붙어 캐시 이름을 nl-map-v2 → v3 로 올렸다(2026-08-28).
      2026-08-28(3차)에 선택 핀(sel.png)·새로오픈(fresh.png)이 목록에 붙어 v3 → v4 로
      올렸다 — 그림이 바뀐 배포라 v3 에 담긴 낡은 사본을 확실히 버리게 한다.
      2026-08-29 카페 마커(cafe.png)가 목록에 붙어 v4 → v5 로 올렸다 — 같은 이유다.
      2026-08-29(2차) 카페 편입 배포로 v5 → v6 — places.json 이 167 → 220 곳으로 바뀌고
      cafe.png 도 다시 그려져(커피색 원반+진한 테두리) v5 의 낡은 사본을 버리게 한다.
      2026-08-29(3차) 「지도에서 전체보기」 배포로 v6 → v7 — 지도 화면에 본 앱 복귀 버튼이
      붙어 문서가 바뀌었다. v6 에 담긴 낡은 문서 사본을 확실히 버리게 한다.
      2026-08-30 하단 시트를 본 앱 카드와 일치시킨 배포로 v7 → v8 — 문서(index.html)와
      data/places.json 이 **둘 다** 바뀌었다(시트가 읽는 필드 8개가 늘었다). 낡은 문서에
      새 데이터, 또는 그 반대가 짝지어지지 않도록 v7 사본을 통째로 버리게 한다.
   4. **낡은 캐시 청소는 우리 것(`nl-map-*`)만 한다.** CacheStorage 는 스코프가 아니라
      출처(origin) 단위라, 같은 출처에 사는 발권기 본 앱의 캐시(`nslunch-*`)가 여기서 다 보인다.
      "내 이름이 아니면 지운다"로 쓰면 지도를 한 번 여는 것만으로 발권기의 오프라인 폴백이
      통째로 지워진다(2026-08-27 실URL 실측으로 확인 — 지도 진입 뒤 `nslunch-v2` 소멸).
*/
var V = "nl-map-v8";
var MINE = "nl-map-";      /* 이 접두사가 붙은 캐시만 우리 것이다 */

self.addEventListener("install", function(e){ self.skipWaiting(); });

self.addEventListener("activate", function(e){
  e.waitUntil(
    caches.keys()
      .then(function(ks){ return Promise.all(ks.map(function(k){
        return (k.indexOf(MINE) === 0 && k !== V) ? caches.delete(k) : null;   /* 남의 캐시는 손대지 않는다 */
      })); })
      .then(function(){ return self.clients.claim(); })
  );
});

self.addEventListener("message", function(e){
  var d = e.data || {};
  if (d.type !== "precache" || !d.urls) return;
  e.waitUntil(caches.open(V).then(function(c){
    return Promise.all(d.urls.map(function(u){
      return c.add(new Request(u, { cache:"no-cache" })).catch(function(){});
    }));
  }));
});

self.addEventListener("fetch", function(e){
  var req = e.request;
  if (req.method !== "GET") return;
  var u;
  try { u = new URL(req.url); } catch (err) { return; }
  if (u.origin !== self.location.origin) return;      /* 네이버·외부 타일은 손대지 않는다 */

  e.respondWith(
    fetch(req).then(function(res){
      if (res && res.status === 200 && res.type === "basic") {
        var copy = res.clone();
        caches.open(V).then(function(c){ c.put(req, copy); }).catch(function(){});
      }
      return res;
    }).catch(function(err){
      return caches.open(V).then(function(c){
        return c.match(req, { ignoreSearch:true }).then(function(hit){
          if (hit) return hit;
          if (req.mode === "navigate") {
            /* 페이지가 미리 담는 키는 location.pathname(= /nonsanlunch/map/) 이다.
               "./" 는 이 스코프에서 그 주소로 풀린다 — index.html 로 맞추면 빗나간다.
               app-naver.html·app-ours.html 폴백은 2026-08-28 배포 정리로 파일이 사라져 뺐다. */
            return c.match("./", { ignoreSearch:true }).then(function(h){
              if (h) return h;
              throw err;
            });
          }
          throw err;
        });
      });
    })
  );
});
