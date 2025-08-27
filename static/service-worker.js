self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open("ldapp-cache-v1").then((cache) => {
      return cache.addAll([
        "/",               // homepage
        "/static/css/style.css",  // i tuoi file principali
        "/static/icons/icon-192.png",
        "/static/icons/icon-512.png"
      ]);
    })
  );
});

self.addEventListener("fetch", (event) => {
  event.respondWith(
    caches.match(event.request).then((response) => {
      return response || fetch(event.request);
    })
  );
});
