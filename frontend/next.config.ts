import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "img.opencritic.com",
      },
    ],
  },
};

export default nextConfig;
