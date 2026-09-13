// ReMuse 溯游 Service Worker：离线可打开记录页（AC-F013-02 的外壳部分）
// - 页面导航：network-first，断网回退到缓存的记录页 "/"
// - _next/static 与图标：cache-first（构建产物带 hash，可长期缓存）
// - /api/*：永不缓存（草稿同步由页面层 localStorage 负责，与 SW 无关）
const CACHE = "remuse-shell-v1";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.add("/"))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))
        )
      )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.pathname.startsWith("/api/")) {
    return;
  }

  // 页面导航：network-first；断网时回退到缓存的记录页（离线也能记录草稿）
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((resp) => {
          if (url.pathname === "/") {
            const copy = resp.clone();
            caches.open(CACHE).then((cache) => cache.put("/", copy));
          }
          return resp;
        })
        .catch(() => caches.match("/"))
    );
    return;
  }

  // 静态资源：cache-first
  if (
    url.pathname.startsWith("/_next/static/") ||
    url.pathname.startsWith("/icons/")
  ) {
    event.respondWith(
      caches.match(event.request).then(
        (hit) =>
          hit ||
          fetch(event.request).then((resp) => {
            const copy = resp.clone();
            caches.open(CACHE).then((cache) => cache.put(event.request, copy));
            return resp;
          })
      )
    );
  }
});
