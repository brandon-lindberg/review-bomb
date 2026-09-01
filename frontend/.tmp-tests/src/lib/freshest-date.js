"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.freshestDate = freshestDate;
/**
 * Returns the most recent of the given ISO date strings as an ISO string,
 * ignoring null/undefined/unparseable values. Used to emit a `dateModified`
 * freshness signal in structured data for AI search engines, which weight
 * recency heavily. Returns undefined when no valid date is present.
 */
function freshestDate(...values) {
    let best;
    for (const value of values) {
        if (!value)
            continue;
        const time = Date.parse(value);
        if (Number.isNaN(time))
            continue;
        if (best === undefined || time > best)
            best = time;
    }
    return best === undefined ? undefined : new Date(best).toISOString();
}
