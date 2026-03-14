"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.hashSnapshotKey = hashSnapshotKey;
exports.deriveSourceScoreFromDisparity = deriveSourceScoreFromDisparity;
exports.encodeSnapshotMetric = encodeSnapshotMetric;
exports.readSnapshotMetric = readSnapshotMetric;
exports.readSnapshotCount = readSnapshotCount;
exports.encodeSnapshotCount = encodeSnapshotCount;
exports.formatSnapshotDisplay = formatSnapshotDisplay;
exports.toTrendSnapshot = toTrendSnapshot;
exports.encodeTrendSnapshot = encodeTrendSnapshot;
exports.readTrendSnapshot = readTrendSnapshot;
function hashSnapshotKey(value) {
    let hash = 2166136261;
    for (let i = 0; i < value.length; i += 1) {
        hash ^= value.charCodeAt(i);
        hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16).padStart(8, "0");
}
function deriveSourceScoreFromDisparity(criticScore, disparity) {
    if (criticScore == null || disparity == null)
        return null;
    return Number(criticScore) - Number(disparity);
}
function encodeSnapshotMetric(value, digits = 2) {
    if (value == null)
        return "na";
    return Number(value).toFixed(digits);
}
function readSnapshotMetric(rawValue) {
    if (rawValue == null)
        return undefined;
    const normalized = rawValue.trim().toLowerCase();
    if (!normalized || normalized === "na")
        return null;
    const parsed = Number(rawValue);
    if (!Number.isFinite(parsed))
        return undefined;
    return parsed;
}
function readSnapshotCount(rawValue) {
    if (rawValue == null)
        return undefined;
    const parsed = Number.parseInt(rawValue, 10);
    if (!Number.isFinite(parsed) || parsed < 0)
        return undefined;
    return parsed;
}
function encodeSnapshotCount(value) {
    if (value == null)
        return undefined;
    const rounded = Math.round(Number(value));
    if (!Number.isFinite(rounded) || rounded < 0)
        return undefined;
    return String(rounded);
}
function formatSnapshotDisplay(value, digits = 0) {
    if (value == null)
        return "N/A";
    return Number(value).toFixed(digits);
}
const TREND_SNAPSHOT_MAX_POINTS = 16;
function toTrendSnapshot(history, maxPoints = TREND_SNAPSHOT_MAX_POINTS) {
    if (!history || history.length === 0)
        return [];
    const points = history
        .map((snapshot) => {
        const combined = snapshot.avg_disparity_combined != null
            ? Number(snapshot.avg_disparity_combined)
            : snapshot.avg_disparity_steam != null && snapshot.avg_disparity_metacritic != null
                ? (Number(snapshot.avg_disparity_steam) + Number(snapshot.avg_disparity_metacritic)) / 2
                : snapshot.avg_disparity_steam ?? snapshot.avg_disparity_metacritic ?? null;
        if (combined == null || !Number.isFinite(Number(combined)))
            return null;
        return Number(Number(combined).toFixed(1));
    })
        .filter((value) => value != null);
    return points.slice(-Math.max(1, maxPoints));
}
function encodeTrendSnapshot(points, maxPoints = TREND_SNAPSHOT_MAX_POINTS) {
    const normalized = points
        .slice(-Math.max(1, maxPoints))
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value))
        .map((value) => Number(value).toFixed(1));
    return normalized.join(",");
}
function readTrendSnapshot(rawValue, maxPoints = TREND_SNAPSHOT_MAX_POINTS) {
    if (rawValue == null)
        return undefined;
    const trimmed = rawValue.trim();
    if (!trimmed)
        return [];
    const values = trimmed
        .split(",")
        .map((token) => Number(token))
        .filter((value) => Number.isFinite(value))
        .map((value) => Number(Number(value).toFixed(1)));
    return values.slice(-Math.max(1, maxPoints));
}
