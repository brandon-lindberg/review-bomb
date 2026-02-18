import type { NextConfig } from "next";
import withSerwistInit from "@serwist/next";

const CANONICAL_HOST = "reviewdisparity.com";
const CANONICAL_ORIGIN = `https://${CANONICAL_HOST}`;

const withSerwist = withSerwistInit({
  swSrc: "src/app/sw.ts",
  swDest: "public/sw.js",
  disable: process.env.NODE_ENV === "development",
});

const nextConfig: NextConfig = {
  turbopack: {},
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
