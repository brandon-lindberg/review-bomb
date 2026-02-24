export const NAVIGATION_START_EVENT = "reviewdisparity:navigation-start";

export function emitNavigationStart() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(NAVIGATION_START_EVENT));
}
