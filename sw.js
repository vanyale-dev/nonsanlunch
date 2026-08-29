/* 논산런치 서비스워커 — 설치 가능성(PWA) + 오프라인 폴백. 캐시는 최소주의:
   내비게이션은 네트워크 우선(항상 최신), 실패 시에만 캐시된 index로 폴백. */
const CACHE = "nslunch-v8";
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(["./", "./index.html"])).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  if (e.request.mode === "navigate") {
    // 지도(/map/)는 우리 스코프(/nonsanlunch/) 안이지만 별개 앱이고 자기 sw(map/sw.js)가 맡는다.
    // 이 가드가 없으면 지도로 넘어가는 순간 지도 HTML이 발권기 앱 셸(./index.html)로 캐시돼
    // 오프라인에서 발권기 자리에 지도가 뜬다 (2026-08-29 지도 진입 카드 도입으로 드러난 결함).
    if (new URL(e.request.url).pathname.indexOf("/map/") !== -1) return;
    e.respondWith(
      fetch(e.request).then(res => {
        const cp = res.clone();
        caches.open(CACHE).then(c => c.put("./index.html", cp));
        return res;
      }).catch(() => caches.match("./index.html"))
    );
  }
});
