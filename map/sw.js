/* 논산런치 · 점심 지도 — 서비스워커
   목적은 하나다: 네트워크가 끊겼을 때 흰 화면(또는 브라우저 오류 페이지) 대신
   방금 보던 화면이 그대로 뜨게 하는 것.

   규칙
   1. 외부 호스트(네이버 SDK·타일)는 **절대 가로채지 않는다** — 그대로 통과시킨다.
   2. 같은 출처는 네트워크 우선 + 실패 시 캐시(오래된 데이터를 조용히 굳히지 않는다).
   3. 미리 담기(precache)는 페이지가 "첫 타일 그린 뒤"에 보내는 메시지로만 한다 —
      첫 화면의 대역폭을 뺏지 않기 위해서다.
*/
var V = "nl-map-v1";

self.addEventListener("install", function(e){ self.skipWaiting(); });

self.addEventListener("activate", function(e){
  e.waitUntil(
    caches.keys()
      .then(function(ks){ return Promise.all(ks.map(function(k){ return k === V ? null : caches.delete(k); })); })
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
            return c.match("app-naver.html", { ignoreSearch:true }).then(function(h){
              return h || c.match("app-ours.html", { ignoreSearch:true }).then(function(h2){
                if (h2) return h2;
                throw err;
              });
            });
          }
          throw err;
        });
      });
    })
  );
});
