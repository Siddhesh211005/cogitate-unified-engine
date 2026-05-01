import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: path.resolve(__dirname),
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://127.0.0.1:8001/api/:path*',
      },
      {
        source: '/gateway/:path*',
        destination: 'http://127.0.0.1:8080/gateway/:path*',
      },
    ]
  },
};

export default nextConfig;
