import { access, mkdir, rename, unlink } from "node:fs/promises";
import { join } from "node:path";
import {
  REPOSITORY_ERROR_CODES,
  RepositoryError,
  assertSafeStudioId,
  atomicWriteJson,
  exclusiveCreateJson,
  readJsonDocument,
  readJsonRaw,
  readUpdatedAt,
  utcNowIso,
  writeJsonDocument,
} from "@/lib/json-atomic";
import { logger } from "@/lib/logger";
import { assertCanTransition, isIdempotentTransition } from "@/lib/pipeline-transitions";
import type { PipelineItem, PipelineState, PipelineStatus } from "@/lib/schemas";
import { JsonStudioRepository, type StudioRepository } from "@/lib/repositories/studio-repository";

export type StudioLock = {
  studioId: string;
  owner: string;
  lockedAt: string;
  expiresAt: string;
};

/** Persistence port for pipeline queue/state JSON and per-studio locks. */
export interface StateRepository {
  getPipeline(): Promise<PipelineState>;
  savePipeline(state: PipelineState, expectedUpdatedAt?: string): Promise<void>;
  getItem(studioId: string): Promise<PipelineItem | null>;
  saveItem(item: PipelineItem, expectedUpdatedAt?: string): Promise<void>;
  transition(
    studioId: string,
    to: PipelineStatus,
    actor: string,
    reason?: string,
  ): Promise<PipelineItem>;
  acquireLock(studioId: string, owner: string, ttlSeconds: number): Promise<StudioLock>;
  releaseLock(studioId: string, owner: string): Promise<void>;
}

const DEFAULT_LOCK_TTL_SECONDS = 900;
const LOCK_ACQUIRE_ATTEMPTS = 4;

function emptyPipeline(): PipelineState {
  return {
    schemaVersion: 1,
    updatedAt: utcNowIso(),
    items: [],
  };
}

function isStudioLock(value: unknown): value is StudioLock {
  if (!value || typeof value !== "object") {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.studioId === "string" &&
    typeof record.owner === "string" &&
    typeof record.lockedAt === "string" &&
    typeof record.expiresAt === "string"
  );
}

function lockExpired(lock: StudioLock, now = Date.now()): boolean {
  const expires = Date.parse(lock.expiresAt);
  return Number.isNaN(expires) || expires <= now;
}

function findItem(pipeline: PipelineState, studioId: string): PipelineItem | undefined {
  return pipeline.items.find((item) => item.studioId === studioId);
}

async function fileExists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch (error) {
    const err = error as NodeJS.ErrnoException;
    if (err.code === "ENOENT") {
      return false;
    }
    throw error;
  }
}

function quoted(value: unknown): string {
  return typeof value === "string" ? `'${value}'` : String(value);
}

export class JsonStateRepository implements StateRepository {
  readonly dataDir: string;
  private readonly studios: StudioRepository;

  constructor(dataDir: string = process.env.DATA_DIR ?? "data", studioRepo?: StudioRepository) {
    this.dataDir = dataDir;
    this.studios = studioRepo ?? new JsonStudioRepository(dataDir);
  }

  private pipelinePath(): string {
    return join(this.dataDir, "state", "pipeline.json");
  }

  private locksDir(): string {
    return join(this.dataDir, "state", "locks");
  }

  private lockPath(studioId: string): string {
    assertSafeStudioId(studioId);
    return join(this.locksDir(), `${studioId}.lock`);
  }

  async getPipeline(): Promise<PipelineState> {
    const document = await readJsonDocument<PipelineState>(this.pipelinePath(), "pipeline");
    if (document === null) {
      return emptyPipeline();
    }
    return document;
  }

  async savePipeline(state: PipelineState, expectedUpdatedAt?: string): Promise<void> {
    if (expectedUpdatedAt !== undefined) {
      const existing = await readJsonRaw(this.pipelinePath());
      if (existing !== null) {
        const currentTs = readUpdatedAt(existing);
        if (currentTs !== expectedUpdatedAt) {
          throw new RepositoryError(
            REPOSITORY_ERROR_CODES.STATE_CONFLICT,
            `pipeline.json updatedAt mismatch (expected ${quoted(expectedUpdatedAt)}, found ${quoted(currentTs)})`,
          );
        }
      }
    }
    const now = utcNowIso();
    const document: PipelineState = {
      ...state,
      schemaVersion: 1,
      updatedAt: now,
      items: Array.isArray(state.items) ? state.items : [],
    };
    await writeJsonDocument({
      filePath: this.pipelinePath(),
      data: document,
      schemaKind: "pipeline",
    });
  }

  async getItem(studioId: string): Promise<PipelineItem | null> {
    assertSafeStudioId(studioId);
    const pipeline = await this.getPipeline();
    const existing = findItem(pipeline, studioId);
    return existing ? structuredClone(existing) : null;
  }

  async saveItem(item: PipelineItem, expectedUpdatedAt?: string): Promise<void> {
    const studioId = item.studioId;
    assertSafeStudioId(studioId);
    const pipeline = await this.getPipeline();
    const existing = findItem(pipeline, studioId);
    const pipelineFileExists = await fileExists(this.pipelinePath());
    if (expectedUpdatedAt !== undefined && pipelineFileExists) {
      if (existing) {
        if (existing.updatedAt !== expectedUpdatedAt) {
          throw new RepositoryError(
            REPOSITORY_ERROR_CODES.STATE_CONFLICT,
            `pipeline item ${studioId} updatedAt mismatch (expected ${quoted(expectedUpdatedAt)}, found ${quoted(existing.updatedAt)})`,
          );
        }
      } else if (pipeline.updatedAt !== expectedUpdatedAt) {
        throw new RepositoryError(
          REPOSITORY_ERROR_CODES.STATE_CONFLICT,
          `pipeline.json updatedAt mismatch (expected ${quoted(expectedUpdatedAt)}, found ${quoted(pipeline.updatedAt)})`,
        );
      }
    }

    const now = utcNowIso();
    const stored: PipelineItem = { ...item, studioId, updatedAt: now };
    const items = [...(pipeline.items ?? [])];
    const index = items.findIndex((entry) => entry.studioId === studioId);
    if (index >= 0) {
      items[index] = stored;
    } else {
      items.push(stored);
    }
    await writeJsonDocument({
      filePath: this.pipelinePath(),
      data: {
        schemaVersion: 1,
        updatedAt: now,
        items,
      } satisfies PipelineState,
      schemaKind: "pipeline",
    });
  }

  /**
   * Queue truth is `pipeline.json` (written first). If `studio.json` exists,
   * syncing `pipelineStatus` must succeed; a missing studio file is skipped.
   */
  async transition(
    studioId: string,
    to: PipelineStatus,
    actor: string,
    reason?: string,
  ): Promise<PipelineItem> {
    assertSafeStudioId(studioId);
    if (!actor.trim()) {
      throw new RepositoryError(REPOSITORY_ERROR_CODES.INPUT_INVALID, "transition actor is required");
    }
    const current = await this.getItem(studioId);
    if (current === null) {
      throw new RepositoryError(
        REPOSITORY_ERROR_CODES.INPUT_INVALID,
        `no pipeline item for studio ${studioId}`,
      );
    }
    if (isIdempotentTransition(current.status, to)) {
      return current;
    }
    assertCanTransition(current.status, to, actor);
    const at = utcNowIso();
    const etag = current.updatedAt;
    const updated: PipelineItem = {
      ...current,
      status: to,
      updatedAt: at,
      history: [
        ...current.history,
        {
          from: current.status,
          to,
          at,
          actor,
          ...(reason !== undefined && reason !== "" ? { reason } : {}),
        },
      ],
    };
    if (current.status === "failed" && to === "queued") {
      updated.attempt = current.attempt + 1;
      delete updated.error;
    }
    await this.saveItem(updated, etag);
    const studio = await this.studios.getStudio(studioId);
    if (studio !== null) {
      await this.studios.saveStudio({ ...studio, pipelineStatus: to, updatedAt: at });
    }
    logger.info("pipeline.transition", {
      studioId,
      from: current.status,
      to,
      actor,
      reason,
    });
    return updated;
  }

  async acquireLock(
    studioId: string,
    owner: string,
    ttlSeconds: number = DEFAULT_LOCK_TTL_SECONDS,
  ): Promise<StudioLock> {
    assertSafeStudioId(studioId);
    if (!owner.trim()) {
      throw new RepositoryError(REPOSITORY_ERROR_CODES.INPUT_INVALID, "lock owner is required");
    }
    if (!Number.isFinite(ttlSeconds) || ttlSeconds <= 0) {
      throw new RepositoryError(
        REPOSITORY_ERROR_CODES.INPUT_INVALID,
        "ttlSeconds must be a positive number",
      );
    }

    await mkdir(this.locksDir(), { recursive: true });
    const path = this.lockPath(studioId);

    for (let attempt = 0; attempt < LOCK_ACQUIRE_ATTEMPTS; attempt += 1) {
      const now = new Date();
      const payload: StudioLock = {
        studioId,
        owner,
        lockedAt: utcNowIso(now),
        expiresAt: utcNowIso(new Date(now.getTime() + ttlSeconds * 1000)),
      };

      let takingOver = false;
      let takeoverExisting: StudioLock | null = null;
      let stalePath: string | null = null;
      if (await fileExists(path)) {
        const existing = await this.readLockFile(studioId);
        if (existing !== null && !lockExpired(existing, now.getTime())) {
          if (existing.owner === owner) {
            await atomicWriteJson(path, payload, { backup: false });
            await this.touchItemLock(studioId, payload);
            return payload;
          }
          throw new RepositoryError(
            REPOSITORY_ERROR_CODES.LOCKED,
            `studio ${studioId} is locked by ${quoted(existing.owner)}`,
          );
        }
        takingOver = true;
        takeoverExisting = existing;
        stalePath = `${path}.stale-${process.pid}-${process.hrtime.bigint()}`;
        try {
          await rename(path, stalePath);
        } catch (error) {
          const err = error as NodeJS.ErrnoException;
          if (err.code === "ENOENT") {
            continue;
          }
          throw new RepositoryError(
            REPOSITORY_ERROR_CODES.LOCKED,
            `studio ${studioId} is locked (could not take over expired lock)`,
          );
        }
      }

      try {
        await exclusiveCreateJson(path, payload);
        if (takingOver) {
          await this.recordLockExpired(studioId, takeoverExisting, owner, now);
        }
        if (stalePath !== null) {
          await unlink(stalePath).catch(() => undefined);
        }
        await this.touchItemLock(studioId, payload);
        return payload;
      } catch (error) {
        const err = error as NodeJS.ErrnoException;
        if (err.code !== "EEXIST") {
          throw error;
        }
      }
    }

    throw new RepositoryError(REPOSITORY_ERROR_CODES.LOCKED, `studio ${studioId} is locked`);
  }

  async releaseLock(studioId: string, owner: string): Promise<void> {
    assertSafeStudioId(studioId);
    const path = this.lockPath(studioId);
    if (!(await fileExists(path))) {
      await this.clearItemLock(studioId, owner);
      return;
    }
    const existing = await this.readLockFile(studioId);
    if (existing !== null && existing.owner !== owner) {
      throw new RepositoryError(
        REPOSITORY_ERROR_CODES.LOCKED,
        `studio ${studioId} is locked by ${quoted(existing.owner)}`,
      );
    }
    try {
      await unlink(path);
    } catch (error) {
      const err = error as NodeJS.ErrnoException;
      if (err.code !== "ENOENT") {
        throw error;
      }
    }
    await this.clearItemLock(studioId, owner);
  }

  private async touchItemLock(studioId: string, lock: StudioLock): Promise<void> {
    const item = await this.getItem(studioId);
    if (!item) {
      return;
    }
    await this.saveItem(
      {
        ...item,
        lockedBy: lock.owner,
        lockExpiresAt: lock.expiresAt,
      },
      item.updatedAt,
    );
  }

  private async clearItemLock(studioId: string, owner: string): Promise<void> {
    const item = await this.getItem(studioId);
    if (!item) {
      return;
    }
    if (item.lockedBy !== undefined && item.lockedBy !== owner) {
      return;
    }
    const next: PipelineItem = { ...item };
    delete next.lockedBy;
    delete next.lockExpiresAt;
    await this.saveItem(next, item.updatedAt);
  }

  private async recordLockExpired(
    studioId: string,
    existing: StudioLock | null,
    newOwner: string,
    now: Date,
  ): Promise<void> {
    const item = await this.getItem(studioId);
    if (item === null) {
      return;
    }
    const at = utcNowIso(now);
    const previous = existing?.owner;
    await this.saveItem(
      {
        ...item,
        warnings: [
          ...item.warnings,
          {
            code: REPOSITORY_ERROR_CODES.LOCK_EXPIRED,
            message: previous
              ? `Took over expired lock from ${quoted(previous)}`
              : "Took over expired lock",
            stage: "lock",
            at,
            retryable: false,
          },
        ],
        history: [
          ...item.history,
          {
            from: item.status,
            to: item.status,
            at,
            actor: newOwner,
            reason: `${REPOSITORY_ERROR_CODES.LOCK_EXPIRED}: previous lock expired`,
          },
        ],
      },
      item.updatedAt,
    );
  }

  private async readLockFile(studioId: string): Promise<StudioLock | null> {
    try {
      const raw = await readJsonRaw(this.lockPath(studioId));
      if (raw === null) {
        return null;
      }
      return isStudioLock(raw) ? raw : null;
    } catch {
      return null;
    }
  }
}
