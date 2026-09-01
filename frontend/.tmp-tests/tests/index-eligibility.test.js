"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const index_eligibility_1 = require("../src/lib/index-eligibility");
(0, node_test_1.default)("eligible canonical entity pages remain indexable", () => {
    strict_1.default.equal((0, index_eligibility_1.shouldIndexEntityPage)({
        indexEligible: true,
        isShareVariant: false,
        page: 1,
    }), true);
});
(0, node_test_1.default)("thin entities remain followable but are not indexable", () => {
    strict_1.default.equal((0, index_eligibility_1.shouldIndexEntityPage)({ indexEligible: false }), false);
    strict_1.default.equal((0, index_eligibility_1.shouldIndexEntityPage)({ indexEligible: undefined }), false);
});
(0, node_test_1.default)("share variants and paginated detail views are not indexable", () => {
    strict_1.default.equal((0, index_eligibility_1.shouldIndexEntityPage)({ indexEligible: true, isShareVariant: true }), false);
    strict_1.default.equal((0, index_eligibility_1.shouldIndexEntityPage)({ indexEligible: true, page: 2 }), false);
    strict_1.default.equal((0, index_eligibility_1.shouldIndexEntityPage)({ indexEligible: true, page: Number.NaN }), false);
});
