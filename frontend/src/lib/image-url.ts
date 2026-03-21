const OPENCRITIC_IMAGE_HOST = "img.opencritic.com";

export function isRemoteImageUrl(src: string): boolean {
  return /^https?:\/\//i.test(src);
}

export function normalizeImageUrl(src: string): string {
  const trimmed = src.trim();

  if (!trimmed) {
    return trimmed;
  }

  if (trimmed.startsWith("///")) {
    return `https:${trimmed.replace(/^\/+/, "//")}`;
  }

  if (trimmed.startsWith("//")) {
    return `https:${trimmed}`;
  }

  if (!isRemoteImageUrl(trimmed)) {
    return trimmed;
  }

  try {
    const url = new URL(trimmed);

    if (url.hostname === OPENCRITIC_IMAGE_HOST) {
      const embeddedHostMatch = url.pathname.match(/^\/{2,}([^/]+\.[^/]+)(\/.*)?$/);
      if (embeddedHostMatch) {
        const [, embeddedHost, embeddedPath = "/"] = embeddedHostMatch;
        return `${url.protocol}//${embeddedHost}${embeddedPath}${url.search}${url.hash}`;
      }

      const normalizedPath = url.pathname.replace(/\/{2,}/g, "/");
      if (normalizedPath !== url.pathname) {
        url.pathname = normalizedPath;
      }
    }

    return url.toString();
  } catch {
    return trimmed;
  }
}
