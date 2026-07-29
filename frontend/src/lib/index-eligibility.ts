interface EntityPageIndexabilityInput {
  indexEligible: boolean | null | undefined;
  isShareVariant?: boolean;
  page?: number;
}

export const INDEX_ELIGIBILITY_POLICY_VERSION = "index-v1";

export function shouldIndexEntityPage({
  indexEligible,
  isShareVariant = false,
  page = 1,
}: EntityPageIndexabilityInput): boolean {
  return (
    indexEligible === true
    && !isShareVariant
    && Number.isInteger(page)
    && page === 1
  );
}
