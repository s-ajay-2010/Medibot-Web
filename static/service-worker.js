// basic service worker - very simple caching strategy.
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => clients.claim());
self.addEventListener('fetch', e => {
  // simple network-first for dynamic content
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});
