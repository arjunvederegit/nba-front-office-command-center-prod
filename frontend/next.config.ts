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
    // Module routes were renamed to match the product's own vocabulary. Every
    // previously published URL still resolves; Next forwards query strings, so
    // shared Trade Evaluator links (?state=…) survive the move.
    return [
      { source: "/trade-machine", destination: "/trade-evaluator", permanent: false },
      { source: "/trade-builder", destination: "/trade-evaluator", permanent: false },
      { source: "/compare", destination: "/strategy-lab", permanent: false },
      { source: "/player-lab", destination: "/player-explorer", permanent: false },
      { source: "/team-hub", destination: "/team-outlook", permanent: false },
      { source: "/team-hub/:teamId", destination: "/team-outlook/:teamId", permanent: false },
      { source: "/teams/:teamId", destination: "/team-outlook/:teamId", permanent: false },
      { source: "/decision-room", destination: "/team-outlook", permanent: false },
      { source: "/cap-lab", destination: "/salary-cap-center", permanent: false },
      { source: "/data-status", destination: "/data-health", permanent: false },
    ];
  },
};

export default nextConfig;
