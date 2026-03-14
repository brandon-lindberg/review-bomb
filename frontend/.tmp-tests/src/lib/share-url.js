"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.buildSnapshotShareParams = buildSnapshotShareParams;
exports.buildEntitySnapshotShareUrl = buildEntitySnapshotShareUrl;
exports.buildCompareShareParams = buildCompareShareParams;
exports.buildCompareShareUrl = buildCompareShareUrl;
exports.withSnapshotNonce = withSnapshotNonce;
exports.buildRedditShareUrl = buildRedditShareUrl;
exports.buildXIntentUrl = buildXIntentUrl;
const share_snapshot_1 = require("./share-snapshot");
const entity_paths_1 = require("./entity-paths");
function buildSnapshotShareParams(input) {
    const params = new URLSearchParams({
        card: input.card,
        v: input.version,
        critic: (0, share_snapshot_1.encodeSnapshotMetric)(input.critic),
        steam: (0, share_snapshot_1.encodeSnapshotMetric)(input.steam),
        mc: (0, share_snapshot_1.encodeSnapshotMetric)(input.metacritic),
        disp: (0, share_snapshot_1.encodeSnapshotMetric)(input.disparity),
    });
    const mode = input.mode ?? "default";
    if (mode !== "default") {
        params.set("mode", mode);
    }
    const nonce = input.nonce?.trim();
    if (nonce) {
        params.set("sx", nonce.slice(0, 24));
    }
    const trend = input.trend?.trim();
    if (trend) {
        params.set("t", trend);
    }
    if (mode === "timing") {
        const early = (0, share_snapshot_1.encodeSnapshotCount)(input.early);
        const launch = (0, share_snapshot_1.encodeSnapshotCount)(input.launch);
        const late = (0, share_snapshot_1.encodeSnapshotCount)(input.late);
        if (early !== undefined)
            params.set("early", early);
        if (launch !== undefined)
            params.set("launch", launch);
        if (late !== undefined)
            params.set("late", late);
    }
    return params;
}
function buildEntitySnapshotShareUrl(siteUrl, entityType, entityLabel, publicId, input) {
    return `${siteUrl}${(0, entity_paths_1.buildEntityPath)(entityType, entityLabel, publicId)}?${buildSnapshotShareParams(input).toString()}`;
}
function buildCompareShareParams(input) {
    const params = new URLSearchParams({
        type: input.type,
        card: input.card,
    });
    if (input.ids && input.ids.length > 0) {
        params.set("ids", input.ids.join(","));
    }
    if (input.labels && input.labels.length > 0) {
        params.set("labels", input.labels.join("|"));
    }
    if (input.snapshotPayload && input.snapshotPayload.trim()) {
        params.set("snap", input.snapshotPayload.trim());
    }
    return params;
}
function buildCompareShareUrl(siteUrl, input) {
    return `${siteUrl}/compare?${buildCompareShareParams(input).toString()}`;
}
function withSnapshotNonce(url, nonce) {
    try {
        const parsed = new URL(url);
        parsed.searchParams.set("sx", nonce);
        return parsed.toString();
    }
    catch {
        return url;
    }
}
function buildRedditShareUrl(url, text, nonce) {
    const sharedUrl = nonce ? withSnapshotNonce(url, nonce) : url;
    return `https://reddit.com/submit?${new URLSearchParams({ url: sharedUrl, title: text }).toString()}`;
}
function buildXIntentUrl(url, text, nonce) {
    const sharedUrl = withSnapshotNonce(url, nonce);
    return `https://twitter.com/intent/tweet?${new URLSearchParams({ text, url: sharedUrl }).toString()}`;
}
