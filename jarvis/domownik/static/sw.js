/* Service worker Domownika — tyle, ile trzeba, żeby dało się zainstalować
   aplikację na ekranie głównym i żeby przy braku sieci nie było białego ekranu.

   Świadomie SIEĆ NAJPIERW, a pamięć podręczna tylko jako koło ratunkowe.
   Serwer stoi w domu (Wi-Fi albo Tailscale), więc oszczędność na ładowaniu
   z pamięci jest żadna, a klasyczna pułapka PWA — telefon trzymający stary
   CSS/JS jeszcze długo po przebudowie serwera — kosztowałaby godziny zgadywania,
   czemu poprawka "nie weszła". Odświeżenie strony ma po prostu działać. */

const CACHE = 'domownik-v5';  // podbij przy zmianie wyglądu – stara kopia zostanie usunięta

/* Strony i pliki, które chcemy mieć pod ręką na wypadek braku sieci. */
const SHELL = [
  '/',
  '/zakupy',
  '/kalendarz',
  '/obowiazki',
  '/static/css/style.css',
  '/static/fonts/archivo-latin.woff2',
  '/static/fonts/archivo-latin-ext.woff2',
  '/static/js/app.js',
  '/static/js/home.js',
  '/static/js/calendar.js',
  '/static/js/chores.js',
  '/static/js/shopping.js',
  '/static/icon/domownik.png',
  '/static/icon/icon-192.png',
];

self.addEventListener('install', (event) => {
  self.skipWaiting();   // nowa wersja przejmuje od razu, bez zamykania kart
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .catch(() => { /* offline przy instalacji - trudno, dociągnie się później */ })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key !== CACHE) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== location.origin) return;

  /* Dane i strumień zmian ZAWSZE prosto z serwera. Podanie tu czegokolwiek
     z pamięci oznaczałoby pokazanie nieaktualnej listy obowiązków, a strumień
     /api/zmiany nigdy się nie kończy i nie wolno go przechwytywać. */
  if (url.pathname.startsWith('/api/')) return;

  event.respondWith((async () => {
    try {
      const fresh = await fetch(request);
      if (fresh.ok) {
        const copy = fresh.clone();
        caches.open(CACHE).then((cache) => cache.put(request, copy)).catch(() => {});
      }
      return fresh;
    } catch (err) {
      const cached = await caches.match(request);
      if (cached) return cached;
      if (request.mode === 'navigate') {
        const home = await caches.match('/');
        if (home) return home;
      }
      throw err;
    }
  })());
});
