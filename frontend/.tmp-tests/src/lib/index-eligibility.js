"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.INDEX_ELIGIBILITY_POLICY_VERSION = void 0;
exports.shouldIndexEntityPage = shouldIndexEntityPage;
exports.INDEX_ELIGIBILITY_POLICY_VERSION = "index-v1";
function shouldIndexEntityPage({ indexEligible, isShareVariant = false, page = 1, }) {
    return (indexEligible === true
        && !isShareVariant
        && Number.isInteger(page)
        && page === 1);
}
