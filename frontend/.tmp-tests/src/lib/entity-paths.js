"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.slugifyEntityLabel = slugifyEntityLabel;
exports.buildEntitySegment = buildEntitySegment;
exports.buildEntityPath = buildEntityPath;
exports.buildEntityUrl = buildEntityUrl;
exports.parseEntityRouteSegment = parseEntityRouteSegment;
exports.buildPathWithQuery = buildPathWithQuery;
const ENTITY_SEGMENT_SEPARATOR = "--";
function slugifyEntityLabel(label) {
    if (!label)
        return "";
    return label
        .trim()
        .normalize("NFKC")
        .toLocaleLowerCase("en-US")
        .replace(/[’'`]+/g, "")
        .replace(/&/g, " and ")
        .replace(/[^\p{Letter}\p{Number}]+/gu, "-")
        .replace(/-+/g, "-")
        .replace(/^-|-$/g, "");
}
function buildEntitySegment(label, publicId) {
    const stableId = String(publicId).trim();
    const slug = slugifyEntityLabel(label);
    return slug ? `${slug}${ENTITY_SEGMENT_SEPARATOR}${stableId}` : stableId;
}
function buildEntityPath(entityType, label, publicId) {
    return `/${entityType}/${buildEntitySegment(label, publicId)}`;
}
function buildEntityUrl(siteUrl, entityType, label, publicId) {
    return `${siteUrl}${buildEntityPath(entityType, label, publicId)}`;
}
function parseEntityRouteSegment(segment) {
    const normalizedSegment = segment.trim().replace(/^\/+|\/+$/g, "");
    const separatorIndex = normalizedSegment.lastIndexOf(ENTITY_SEGMENT_SEPARATOR);
    if (separatorIndex <= 0 || separatorIndex === normalizedSegment.length - ENTITY_SEGMENT_SEPARATOR.length) {
        return {
            identifier: normalizedSegment,
            slug: null,
            isSlugged: false,
        };
    }
    return {
        identifier: normalizedSegment.slice(separatorIndex + ENTITY_SEGMENT_SEPARATOR.length),
        slug: normalizedSegment.slice(0, separatorIndex) || null,
        isSlugged: true,
    };
}
function buildPathWithQuery(path, query) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
        if (value == null)
            continue;
        if (Array.isArray(value)) {
            for (const item of value) {
                params.append(key, item);
            }
            continue;
        }
        params.set(key, value);
    }
    const serialized = params.toString();
    return serialized ? `${path}?${serialized}` : path;
}
