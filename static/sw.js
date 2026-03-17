const CACHE_NAME = 'pdf-audio-v3.0.0';
const STATIC_CACHE = 'static-v3.0.0';
const DYNAMIC_CACHE = 'dynamic-v3.0.0';
const OFFLINE_AUDIO_CACHE = 'offline-audio-v1';

// Arquivos estáticos para cache
const STATIC_FILES = [
  '/',
  '/static/manifest.json'
];

// Instalação do Service Worker
self.addEventListener('install', (event) => {
  console.log('Service Worker instalado');
  
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('Cache estático criado');
        return cache.addAll(STATIC_FILES);
      })
      .then(() => {
        return self.skipWaiting();
      })
  );
});

// Ativação do Service Worker
self.addEventListener('activate', (event) => {
  console.log('Service Worker ativado');
  
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((cacheName) => 
              cacheName !== CACHE_NAME && 
              cacheName !== STATIC_CACHE && 
              cacheName !== DYNAMIC_CACHE
            )
            .map((cacheName) => {
              console.log('Removendo cache antigo:', cacheName);
              return caches.delete(cacheName);
            })
        );
      })
      .then(() => {
        return self.clients.claim();
      })
  );
});

// Interceptação de requisições
self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== 'GET') {
    event.respondWith(fetch(request));
    return;
  }

  const isSameOrigin = url.origin === self.location.origin;
  const isAudio = isSameOrigin && url.pathname.startsWith('/play/');
  const isDownload = isSameOrigin && (url.pathname.startsWith('/download/') || url.pathname.startsWith('/download-') || url.pathname.startsWith('/api/conversions/'));
  const isStatus = isSameOrigin && (url.pathname.startsWith('/status/') || url.pathname.startsWith('/api/'));
  const isNav = request.mode === 'navigate' || (request.headers.get('accept') || '').includes('text/html');

  if (isAudio || isDownload) {
    event.respondWith(cacheFirst(request, isAudio ? OFFLINE_AUDIO_CACHE : DYNAMIC_CACHE));
    return;
  }

  if (isStatus) {
    event.respondWith(networkFirst(request, DYNAMIC_CACHE));
    return;
  }
  
  // Estratégia de cache: Cache First para estáticos, Network First para dinâmicos
  if (isNav) {
    event.respondWith(networkFirst(request, DYNAMIC_CACHE, '/'));
    return;
  }

  if (isSameOrigin && STATIC_FILES.includes(url.pathname)) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  event.respondWith(networkFirst(request, DYNAMIC_CACHE));
});

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  try {
    const resp = await fetch(request);
    if (resp && resp.ok) {
      cache.put(request, resp.clone());
    }
    return resp;
  } catch (e) {
    const fallback = await cache.match(request);
    if (fallback) return fallback;
    return new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
  }
}

async function networkFirst(request, cacheName, fallbackPath) {
  const cache = await caches.open(cacheName);
  try {
    const resp = await fetch(request);
    if (resp && resp.ok) {
      cache.put(request, resp.clone());
    }
    return resp;
  } catch (e) {
    const cached = await cache.match(request);
    if (cached) return cached;
    if (fallbackPath) {
      const fb = await caches.match(fallbackPath);
      if (fb) return fb;
    }
    return new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
  }
}

self.addEventListener('sync', (event) => {
});

// Push notifications
self.addEventListener('push', (event) => {
  const options = {
    body: event.data.text(),
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/badge.png',
    vibrate: [200, 100, 200],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: 1
    },
    actions: [
      {
        action: 'explore',
        title: 'Abrir App',
        icon: '/static/icons/checkmark.png'
      },
      {
        action: 'close',
        title: 'Fechar',
        icon: '/static/icons/xmark.png'
      }
    ]
  };
  
  event.waitUntil(
    self.registration.showNotification('PDF para Áudio', options)
  );
});

// Manipulação de cliques em notificações
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  if (event.action === 'explore') {
    // Abrir o app
    event.waitUntil(
      clients.openWindow('/')
    );
  }
});

// IndexedDB para armazenamento offline
function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('pdfAudioDB', 1);
    
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
    
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains('pendingFiles')) {
        const store = db.createObjectStore('pendingFiles', { keyPath: 'id' });
        store.createIndex('timestamp', 'timestamp', { unique: false });
      }
    };
  });
}

async function getPendingFiles() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(['pendingFiles'], 'readonly');
    const store = transaction.objectStore('pendingFiles');
    const request = store.getAll();
    
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function removePendingFile(id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(['pendingFiles'], 'readwrite');
    const store = transaction.objectStore('pendingFiles');
    const request = store.delete(id);
    
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

// Estratégias de cache avançadas
class CacheStrategies {
  static async staleWhileRevalidate(request) {
    const cache = await caches.open(DYNAMIC_CACHE);
    const cached = await cache.match(request);
    
    const fetchPromise = fetch(request).then((response) => {
      if (response.ok) {
        cache.put(request, response.clone());
      }
      return response;
    });
    
    return cached || fetchPromise;
  }
  
  static async networkFirst(request) {
    try {
      const response = await fetch(request);
      if (response.ok) {
        const cache = await caches.open(DYNAMIC_CACHE);
        cache.put(request, response.clone());
      }
      return response;
    } catch (error) {
      const cached = await caches.match(request);
      return cached || new Response('Offline', { status: 503 });
    }
  }
  
  static async cacheFirst(request) {
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }
    
    try {
      const response = await fetch(request);
      if (response.ok) {
        const cache = await caches.open(DYNAMIC_CACHE);
        cache.put(request, response.clone());
      }
      return response;
    } catch (error) {
      return new Response('Offline', { status: 503 });
    }
  }
}

// Otimização de performance
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

// Limpeza de cache antigo
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((cacheName) => {
            return cacheName !== STATIC_CACHE && 
                   cacheName !== DYNAMIC_CACHE;
          })
          .map((cacheName) => {
            return caches.delete(cacheName);
          })
      );
    })
  );
});
