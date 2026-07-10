/** @type {import('next').NextConfig} */
const nodeMajor = Number.parseInt(process.versions.node.split(".")[0] || "0", 10);
const needsDesktopNodeWorkaround = nodeMajor >= 22;

const nextConfig = {
  reactStrictMode: true,
  experimental: {
    // Next build workers can hang under the desktop Node 24 runtime.
    // Node 20 remains the recommended production runtime for this app.
    webpackBuildWorker: !needsDesktopNodeWorkaround,
    serverMinification: !needsDesktopNodeWorkaround,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  webpack(config, { dev }) {
    if (!dev && needsDesktopNodeWorkaround) {
      config.optimization.minimize = false;
    }
    return config;
  },
  async redirects() {
    return [{ source: "/favicon.ico", destination: "/favicon.svg", permanent: false }];
  },
};

module.exports = nextConfig;
