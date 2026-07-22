import type { NextConfig } from "next";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${API_URL}/api/v1/:path*`,
      },
    ];
  },
  async redirects() {
    // Routes renamed in the TradeLab → RosterLab transition; old links keep working.
    return [
      { source: "/trade-builder", destination: "/trade-machine", permanent: false },
      { source: "/data-health", destination: "/data-status", permanent: false },
      { source: "/decision-room", destination: "/team-hub", permanent: false },
      { source: "/teams/:teamId", destination: "/team-hub/:teamId", permanent: false },
    ];
  },
};

export default nextConfig;
