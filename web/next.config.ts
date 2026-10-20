import type { NextConfig } from "next";

// The app is client-rendered against a local API, so none of the caching features are needed.
const nextConfig: NextConfig = {
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
