const CACHE_NAME = "CACHE_PLACEHOLDER";
const ASSETS_TO_CACHE = [
  "/",
  "/index.html",
  "/css/daisy.min.css",
  "/css/style.min.css",
  "/js/index.min.js",
  "/js/theme.js",
  "/manifest.json",
  "/icons/favicon.ico",
  "/icons/favicon-32x32.avif",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      // One asset at a time: a single missing file must not abort the whole
      // install, which would leave the old worker and its cache in place.
      Promise.all(ASSETS_TO_CACHE.map((url) => cache.add(url).catch(() => {}))),
    ),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) =>
      Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name)),
      ),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const responseClone = response.clone();
        caches
          .open(CACHE_NAME)
          .then((cache) => cache.put(event.request, responseClone));
        return response;
      })
      .catch(() =>
        // ignoreSearch: assets are requested as /css/foo.css?v=<hash> while the
        // install-time precache stores the bare URL, so the query string has to
        // be ignored for the offline fallback to find the precached copy.
        caches.match(event.request, { ignoreSearch: true }),
      ),
  );
});
