import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  EXPECTED_SCHEMA_FILES,
  compileSchemas,
  createAjv,
  fixtureKind,
  fixturesDir,
  listSchemaFiles,
  loadJson,
  matchSchema,
  schemaStem,
  schemasDir,
  validateData,
} from "../../scripts/validate-data";

const root = process.cwd();
const schemaFiles = listSchemaFiles(schemasDir(root));

describe("JSON schema contract", () => {
  it("expects the five schema files from the plan", () => {
    expect([...EXPECTED_SCHEMA_FILES]).toEqual([
      "studio.schema.json",
      "dossier.schema.json",
      "generated.schema.json",
      "pipeline.schema.json",
      "deployment.schema.json",
    ]);
  });
});

describe("JSON schemas", () => {
  it("loads each schema file", () => {
    const ajv = createAjv();
    const validators = compileSchemas(schemaFiles, ajv);
    expect(schemaFiles.length).toBeGreaterThan(0);
    expect(validators.size).toBe(schemaFiles.length);
    for (const expected of EXPECTED_SCHEMA_FILES) {
      const found = schemaFiles.some((file) => schemaStem(file) === expected.replace(/\.schema\.json$/u, ""));
      expect(found, `missing ${expected}`).toBe(true);
    }
  });

  it("accepts matching valid fixtures and rejects invalid fixtures", () => {
    const report = validateData(root);
    expect(report.skipped).toBe(false);
    const failures = report.messages.filter((item) => !item.ok);
    expect(failures.map((item) => item.message)).toEqual([]);
    expect(report.ok).toBe(true);
  });

  it("validates each expected valid/invalid fixture pair", () => {
    const fixtures = fixturesDir(root);
    expect(existsSync(fixtures)).toBe(true);
    const validators = compileSchemas(schemaFiles);
    const names = [
      "studio",
      "dossier",
      "generated",
      "pipeline",
      "deployment",
    ] as const;

    for (const name of names) {
      const validPath = join(fixtures, `${name}.valid.json`);
      const invalidPath = join(fixtures, `${name}.invalid.json`);
      expect(existsSync(validPath), validPath).toBe(true);
      expect(existsSync(invalidPath), invalidPath).toBe(true);

      const validKind = fixtureKind(validPath);
      const invalidKind = fixtureKind(invalidPath);
      expect(validKind?.kind).toBe("valid");
      expect(invalidKind?.kind).toBe("invalid");

      const validSchema = matchSchema(validKind!.stem, schemaFiles);
      const invalidSchema = matchSchema(invalidKind!.stem, schemaFiles);
      expect(validSchema).toBeDefined();
      expect(invalidSchema).toBeDefined();

      const validFn = validators.get(validSchema!);
      const invalidFn = validators.get(invalidSchema!);
      expect(validFn?.(loadJson(validPath))).toBe(true);
      expect(invalidFn?.(loadJson(invalidPath))).toBe(false);
    }
  });

  it("rejects invalid date-time and uri formats (Ajv addFormats)", () => {
    const studioPath = schemaFiles.find((file) => schemaStem(file) === "studio");
    expect(studioPath).toBeDefined();
    const validate = compileSchemas(schemaFiles).get(studioPath!);
    expect(validate).toBeDefined();
    const instance = loadJson(join(fixturesDir(root), "studio.valid.json")) as Record<string, unknown>;

    expect(validate?.({ ...instance, updatedAt: "not-a-date" })).toBe(false);
    expect(
      validate?.({
        ...instance,
        contacts: { ...(instance.contacts as object), website: "not a uri" },
      }),
    ).toBe(false);
  });
});
