import { readFile } from "node:fs/promises";
import { join } from "node:path";

export type CatalogStudio = {
  studioId: string;
  name: string;
  city?: string;
  state?: string;
  score: number;
  templateId: "editorial" | "immersive" | "minimal" | "bold";
  href: string;
};

export type StudioCatalog = {
  schemaVersion: 1;
  generatedAt: string;
  criteria: { minScore: number; maxScore: number; order: string; limit: number };
  eligibleCount: number;
  count: number;
  studios: CatalogStudio[];
};

export async function loadCatalog(): Promise<StudioCatalog> {
  const path = join(process.cwd(), process.env.DATA_DIR ?? "data", "catalog.json");
  const raw = JSON.parse(await readFile(path, "utf8")) as StudioCatalog;
  if (raw.schemaVersion !== 1 || !Array.isArray(raw.studios) || raw.count !== raw.studios.length) {
    throw new Error("data/catalog.json is invalid");
  }
  return raw;
}
