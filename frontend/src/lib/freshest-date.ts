/**
 * Returns the most recent of the given ISO date strings as an ISO string,
 * ignoring null/undefined/unparseable values. Used to emit a `dateModified`
 * freshness signal in structured data for AI search engines, which weight
 * recency heavily. Returns undefined when no valid date is present.
 */
export function freshestDate(
  ...values: Array<string | null | undefined>
): string | undefined {
  let best: number | undefined;

  for (const value of values) {
    if (!value) continue;
    const time = Date.parse(value);
    if (Number.isNaN(time)) continue;
    if (best === undefined || time > best) best = time;
  }

  return best === undefined ? undefined : new Date(best).toISOString();
}
