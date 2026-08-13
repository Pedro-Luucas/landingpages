import { existsSync, readFileSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { bakSibling, tmpSibling } from "@/lib/json-atomic";
import { JsonStateRepository } from "@/lib/repositories/state-repository";
import { JsonStudioRepository } from "@/lib/repositories/studio-repository";
import type { PipelineItem, Studio } from "@/lib/schemas";

function cloneFixture<T>(name: string): T {
  return JSON.parse(
    readFileSync(join(process.cwd(), "schemas", "fixtures", name), "utf8"),
  ) as T;
}

function importedItem(studioId: string, at: string): PipelineItem {
  return {
    studioId,
    status: "imported",
    attempt: 0,
    warnings: [],
    history: [{ to: "imported", at, actor: "pipeline:importer" }],
    createdAt: at,
    updatedAt: at,
  };
}

class FailingStudioSaveRepository extends JsonStudioRepository {
  override saveStudio(): Promise<void> {
    return Promise.reject(new Error("studio.json write failed"));
  }
}

describe("JSON repositories", () => {
  let dataDir: string;

  beforeEach(async () => {
    dataDir = await mkdtemp(join(tmpdir(), "landingpages-m1-"));
  });

  afterEach(async () => {
    await rm(dataDir, { recursive: true, force: true });
  });

  it("reads the valid target when a leftover .tmp exists", async () => {
    const studio = cloneFixture<Studio>("studio.valid.json");
    const target = join(dataDir, "studios", studio.studioId, "studio.json");
    await mkdir(join(dataDir, "studios", studio.studioId), { recursive: true });
    await writeFile(target, `${JSON.stringify(studio, null, 2)}\n`, "utf8");
    await writeFile(tmpSibling(target), "{this is not valid json", "utf8");

    const repo = new JsonStudioRepository(dataDir);
    await expect(repo.getStudio(studio.studioId)).resolves.toEqual(studio);
    await expect(readFile(tmpSibling(target), "utf8")).resolves.toBe("{this is not valid json");
  });

  it("keeps a .bak of the previous JSON on atomic replace", async () => {
    const studio = cloneFixture<Studio>("studio.valid.json");
    const repo = new JsonStudioRepository(dataDir);
    await repo.saveStudio(studio);
    await repo.saveStudio({ ...studio, name: "Renamed Studio" });

    const target = join(dataDir, "studios", studio.studioId, "studio.json");
    const bak = JSON.parse(await readFile(bakSibling(target), "utf8")) as Studio;
    expect(bak.name).toBe(studio.name);
    await expect(repo.getStudio(studio.studioId)).resolves.toMatchObject({ name: "Renamed Studio" });
  });

  it("throws STATE_CONFLICT when updatedAt does not match the file", async () => {
    const studio = cloneFixture<Studio>("studio.valid.json");
    const repo = new JsonStudioRepository(dataDir);
    await repo.saveStudio(studio);
    await expect(repo.saveStudio(studio, "1999-01-01T00:00:00.000Z")).rejects.toMatchObject({
      code: "STATE_CONFLICT",
    });
  });

  it("returns an empty in-memory pipeline when pipeline.json is missing", async () => {
    const state = new JsonStateRepository(dataDir);
    const pipeline = await state.getPipeline();
    expect(pipeline).toMatchObject({ schemaVersion: 1, items: [] });
    expect(typeof pipeline.updatedAt).toBe("string");
    expect(existsSync(join(dataDir, "state", "pipeline.json"))).toBe(false);
    await expect(state.getItem("tmp-studio-a")).resolves.toBeNull();
  });

  it("creates pipeline.json items when saving an item with no existing file", async () => {
    const state = new JsonStateRepository(dataDir);
    await state.saveItem(importedItem("tmp-studio-a", "1999-01-01T00:00:00Z"));
    const pipeline = await state.getPipeline();
    expect(pipeline.items).toHaveLength(1);
    expect(pipeline.updatedAt).not.toBe("1999-01-01T00:00:00Z");
    expect(pipeline.items[0]?.updatedAt).not.toBe("1999-01-01T00:00:00Z");
    expect(pipeline.items[0]?.studioId).toBe("tmp-studio-a");
  });

  it("stamps pipeline.json updatedAt on savePipeline instead of keeping a stale caller timestamp", async () => {
    const state = new JsonStateRepository(dataDir);
    await state.savePipeline({
      schemaVersion: 1,
      updatedAt: "1999-01-01T00:00:00Z",
      items: [],
    });
    const pipeline = await state.getPipeline();
    expect(pipeline.updatedAt).not.toBe("1999-01-01T00:00:00Z");
  });

  it("rejects a forbidden transition", async () => {
    const state = new JsonStateRepository(dataDir);
    const at = "2026-08-12T12:00:00.000Z";
    await state.saveItem(importedItem("tmp-studio-a", at));
    await expect(state.transition("tmp-studio-a", "deployed", "dashboard")).rejects.toMatchObject({
      code: "INPUT_INVALID",
    });
  });

  it("errors when transitioning a studio that has no pipeline item", async () => {
    const state = new JsonStateRepository(dataDir);
    await expect(state.transition("tmp-studio-a", "queued", "dashboard")).rejects.toMatchObject({
      code: "INPUT_INVALID",
    });
  });

  it("allows imported → queued without studio.json", async () => {
    const state = new JsonStateRepository(dataDir);
    const at = "2026-08-12T12:00:00.000Z";
    await state.saveItem(importedItem("tmp-studio-a", at));
    const updated = await state.transition("tmp-studio-a", "queued", "dashboard", "enqueue");
    expect(updated.status).toBe("queued");
  });

  it("allows imported → queued and appends history", async () => {
    const studio = cloneFixture<Studio>("studio.valid.json");
    studio.studioId = "tmp-studio-a";
    studio.pipelineStatus = "imported";
    const at = "2026-08-12T12:00:00.000Z";
    const studios = new JsonStudioRepository(dataDir);
    const state = new JsonStateRepository(dataDir);
    await studios.saveStudio(studio);
    await state.saveItem(importedItem("tmp-studio-a", at));

    const updated = await state.transition("tmp-studio-a", "queued", "dashboard", "enqueue");
    expect(updated.status).toBe("queued");
    expect(updated.history).toHaveLength(2);
    expect(updated.history[1]).toMatchObject({
      from: "imported",
      to: "queued",
      actor: "dashboard",
      reason: "enqueue",
    });

    const stored = await state.getItem("tmp-studio-a");
    expect(stored?.status).toBe("queued");
    expect(stored?.history.at(-1)?.to).toBe("queued");
    await expect(studios.getStudio("tmp-studio-a")).resolves.toMatchObject({
      pipelineStatus: "queued",
    });
  });

  it("fails the transition when studio.json exists but cannot be updated", async () => {
    const studio = cloneFixture<Studio>("studio.valid.json");
    studio.studioId = "tmp-studio-a";
    studio.pipelineStatus = "imported";
    const at = "2026-08-12T12:00:00.000Z";
    const studios = new JsonStudioRepository(dataDir);
    await studios.saveStudio(studio);
    const state = new JsonStateRepository(dataDir, new FailingStudioSaveRepository(dataDir));
    await state.saveItem(importedItem("tmp-studio-a", at));

    await expect(state.transition("tmp-studio-a", "queued", "dashboard")).rejects.toThrow(
      "studio.json write failed",
    );
    await expect(state.getItem("tmp-studio-a")).resolves.toMatchObject({ status: "queued" });
  });

  it("refreshes TTL when the same owner acquires an unexpired lock", async () => {
    const state = new JsonStateRepository(dataDir);
    const first = await state.acquireLock("tmp-studio-a", "worker-1", 60);
    const second = await state.acquireLock("tmp-studio-a", "worker-1", 120);
    expect(second.owner).toBe("worker-1");
    expect(Date.parse(second.expiresAt)).toBeGreaterThan(Date.parse(first.expiresAt));
    expect(second.lockedAt).toBeTruthy();
  });

  it("throws LOCKED when a different owner holds an unexpired lock", async () => {
    const state = new JsonStateRepository(dataDir);
    await state.acquireLock("tmp-studio-a", "worker-1", 60);
    await expect(state.acquireLock("tmp-studio-a", "worker-2", 60)).rejects.toMatchObject({
      code: "LOCKED",
    });
  });

  it("takes over an expired lock and records LOCK_EXPIRED on the item", async () => {
    const state = new JsonStateRepository(dataDir);
    const at = "2026-08-12T12:00:00.000Z";
    await state.saveItem(importedItem("tmp-studio-a", at));
    const lockPath = join(dataDir, "state", "locks", "tmp-studio-a.lock");
    await mkdir(join(dataDir, "state", "locks"), { recursive: true });
    await writeFile(
      lockPath,
      `${JSON.stringify({
        owner: "stale",
        lockedAt: "2000-01-01T00:00:00Z",
        expiresAt: "2000-01-01T00:00:00Z",
        studioId: "tmp-studio-a",
      }, null, 2)}\n`,
      "utf8",
    );

    const lock = await state.acquireLock("tmp-studio-a", "fresh", 30);
    expect(lock.owner).toBe("fresh");
    const item = await state.getItem("tmp-studio-a");
    expect(item?.warnings.some((warning) => warning.code === "LOCK_EXPIRED")).toBe(true);
    expect(item?.history.some((entry) => entry.reason?.includes("LOCK_EXPIRED"))).toBe(true);
    expect(item?.lockedBy).toBe("fresh");
  });

  it("treats a missing lock file as a successful release", async () => {
    const state = new JsonStateRepository(dataDir);
    await expect(state.releaseLock("tmp-studio-a", "worker-1")).resolves.toBeUndefined();
  });

  it("throws LOCKED when releaseLock is called by the wrong owner", async () => {
    const state = new JsonStateRepository(dataDir);
    await state.acquireLock("tmp-studio-a", "worker-1", 60);
    await expect(state.releaseLock("tmp-studio-a", "worker-2")).rejects.toMatchObject({
      code: "LOCKED",
    });
  });
});
