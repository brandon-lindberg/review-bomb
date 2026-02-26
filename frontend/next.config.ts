import type { NextConfig } from "next";
import withSerwistInit from "@serwist/next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const CANONICAL_HOST = "reviewdisparity.com";
const CANONICAL_ORIGIN = `https://${CANONICAL_HOST}`;
const CONFIG_DIR = path.dirname(fileURLToPath(import.meta.url));

const withSerwist = withSerwistInit({
  swSrc: "src/app/sw.ts",
  swDest: "public/sw.js",
  disable: process.env.NODE_ENV === "development",
});

const nextConfig: NextConfig = {
  outputFileTracingRoot: CONFIG_DIR,
  turbopack: {
    root: CONFIG_DIR,
  },
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "img.opencritic.com",
      },
    ],
  },
  async redirects() {
    return [
      {
        source: "/:path*",
        has: [{ type: "host", value: `www.${CANONICAL_HOST}` }],
        destination: `${CANONICAL_ORIGIN}/:path*`,
        permanent: true,
      },
      {
        source: "/:path*",
        has: [
          { type: "host", value: CANONICAL_HOST },
          { type: "header", key: "x-forwarded-proto", value: "http" },
        ],
        destination: `${CANONICAL_ORIGIN}/:path*`,
        permanent: true,
      },
    ];
  },
};

export default withSerwist(nextConfig);
