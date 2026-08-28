/* 논산런치 서비스워커 — 설치 가능성(PWA) + 오프라인 폴백. 캐시는 최소주의:
   내비게이션은 네트워크 우선(항상 최신), 실패 시에만 캐시된 index로 폴백. */
const CACHE = "nslunch-v6";
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(["./", "./index.html"])).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  if (e.request.mode === "navigate") {
    e.respondWith(
      fetch(e.request).then(res => {
        const cp = res.clone();
        caches.open(CACHE).then(c => c.put("./index.html", cp));
        return res;
      }).catch(() => caches.match("./index.html"))
    );
  }
});
