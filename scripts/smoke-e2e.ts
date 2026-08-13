import { spawn, spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import type { StudioCatalog } from "../lib/catalog";

const port = 4319;
const baseUrl = `http://127.0.0.1:${port}`;

async function waitForServer(logs: () => string) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(baseUrl);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Next server did not become ready.\n${logs()}`);
}

async function assertPage(path: string, needle: string) {
  const response = await fetch(`${baseUrl}${path}`, { redirect: "manual" });
  const body = await response.text();
  if (response.status !== 200 || !body.includes(needle)) {
    throw new Error(`${path} failed: HTTP ${response.status}; expected ${JSON.stringify(needle)}`);
  }
}

async function main() {
  const catalog = JSON.parse(await readFile(join(process.cwd(), "data", "catalog.json"), "utf8")) as StudioCatalog;
  if (catalog.count !== 100 || catalog.studios.length !== 100) throw new Error("Catalog must contain exactly 100 studios");
  for (const studio of catalog.studios) {
    if (studio.score < 80 || studio.score > 99.01) throw new Error(`Score outside requested range: ${studio.studioId}`);
  }

  let output = "";
  const nextCli = join(process.cwd(), "node_modules", "next", "dist", "bin", "next");
  const server = spawn(process.execPath, [nextCli, "start", "-p", String(port)], {
    cwd: process.cwd(),
    env: { ...process.env, PORT: String(port) },
    stdio: ["ignore", "pipe", "pipe"],
  });
  server.stdout.on("data", (chunk) => { output += chunk.toString(); });
  server.stderr.on("data", (chunk) => { output += chunk.toString(); });

  try {
    await waitForServer(() => output);
    const first = catalog.studios[0];
    const last = catalog.studios[catalog.studios.length - 1];
    await assertPage("/", "100 estúdios");
    await assertPage(first.href, first.name);
    await assertPage(last.href, last.name);
    await assertPage("/sitemap.xml", first.href);
    const home = await fetch(baseUrl);
    if (!home.headers.get("content-security-policy") || home.headers.get("x-content-type-options") !== "nosniff") {
      throw new Error("Expected security headers were not present");
    }
    const dashboard = await fetch(`${baseUrl}/dashboard`, { redirect: "manual" });
    if (![302, 303, 307, 308].includes(dashboard.status) || !dashboard.headers.get("location")?.includes("/dashboard-login")) {
      throw new Error("Unauthenticated dashboard did not redirect to login");
    }
    const preview = await fetch(`${baseUrl}/preview/${first.studioId}`, { redirect: "manual" });
    if (![302, 303, 307, 308].includes(preview.status)) throw new Error("Unauthenticated draft preview was exposed");
    process.stdout.write(`Smoke E2E passed: catalog + first/last landing + sitemap (${catalog.count} studios).\n`);
  } finally {
    if (process.platform === "win32" && server.pid) {
      spawnSync("taskkill", ["/pid", String(server.pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      server.kill("SIGTERM");
    }
  }
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n`);
  process.exitCode = 1;
});
