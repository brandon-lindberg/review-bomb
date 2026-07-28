import { defaultCache } from "@serwist/next/worker";
import type { PrecacheEntry, RuntimeCaching, SerwistGlobalConfig } from "serwist";
import { NetworkOnly, Serwist } from "serwist";

declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}

declare const self: ServiceWorkerGlobalScope;

const configuredApiUrl =
  process.env.NEXT_PUBLIC_API_URL || "https://review-disparity.onrender.com/api/v1";
const configuredApiOrigin = new URL(configuredApiUrl).origin;

// Live application data must never be satisfied from Cache Storage. The app
// shell and static assets remain available offline through Serwist's defaults,
// while client components show their own offline/error state for live panels.
const liveDataCaching: RuntimeCaching[] = [
  {
    matcher: ({ sameOrigin, url }) =>
      (url.origin === configuredApiOrigin && url.pathname.startsWith("/api/v1/"))
      || (sameOrigin && url.pathname.startsWith("/api/live/")),
    method: "GET",
    handler: new NetworkOnly(),
  },
];

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: [...liveDataCaching, ...defaultCache],
  fallbacks: {
    entries: [
      {
        url: "/~offline",
        matcher({ request }) {
          return request.destination === "document";
        },
      },
    ],
  },
});

// Older workers used the generic cross-origin cache for backend API responses.
// Remove only those legacy entries when this worker activates so an installed
// PWA cannot fall back to pre-fix API payloads.
self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const cacheNames = await caches.keys();
    await Promise.all(
      cacheNames.map(async (cacheName) => {
        if (cacheName === "apis") {
          await caches.delete(cacheName);
          return;
        }
        if (cacheName !== "cross-origin") return;

        const cache = await caches.open(cacheName);
        const requests = await cache.keys();
        await Promise.all(
          requests
            .filter((request) => new URL(request.url).origin === configuredApiOrigin)
            .map((request) => cache.delete(request)),
        );
      }),
    );
  })());
});

serwist.addEventListeners();
