"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.buildSitemapEntityPages = buildSitemapEntityPages;
exports.validateSitemapInventory = validateSitemapInventory;
exports.buildStaticSitemapPages = buildStaticSitemapPages;
const entity_paths_1 = require("./entity-paths");
function normalizedNonEmptyString(value) {
    if (typeof value !== "string")
        return null;
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
}
function normalizedLastModified(value) {
    const rawValue = normalizedNonEmptyString(value);
    if (!rawValue)
        return null;
    const parsed = new Date(rawValue);
    return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}
function buildSitemapEntityPages({ siteUrl, entityType, entries, labelKey, }) {
    let skippedCount = 0;
    let invalidLastModifiedCount = 0;
    const pages = [];
    for (const entry of entries) {
        const publicId = normalizedNonEmptyString(entry.public_id);
        const label = normalizedNonEmptyString(entry[labelKey]);
        if (!publicId || !label) {
            skippedCount += 1;
            continue;
        }
        const lastModified = normalizedLastModified(entry.last_modified);
        if (entry.last_modified != null && !lastModified) {
            invalidLastModifiedCount += 1;
        }
        pages.push({
            url: `${siteUrl}${(0, entity_paths_1.buildEntityPath)(entityType, label, publicId)}`,
            ...(lastModified ? { lastModified } : {}),
            changeFrequency: "weekly",
            priority: 0.7,
        });
    }
    return { pages, skippedCount, invalidLastModifiedCount };
}
function validateSitemapInventory({ pages, minimumCount, label, }) {
    if (pages.length < minimumCount) {
        throw new Error(`${label} sitemap count ${pages.length} is below safety floor ${minimumCount}`);
    }
    const uniqueUrls = new Set(pages.map((page) => page.url));
    if (uniqueUrls.size !== pages.length) {
        throw new Error(`${label} sitemap contains duplicate canonical URLs`);
    }
}
function buildStaticSitemapPages(siteUrl) {
    return [
        { url: `${siteUrl}/`, changeFrequency: "daily", priority: 1.0 },
        { url: `${siteUrl}/games`, changeFrequency: "daily", priority: 0.9 },
        { url: `${siteUrl}/news`, changeFrequency: "daily", priority: 0.8 },
        { url: `${siteUrl}/journalists`, changeFrequency: "daily", priority: 0.9 },
        { url: `${siteUrl}/outlets`, changeFrequency: "daily", priority: 0.9 },
        { url: `${siteUrl}/leaderboards`, changeFrequency: "daily", priority: 0.8 },
        { url: `${siteUrl}/compare`, changeFrequency: "weekly", priority: 0.6 },
        { url: `${siteUrl}/about`, changeFrequency: "monthly", priority: 0.4 },
        { url: `${siteUrl}/faq`, changeFrequency: "monthly", priority: 0.4 },
        { url: `${siteUrl}/terms`, changeFrequency: "yearly", priority: 0.2 },
        { url: `${siteUrl}/privacy`, changeFrequency: "yearly", priority: 0.2 },
    ];
}
