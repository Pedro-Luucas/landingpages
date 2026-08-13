import { mkdir, open, readFile, rename, unlink } from "node:fs/promises";
import { dirname } from "node:path";
import type { ErrorObject, ValidateFunction } from "ajv";
import {
  compileSchemas,
  createAjv,
  listSchemaFiles,
  loadJson,
  schemaStem,
  schemasDir,
} from "@/scripts/validate-data";

export const REPOSITORY_ERROR_CODES = {
  STATE_CONFLICT: "STATE_CONFLICT",
  LOCKED: "LOCKED",
  LOCK_EXPIRED: "LOCK_EXPIRED",
  SCHEMA_INVALID: "SCHEMA_INVALID",
  INPUT_INVALID: "INPUT_INVALID",
} as const;

export type RepositoryErrorCode =
  (typeof REPOSITORY_ERROR_CODES)[keyof typeof REPOSITORY_ERROR_CODES];

export class RepositoryError extends Error {
  readonly code: RepositoryErrorCode;

  constructor(code: RepositoryErrorCode, message: string) {
    super(message);
    this.name = "RepositoryError";
    this.code = code;
  }
}

export type SchemaKind =
  | "studio"
  | "dossier"
  | "generated"
  | "approved"
  | "pipeline"
  | "deployment";

const STUDIO_ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

let validatorsByStem: Map<string, ValidateFunction> | undefined;

export function tmpSibling(targetPath: string): string {
  return `${targetPath}.tmp`;
}

export function bakSibling(targetPath: string): string {
  return `${targetPath}.bak`;
}

/** UTC ISO-8601 with `Z`, seconds precision — matches Python `format_iso`. */
export function utcNowIso(date = new Date()): string {
  return date.toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function assertSafeStudioId(studioId: string): void {
  if (!STUDIO_ID_PATTERN.test(studioId)) {
    throw new RepositoryError(
      REPOSITORY_ERROR_CODES.INPUT_INVALID,
      `invalid studioId: ${studioId}`,
    );
  }
}

export function readUpdatedAt(value: unknown): string | undefined {
  if (!value || typeof value !== "object" || !("updatedAt" in value)) {
    return undefined;
  }
  const updatedAt = (value as { updatedAt: unknown }).updatedAt;
  return typeof updatedAt === "string" ? updatedAt : undefined;
}

function formatAjvErrors(errors: ErrorObject[] | null | undefined): string {
  if (!errors?.length) {
    return "unknown validation error";
  }
  return errors
    .map((error) => `${error.instancePath || "/"} ${error.message ?? ""}`.trim())
    .join("; ");
}

function buildApprovedSchema(generated: unknown): object {
  if (!generated || typeof generated !== "object") {
    throw new Error("generated.schema.json is not an object");
  }
  const schema = structuredClone(generated) as {
    $id?: string;
    properties?: Record<string, unknown>;
    required?: string[];
  };
  delete schema.$id;
  schema.properties = {
    ...schema.properties,
    approvedAt: { type: "string", format: "date-time" },
    approvedBy: { type: "string", minLength: 1 },
    approvalNote: { type: "string" },
    assetHashes: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["path", "sha256"],
        properties: {
          path: { type: "string", minLength: 1 },
          sha256: { type: "string", pattern: "^[a-fA-F0-9]{64}$" },
        },
      },
    },
  };
  schema.required = [...(schema.required ?? []), "approvedAt", "approvedBy", "assetHashes"];
  return schema;
}

function getValidators(): Map<string, ValidateFunction> {
  if (validatorsByStem) {
    return validatorsByStem;
  }
  const ajv = createAjv();
  const files = listSchemaFiles(schemasDir());
  const compiled = compileSchemas(files, ajv);
  const byStem = new Map<string, ValidateFunction>();
  for (const file of files) {
    const validate = compiled.get(file);
    if (validate) {
      byStem.set(schemaStem(file), validate);
    }
  }
  const generatedPath = files.find((file) => schemaStem(file) === "generated");
  if (generatedPath) {
    byStem.set("approved", ajv.compile(buildApprovedSchema(loadJson(generatedPath))));
  }
  validatorsByStem = byStem;
  return byStem;
}

export function validateSchema(kind: SchemaKind, data: unknown, path: string): void {
  const validate = getValidators().get(kind);
  if (!validate) {
    throw new RepositoryError(
      REPOSITORY_ERROR_CODES.SCHEMA_INVALID,
      `no JSON schema registered for ${kind} (${path})`,
    );
  }
  if (validate(data) !== true) {
    throw new RepositoryError(
      REPOSITORY_ERROR_CODES.SCHEMA_INVALID,
      `${path} failed ${kind} schema: ${formatAjvErrors(validate.errors)}`,
    );
  }
}

export async function readJsonRaw(filePath: string): Promise<unknown | null> {
  try {
    const text = await readFile(filePath, "utf8");
    return JSON.parse(text) as unknown;
  } catch (error) {
    const err = error as NodeJS.ErrnoException;
    if (err.code === "ENOENT") {
      return null;
    }
    if (error instanceof SyntaxError) {
      throw new RepositoryError(
        REPOSITORY_ERROR_CODES.SCHEMA_INVALID,
        `invalid JSON in ${filePath}: ${error.message}`,
      );
    }
    throw error;
  }
}

export async function readJsonDocument<T>(filePath: string, kind: SchemaKind): Promise<T | null> {
  const raw = await readJsonRaw(filePath);
  if (raw === null) {
    return null;
  }
  validateSchema(kind, raw, filePath);
  return raw as T;
}

async function writeFileAtomic(filePath: string, payload: string | Buffer): Promise<void> {
  const tmpPath = tmpSibling(filePath);
  const handle = await open(tmpPath, "w");
  try {
    await handle.writeFile(payload);
    await handle.sync();
  } catch (error) {
    await handle.close().catch(() => undefined);
    await unlink(tmpPath).catch(() => undefined);
    throw error;
  }
  await handle.close();
  await rename(tmpPath, filePath);
}

async function writeBackupIfExists(filePath: string): Promise<void> {
  let previous: Buffer;
  try {
    previous = await readFile(filePath);
  } catch (error) {
    const err = error as NodeJS.ErrnoException;
    if (err.code === "ENOENT") {
      return;
    }
    throw error;
  }
  await writeFileAtomic(bakSibling(filePath), previous);
}

/**
 * Write JSON to `file.tmp` in the same directory, fsync, then rename over the
 * target. Node's `rename` replaces an existing file on Windows. When the
 * target already exists, a `*.bak` copy of the previous file is kept (same as
 * Python `atomic_write_text`), unless `backup` is false.
 */
export async function atomicWriteJson(
  filePath: string,
  data: unknown,
  options?: { backup?: boolean },
): Promise<void> {
  const backup = options?.backup ?? true;
  await mkdir(dirname(filePath), { recursive: true });
  const tmpPath = tmpSibling(filePath);
  const payload = `${JSON.stringify(data, null, 2)}\n`;
  const handle = await open(tmpPath, "w");
  try {
    await handle.writeFile(payload, "utf8");
    await handle.sync();
  } catch (error) {
    await handle.close().catch(() => undefined);
    await unlink(tmpPath).catch(() => undefined);
    throw error;
  }
  await handle.close();
  if (backup) {
    await writeBackupIfExists(filePath);
  }
  await rename(tmpPath, filePath);
}

/** Create `filePath` with `O_CREAT|O_EXCL` (`wx`). Throws `EEXIST` if it already exists. */
export async function exclusiveCreateJson(filePath: string, data: unknown): Promise<void> {
  await mkdir(dirname(filePath), { recursive: true });
  const payload = `${JSON.stringify(data, null, 2)}\n`;
  const handle = await open(filePath, "wx");
  try {
    await handle.writeFile(payload, "utf8");
    await handle.sync();
  } catch (error) {
    await handle.close().catch(() => undefined);
    await unlink(filePath).catch(() => undefined);
    throw error;
  }
  await handle.close();
}

export async function writeJsonDocument(options: {
  filePath: string;
  data: unknown;
  schemaKind: SchemaKind;
  expectedUpdatedAt?: string;
}): Promise<void> {
  const { filePath, data, schemaKind, expectedUpdatedAt } = options;
  if (expectedUpdatedAt !== undefined) {
    const existing = await readJsonRaw(filePath);
    if (existing !== null) {
      const fileUpdatedAt = readUpdatedAt(existing);
      if (fileUpdatedAt !== expectedUpdatedAt) {
        throw new RepositoryError(
          REPOSITORY_ERROR_CODES.STATE_CONFLICT,
          `updatedAt mismatch for ${filePath}: expected ${expectedUpdatedAt}, found ${fileUpdatedAt ?? "<missing>"}`,
        );
      }
    }
  }
  validateSchema(schemaKind, data, filePath);
  await atomicWriteJson(filePath, data);
}
