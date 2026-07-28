"use client";

import { useEffect } from "react";

/**
 * A newly activated worker can control an already-open PWA without replacing
 * the JavaScript currently running in that window. Reload once when an
 * existing controller changes so deployed UI/cache rules take effect without
 * asking mobile users to perform a hard refresh.
 */
export function ServiceWorkerRefresh() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    const hadController = Boolean(navigator.serviceWorker.controller);
    let reloading = false;

    const handleControllerChange = () => {
      if (!hadController || reloading) return;
      reloading = true;
      window.location.reload();
    };

    navigator.serviceWorker.addEventListener(
      "controllerchange",
      handleControllerChange,
    );
    return () => {
      navigator.serviceWorker.removeEventListener(
        "controllerchange",
        handleControllerChange,
      );
    };
  }, []);

  return null;
}
