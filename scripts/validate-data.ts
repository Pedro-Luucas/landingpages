import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import Ajv2020, { type ErrorObject, type ValidateFunction } from "ajv/dist/2020";
import addFormats from "ajv-formats";

export const EXPECTED_SCHEMA_FILES = [
  "studio.schema.json",
  "dossier.schema.json",
  "generated.schema.json",
  "pipeline.schema.json",
  "deployment.schema.json",
] as const;

export type FixtureKind = "valid" | "invalid";

export type ValidationMessage = {
  ok: boolean;
  path: string;
  message: string;
};

export type ValidationReport = {
  skipped: boolean;
  skipReason?: string;
  ok: boolean;
  messages: ValidationMessage[];
};

export function schemasDir(root = process.cwd()): string {
  return join(root, "schemas");
}

export function fixturesDir(root = process.cwd()): string {
  return join(schemasDir(root), "fixtures");
}

export function loadJson(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8")) as unknown;
}

export function createAjv(): Ajv2020 {
  const ajv = new Ajv2020({
    allErrors: true,
    // Schemas use draft 2020-12 `allOf` + `unevaluatedProperties`; Ajv strictTypes
    // rejects that composition even though the documents are valid JSON Schema.
    strict: false,
  });
  addFormats(ajv);
  return ajv;
}

export function listSchemaFiles(directory: string): string[] {
  if (!existsSync(directory)) {
    return [];
  }
  return readdirSync(directory)
    .filter((name) => name.endsWith(".schema.json"))
    .sort()
    .map((name) => join(directory, name));
}

export function schemaStem(filePath: string): string {
  const name = filePath.replaceAll("\\", "/").split("/").pop() ?? filePath;
  const suffix = ".schema.json";
  if (name.endsWith(suffix)) {
    return name.slice(0, -suffix.length);
  }
  return name.replace(/\.json$/u, "");
}

export function fixtureKind(filePath: string): { stem: string; kind: FixtureKind } | null {
  const name = filePath.replaceAll("\\", "/").split("/").pop() ?? filePath;
  if (name.endsWith(".valid.json")) {
    return { stem: name.slice(0, -".valid.json".length), kind: "valid" };
  }
  if (name.endsWith(".invalid.json")) {
    return { stem: name.slice(0, -".invalid.json".length), kind: "invalid" };
  }
  return null;
}

export function matchSchema(
  fixtureStem: string,
  schemaFiles: string[],
): string | undefined {
  let best: string | undefined;
  let bestLen = -1;
  for (const schemaPath of schemaFiles) {
    const stem = schemaStem(schemaPath);
    if (fixtureStem === stem || fixtureStem.startsWith(`${stem}.`)) {
      if (stem.length > bestLen) {
        best = schemaPath;
        bestLen = stem.length;
      }
    }
  }
  return best;
}

function formatAjvErrors(errors: ErrorObject[] | null | undefined): string {
  if (!errors?.length) {
    return "unknown validation error";
  }
  return errors
    .map((error) => `${error.instancePath || "/"} ${error.message ?? ""}`.trim())
    .join("; ");
}

export function compileSchemas(
  schemaFiles: string[],
  ajv = createAjv(),
): Map<string, ValidateFunction> {
  const validators = new Map<string, ValidateFunction>();
  for (const schemaPath of schemaFiles) {
    const document = loadJson(schemaPath);
    validators.set(schemaPath, ajv.compile(document as object));
  }
  return validators;
}

export function validateData(root = process.cwd()): ValidationReport {
  const directory = schemasDir(root);
  const schemaFiles = listSchemaFiles(directory);

  if (schemaFiles.length === 0) {
    return {
      skipped: false,
      ok: false,
      messages: [
        {
          ok: false,
          path: directory,
          message: `no *.schema.json files in ${directory}`,
        },
      ],
    };
  }

  const missingExpected = EXPECTED_SCHEMA_FILES.filter(
    (name) => !schemaFiles.some((file) => schemaStem(file) === name.replace(/\.schema\.json$/u, "")),
  );
  if (missingExpected.length > 0) {
    return {
      skipped: false,
      ok: false,
      messages: missingExpected.map((name) => ({
        ok: false,
        path: join(directory, name),
        message: `missing expected schema ${name}`,
      })),
    };
  }

  const messages: ValidationMessage[] = [];
  let ok = true;
  const validators = compileSchemas(schemaFiles);

  for (const schemaPath of schemaFiles) {
    messages.push({
      ok: true,
      path: schemaPath,
      message: `loaded ${schemaStem(schemaPath)}.schema.json`,
    });
  }

  const fixtures = fixturesDir(root);
  if (!existsSync(fixtures)) {
    messages.push({
      ok: true,
      path: fixtures,
      message: `note: fixtures directory not found (${fixtures}); schemas loaded OK`,
    });
    return { skipped: false, ok, messages };
  }

  const fixtureFiles = readdirSync(fixtures)
    .filter((name) => fixtureKind(name) !== null)
    .sort()
    .map((name) => join(fixtures, name));

  if (fixtureFiles.length === 0) {
    messages.push({
      ok: true,
      path: fixtures,
      message: `note: no *.valid.json / *.invalid.json fixtures in ${fixtures}; schemas loaded OK`,
    });
    return { skipped: false, ok, messages };
  }

  for (const fixturePath of fixtureFiles) {
    const kindInfo = fixtureKind(fixturePath);
    if (!kindInfo) {
      continue;
    }
    const schemaPath = matchSchema(kindInfo.stem, schemaFiles);
    if (!schemaPath) {
      ok = false;
      messages.push({
        ok: false,
        path: fixturePath,
        message: `no matching *.schema.json for fixture ${kindInfo.stem}`,
      });
      continue;
    }
    const validate = validators.get(schemaPath);
    if (!validate) {
      ok = false;
      messages.push({
        ok: false,
        path: fixturePath,
        message: `validator missing for ${schemaPath}`,
      });
      continue;
    }
    const instance = loadJson(fixturePath);
    const passed = validate(instance);
    const errorText = formatAjvErrors(validate.errors);

    if (kindInfo.kind === "valid") {
      const fixtureOk = passed === true;
      ok = ok && fixtureOk;
      messages.push({
        ok: fixtureOk,
        path: fixturePath,
        message: fixtureOk
          ? `${kindInfo.stem}.valid.json vs ${schemaStem(schemaPath)}.schema.json: OK`
          : `${kindInfo.stem}.valid.json FAIL (expected valid): ${errorText}`,
      });
    } else {
      const fixtureOk = passed !== true;
      ok = ok && fixtureOk;
      messages.push({
        ok: fixtureOk,
        path: fixturePath,
        message: fixtureOk
          ? `${kindInfo.stem}.invalid.json vs ${schemaStem(schemaPath)}.schema.json: OK (rejected)`
          : `${kindInfo.stem}.invalid.json FAIL (expected invalid, but schema accepted it)`,
      });
    }
  }

  return { skipped: false, ok, messages };
}

function isCliEntry(): boolean {
  const entry = process.argv[1];
  if (!entry) {
    return false;
  }
  return entry.replaceAll("\\", "/").includes("scripts/validate-data");
}

function main(): void {
  const report = validateData();
  if (report.skipped) {
    console.warn(report.skipReason);
    process.exit(0);
  }
  for (const item of report.messages) {
    if (item.ok) {
      console.log(item.message);
    } else {
      console.error(item.message);
    }
  }
  if (!report.ok) {
    process.exit(1);
  }
}

if (isCliEntry()) {
  main();
}
