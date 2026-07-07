/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Proxy all /api/* calls to the local FastAPI backend so the browser only ever talks to
  // this frontend's origin. That lets one public tunnel (to :3000) expose the whole app —
  // no CORS, no separate backend URL. Override with the BACKEND_ORIGIN env var if needed.
  async rewrites() {
    const backend = process.env.BACKEND_ORIGIN || "http://127.0.0.1:8741";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};
export default nextConfig;
