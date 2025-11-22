self.addEventListener('install', e => {
  console.log('SW installed');
  self.skipWaiting();
});
self.addEventListener('fetch', e => {
  e.respondWith(fetch(e.request));
});
