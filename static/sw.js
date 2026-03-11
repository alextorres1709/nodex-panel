/**
 * NodexAI Panel — Service Worker
 * Enables offline caching, PWA install, and push notification support.
 */

const CACHE_NAME = 'nodexai-v2';
const STATIC_ASSETS = [
    '/static/css/styles.css',
    '/static/js/app.js',
    '/static/img/logo.png',
    '/static/img/logo-fondo.png',
];

// Install: pre-cache static assets
self.addEventListener('install', function(event) {
    event.waitUntil(
        caches.open(CACHE_NAME).then(function(cache) {
            return cache.addAll(STATIC_ASSETS);
        })
    );
    self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', function(event) {
    event.waitUntil(
        caches.keys().then(function(names) {
            return Promise.all(
                names.filter(function(n) { return n !== CACHE_NAME; })
                     .map(function(n) { return caches.delete(n); })
            );
        })
    );
    self.clients.claim();
});

// Fetch: network-first for API/pages, cache-first for static assets
self.addEventListener('fetch', function(event) {
    var url = new URL(event.request.url);

    // Static assets: cache-first
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(event.request).then(function(cached) {
                return cached || fetch(event.request).then(function(response) {
                    if (response.ok) {
                        var clone = response.clone();
                        caches.open(CACHE_NAME).then(function(cache) {
                            cache.put(event.request, clone);
                        });
                    }
                    return response;
                });
            })
        );
        return;
    }

    // API and pages: network-first with offline fallback
    if (event.request.method === 'GET') {
        event.respondWith(
            fetch(event.request).then(function(response) {
                if (response.ok && url.pathname !== '/login') {
                    var clone = response.clone();
                    caches.open(CACHE_NAME).then(function(cache) {
                        cache.put(event.request, clone);
                    });
                }
                return response;
            }).catch(function() {
                return caches.match(event.request).then(function(cached) {
                    return cached || new Response(
                        '<html><body style="background:#0a0a0a;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;font-family:system-ui">'
                        + '<div style="text-align:center"><h1>NodexAI</h1><p>Sin conexion. Reconectando...</p></div></body></html>',
                        { headers: { 'Content-Type': 'text/html' } }
                    );
                });
            })
        );
    }
});

// Push notifications (for future APK integration)
self.addEventListener('push', function(event) {
    var data = { title: 'NodexAI', body: 'Nueva notificacion', icon: '/static/img/logo.png' };
    if (event.data) {
        try { data = event.data.json(); } catch(e) { data.body = event.data.text(); }
    }
    event.waitUntil(
        self.registration.showNotification(data.title || 'NodexAI', {
            body: data.body || '',
            icon: data.icon || '/static/img/logo.png',
            badge: '/static/img/logo.png',
            data: { url: data.link || '/dashboard' },
        })
    );
});

// Notification click: open the linked page
self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    var url = (event.notification.data && event.notification.data.url) || '/dashboard';
    event.waitUntil(
        self.clients.matchAll({ type: 'window' }).then(function(clients) {
            for (var i = 0; i < clients.length; i++) {
                if (clients[i].url.indexOf(url) !== -1 && 'focus' in clients[i]) {
                    return clients[i].focus();
                }
            }
            return self.clients.openWindow(url);
        })
    );
});
