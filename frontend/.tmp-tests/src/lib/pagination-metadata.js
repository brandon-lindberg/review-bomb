"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getIndexablePaginationPage = getIndexablePaginationPage;
/**
 * Returns the page number when a listing URL is plain default-view pagination
 * (?page=N, N >= 2, no sort/filter/search facets) — those pages are kept
 * indexable with self-referencing canonicals so detail pages retain followed
 * internal links. Returns null for the base page and for every other faceted
 * state (which stay noindex).
 */
function getIndexablePaginationPage(pageParam, hasNonPageFacets) {
    if (hasNonPageFacets)
        return null;
    const trimmed = pageParam?.trim();
    if (!trimmed)
        return null;
    if (!/^\d+$/.test(trimmed))
        return null;
    const page = Number.parseInt(trimmed, 10);
    if (!Number.isSafeInteger(page) || page < 2)
        return null;
    return page;
}
