import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rename, rm, unlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { JsonStateRepository } from "@/lib/repositories/state-repository";

vi.mock("node:fs/promises", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:fs/promises")>();
  return {
    ...actual,
    rename: vi.fn(actual.rename),
    unlink: vi.fn(actual.unlink),
  };
});

describe("expired lock takeover", () => {
  let dataDir: string;

  beforeEach(async () => {
    dataDir = await mkdtemp(join(tmpdir(), "landingpages-lock-"));
    vi.mocked(rename).mockClear();
    vi.mocked(unlink).mockClear();
  });

  afterEach(async () => {
    await rm(dataDir, { recursive: true, force: true });
  });

  it("renames the live lock path to a stale sibling instead of unlinking it", async () => {
    const state = new JsonStateRepository(dataDir);
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
    expect(existsSync(lockPath)).toBe(true);

    expect(
      vi.mocked(rename).mock.calls.some(
        ([from, to]) => from === lockPath && String(to).includes(`${lockPath}.stale-`),
      ),
    ).toBe(true);
    expect(vi.mocked(unlink).mock.calls.every(([target]) => target !== lockPath)).toBe(true);
  });
});
