"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const pagination_metadata_1 = require("../src/lib/pagination-metadata");
(0, node_test_1.default)("plain ?page=N pagination of the default view is indexable", () => {
    strict_1.default.equal((0, pagination_metadata_1.getIndexablePaginationPage)("2", false), 2);
    strict_1.default.equal((0, pagination_metadata_1.getIndexablePaginationPage)("37", false), 37);
});
(0, node_test_1.default)("base page and page 1 are not treated as paginated states", () => {
    strict_1.default.equal((0, pagination_metadata_1.getIndexablePaginationPage)(undefined, false), null);
    strict_1.default.equal((0, pagination_metadata_1.getIndexablePaginationPage)("", false), null);
    strict_1.default.equal((0, pagination_metadata_1.getIndexablePaginationPage)("1", false), null);
});
(0, node_test_1.default)("faceted views stay noindex even when paginated", () => {
    strict_1.default.equal((0, pagination_metadata_1.getIndexablePaginationPage)("2", true), null);
});
(0, node_test_1.default)("junk page values are rejected", () => {
    strict_1.default.equal((0, pagination_metadata_1.getIndexablePaginationPage)("0", false), null);
    strict_1.default.equal((0, pagination_metadata_1.getIndexablePaginationPage)("-3", false), null);
    strict_1.default.equal((0, pagination_metadata_1.getIndexablePaginationPage)("2abc", false), null);
    strict_1.default.equal((0, pagination_metadata_1.getIndexablePaginationPage)("abc", false), null);
    strict_1.default.equal((0, pagination_metadata_1.getIndexablePaginationPage)("2.5", false), null);
    strict_1.default.equal((0, pagination_metadata_1.getIndexablePaginationPage)("999999999999999999999", false), null);
});
