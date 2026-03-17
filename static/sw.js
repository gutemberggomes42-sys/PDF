const CACHE_NAME = 'pdf-audio-v2.0.1';
const STATIC_CACHE = 'static-v2.0.1';
const DYNAMIC_CACHE = 'dynamic-v2.0.1';

// Arquivos estáticos para cache
const STATIC_FILES = [
  '/',
  '/index.html',
  '/editor.html',
  '/static/manifest.json',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png',
  'https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css',
  'https://cdn.quilljs.com/1.3.6/quill.snow.css',
  'https://cdn.quilljs.com/1.3.6/quill.js',
  'https://cdn.jsdelivr.net/npm/chart.js'
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

  if (url.origin === self.location.origin) {
    if (
      url.pathname.startsWith('/play/') ||
      url.pathname.startsWith('/download/') ||
      url.pathname.startsWith('/status/') ||
      url.pathname.startsWith('/merge-audio/') ||
      url.pathname.startsWith('/download-merged/') ||
      url.pathname.startsWith('/upload')
    ) {
      event.respondWith(fetch(request));
      return;
    }
  }
  
  // Estratégia de cache: Cache First para estáticos, Network First para dinâmicos
  if (STATIC_FILES.includes(url.pathname) || 
      url.origin === self.location.origin && 
      (url.pathname.endsWith('.css') || 
       url.pathname.endsWith('.js') || 
       url.pathname.endsWith('.png') || 
       url.pathname.endsWith('.jpg') || 
       url.pathname.endsWith('.ico'))) {
    
    // Cache First para arquivos estáticos
    event.respondWith(
      caches.match(request)
        .then((response) => {
          if (response) {
            return response;
          }
          
          return fetch(request)
            .then((response) => {
              // Cache da resposta bem-sucedida
              if (response.ok) {
                const responseClone = response.clone();
                caches.open(DYNAMIC_CACHE)
                  .then((cache) => {
                    cache.put(request, responseClone);
                  });
              }
              return response;
            })
            .catch(() => {
              // Fallback para offline
              return new Response('Offline', {
                status: 503,
                statusText: 'Service Unavailable'
              });
            });
        })
    );
  } else {
    // Network First para requisições dinâmicas
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Cache de respostas GET bem-sucedidas
          if (request.method === 'GET' && response.ok) {
            const responseClone = response.clone();
            caches.open(DYNAMIC_CACHE)
              .then((cache) => {
                cache.put(request, responseClone);
              });
          }
          return response;
        })
        .catch(() => {
          // Tentar obter do cache
          return caches.match(request)
            .then((response) => {
              if (response) {
                return response;
              }
              
              // Fallback para página offline
              if (request.headers.get('accept').includes('text/html')) {
                return caches.match('/offline.html');
              }
              
              return new Response('Offline', {
                status: 503,
                statusText: 'Service Unavailable'
              });
            });
        })
    );
  }
});

// Background Sync para sincronização quando online
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-audio-files') {
    event.waitUntil(syncAudioFiles());
  }
});

// Sincronização de arquivos de áudio
async function syncAudioFiles() {
  try {
    // Obter arquivos pendentes do IndexedDB
    const pendingFiles = await getPendingFiles();
    
    for (const file of pendingFiles) {
      try {
        // Tentar upload quando online
        const response = await fetch('/upload', {
          method: 'POST',
          body: file.data,
          headers: file.headers
        });
        
        if (response.ok) {
          // Remover da lista de pendentes
          await removePendingFile(file.id);
        }
      } catch (error) {
        console.error('Erro no sync do arquivo:', error);
      }
    }
  } catch (error) {
    console.error('Erro na sincronização:', error);
  }
}

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
