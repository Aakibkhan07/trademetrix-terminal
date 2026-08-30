self.addEventListener('install', (e) => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/api/')) return;
  e.respondWith(
    caches.open('tm-v1').then((c) =>
      c.match(e.request).then((r) => r || fetch(e.request).then((res) => {
        if (res.ok && url.origin === self.location.origin) c.put(e.request, res.clone());
        return res;
      }))
    )
  );
});
self.addEventListener('push', (e) => {
  const data = e.data ? e.data.json() : { title: 'TradeMetrix', body: 'Update' };
  e.waitUntil(self.registration.showNotification(data.title || 'TradeMetrix', {
    body: data.body || '',
    icon: '/favicon.svg',
    badge: '/favicon.svg',
    tag: data.tag || 'tm',
  }));
});
