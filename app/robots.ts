import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  const base = (process.env.APP_BASE_URL ?? "http://localhost:3000").replace(/\/$/, "");
  return { rules: { userAgent: "*", allow: "/", disallow: "/dashboard" }, sitemap: `${base}/sitemap.xml` };
}
