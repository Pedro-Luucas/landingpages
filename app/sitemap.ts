import type { MetadataRoute } from "next";
import { loadCatalog } from "@/lib/catalog";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const catalog = await loadCatalog();
  const base = (process.env.APP_BASE_URL ?? "http://localhost:3000").replace(/\/$/, "");
  return [
    { url: base, lastModified: new Date(catalog.generatedAt), changeFrequency: "weekly", priority: 1 },
    ...catalog.studios.map((studio) => ({
      url: `${base}${studio.href}`,
      lastModified: new Date(catalog.generatedAt),
      changeFrequency: "monthly" as const,
      priority: 0.8,
    })),
  ];
}
