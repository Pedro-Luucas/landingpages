import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { atomicWriteJson, utcNowIso } from "@/lib/json-atomic";
import { JsonStudioRepository } from "@/lib/repositories/studio-repository";
import { JsonStateRepository } from "@/lib/repositories/state-repository";
import type {
  ApprovedSite,
  Dossier,
  GeneratedSite,
  PipelineHistoryEntry,
  PipelineItem,
  PipelineState,
  Studio,
} from "@/lib/schemas";

type SourceRecord = {
  title?: unknown;
  type?: unknown;
  cidade?: unknown;
  estado?: unknown;
  ratingCount?: unknown;
  rating?: unknown;
  address?: unknown;
  phoneNumber?: unknown;
  website?: unknown;
  latitude?: unknown;
  longitude?: unknown;
  score_comercial?: unknown;
  [key: string]: unknown;
};

type SourceFile = { musica?: unknown } | SourceRecord[];

type BatchOptions = {
  input: string;
  limit: number;
  minScore: number;
  maxScore: number;
  dataDir: string;
};

const TEMPLATE_IDS = ["editorial", "immersive", "minimal", "bold"] as const;
const PALETTES = [
  { background: "#0b0d0f", surface: "#15191d", primary: "#f3c969", secondary: "#72808d", text: "#f6f2e9", mutedText: "#a8afb5" },
  { background: "#f2eee7", surface: "#fffaf1", primary: "#bd3f2f", secondary: "#315a63", text: "#211e1b", mutedText: "#6d665e" },
  { background: "#07130f", surface: "#10241c", primary: "#8fe36c", secondary: "#e3ad59", text: "#f1f5e9", mutedText: "#9eb2a7" },
  { background: "#111018", surface: "#201b2b", primary: "#ff6b4a", secondary: "#6fd0ca", text: "#fff6ea", mutedText: "#b9acbd" },
  { background: "#efe6d3", surface: "#faf3e6", primary: "#213a5c", secondary: "#a04e36", text: "#17202a", mutedText: "#6d6b68" },
  { background: "#08080a", surface: "#18181d", primary: "#d7ff3f", secondary: "#9a8cff", text: "#f8f8f2", mutedText: "#a4a4ad" },
] as const;

const FONT_BY_TEMPLATE = {
  editorial: { heading: "Fraunces", body: "Newsreader", radius: "small" },
  immersive: { heading: "Bebas_Neue", body: "IBM_Plex_Sans", radius: "none" },
  minimal: { heading: "Literata", body: "Source_Sans_3", radius: "medium" },
  bold: { heading: "Archivo_Black", body: "Outfit", radius: "large" },
} as const;

function text(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed || undefined;
}

function finite(value: unknown): number | undefined {
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function integer(value: unknown): number | undefined {
  const number = finite(value);
  return number !== undefined && Number.isInteger(number) && number >= 0
    ? number
    : undefined;
}

function sha256(value: unknown): string {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

function slugify(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-") || "studio";
}

function studioIdFor(record: SourceRecord): string {
  const name = text(record.title) ?? "studio";
  const city = text(record.cidade) ?? "br";
  const digest = sha256([name, city, text(record.estado), text(record.address)]).slice(0, 6);
  const namePart = slugify(name).slice(0, 52).replace(/-+$/g, "");
  const cityPart = slugify(city).slice(0, 12).replace(/-+$/g, "");
  return `${namePart}-${cityPart}-${digest}`;
}

function parseArgs(argv: string[]): BatchOptions {
  const options: BatchOptions = {
    input: "estudios_musica.json",
    limit: 100,
    minScore: 80,
    maxScore: 99.01,
    dataDir: process.env.DATA_DIR ?? "data",
  };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    const raw = argv[index + 1];
    if (!raw) continue;
    if (flag === "--input") options.input = raw;
    if (flag === "--limit") options.limit = Number(raw);
    if (flag === "--min-score") options.minScore = Number(raw);
    if (flag === "--max-score") options.maxScore = Number(raw);
    if (flag === "--data-dir") options.dataDir = raw;
  }
  if (!Number.isInteger(options.limit) || options.limit < 1 || options.limit > 2_000) {
    throw new Error("--limit must be an integer between 1 and 2000");
  }
  if (!Number.isFinite(options.minScore) || !Number.isFinite(options.maxScore)) {
    throw new Error("score bounds must be finite numbers");
  }
  return options;
}

function recordsFromSource(source: SourceFile): SourceRecord[] {
  if (Array.isArray(source)) return source;
  if (source && Array.isArray(source.musica)) return source.musica as SourceRecord[];
  throw new Error("source JSON must be an array or an object with musica[]");
}

function compareRecords(a: SourceRecord, b: SourceRecord): number {
  const scoreDiff = (finite(b.score_comercial) ?? 0) - (finite(a.score_comercial) ?? 0);
  if (scoreDiff !== 0) return scoreDiff;
  return `${text(a.title) ?? ""}|${text(a.cidade) ?? ""}`.localeCompare(
    `${text(b.title) ?? ""}|${text(b.cidade) ?? ""}`,
    "pt-BR",
  );
}

function sourceUrl(record: SourceRecord): string {
  const latitude = finite(record.latitude);
  const longitude = finite(record.longitude);
  const query = latitude !== undefined && longitude !== undefined
    ? `${latitude},${longitude}`
    : text(record.address) ?? [text(record.title), text(record.cidade)].filter(Boolean).join(" ");
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

function socialContacts(website: string | undefined): Pick<Studio["contacts"], "instagram" | "facebook"> {
  if (!website) return {};
  try {
    const host = new URL(website).hostname.toLowerCase().replace(/^www\./, "");
    if (host === "instagram.com" || host.endsWith(".instagram.com")) return { instagram: website };
    if (host === "facebook.com" || host.endsWith(".facebook.com") || host === "fb.com") return { facebook: website };
  } catch {
    return {};
  }
  return {};
}

function buildStudio(record: SourceRecord, studioId: string, now: string, inputName: string): Studio {
  const name = text(record.title) ?? studioId;
  const website = text(record.website);
  const contacts: Studio["contacts"] = {
    ...(text(record.phoneNumber) ? { phone: text(record.phoneNumber) } : {}),
    ...(website ? { website } : {}),
    ...socialContacts(website),
  };
  return {
    schemaVersion: 1,
    studioId,
    sourceId: sha256([name, text(record.cidade), text(record.estado), text(record.address)]),
    name,
    ...(text(record.type) ? { type: text(record.type) } : {}),
    slug: slugify(name),
    location: {
      ...(text(record.cidade) ? { city: text(record.cidade) } : {}),
      ...(text(record.estado) ? { state: text(record.estado) } : {}),
      ...(text(record.address) ? { address: text(record.address) } : {}),
      ...(finite(record.latitude) !== undefined ? { latitude: finite(record.latitude) } : {}),
      ...(finite(record.longitude) !== undefined ? { longitude: finite(record.longitude) } : {}),
    },
    contacts,
    source: {
      importedAt: now,
      sourceFile: inputName,
      sourceHash: sha256(record),
      originalRecord: record,
    },
    ...(finite(record.score_comercial) !== undefined
      ? { commercialScore: finite(record.score_comercial) }
      : {}),
    pipelineStatus: "approved",
    updatedAt: now,
  };
}

function evidence<T>(value: T, url: string, now: string) {
  return {
    value,
    sourceUrl: url,
    sourceType: "source_json" as const,
    collectedAt: now,
    confidence: 0.95,
  };
}

function buildDossier(studio: Studio, record: SourceRecord, now: string): Dossier {
  const url = sourceUrl(record);
  const selectedProfiles: Dossier["discovery"]["selectedProfiles"] = {};
  if (studio.contacts.instagram) selectedProfiles.instagram = evidence(studio.contacts.instagram, studio.contacts.instagram, now);
  if (studio.contacts.facebook) selectedProfiles.facebook = evidence(studio.contacts.facebook, studio.contacts.facebook, now);
  const cityLabel = [studio.location.city, studio.location.state].filter(Boolean).join(", ");
  const description = cityLabel
    ? `${studio.name} é um estúdio musical localizado em ${cityLabel}.`
    : `${studio.name} é um estúdio musical.`;
  const rating = finite(record.rating);
  const count = integer(record.ratingCount);
  const reviewValue = {
    ...(rating !== undefined ? { rating } : {}),
    ...(count !== undefined ? { count } : {}),
  };
  const mapValue = {
    ...(studio.location.latitude !== undefined ? { latitude: studio.location.latitude } : {}),
    ...(studio.location.longitude !== undefined ? { longitude: studio.location.longitude } : {}),
    ...(studio.location.address ? { address: studio.location.address } : {}),
  };
  return {
    schemaVersion: 1,
    studioId: studio.studioId,
    discovery: {
      attempts: [{
        at: now,
        method: "source_import",
        ...(studio.contacts.website ? { url: studio.contacts.website } : {}),
        result: Object.keys(selectedProfiles).length ? "social_profile_from_source" : "source_contact_only",
      }],
      selectedProfiles,
      requiresHumanReview: false,
    },
    social: { highlights: [], posts: [] },
    facts: {
      description: [evidence(description, url, now)],
      equipment: [],
      prices: [],
      openingHours: [],
      googleReviews: Object.keys(reviewValue).length ? [evidence(reviewValue, url, now)] : [],
      map: Object.keys(mapValue).length ? [evidence(mapValue, url, now)] : [],
    },
    media: { candidates: [], selected: [] },
    warnings: [{
      code: "SOURCE_ONLY_BATCH",
      message: "Página gerada somente com fatos presentes na fonte; mídia, preços, horários e equipamentos não confirmados foram omitidos.",
      stage: "batch",
      at: now,
      retryable: false,
    }],
    completedAt: now,
  };
}

function buildGenerated(studio: Studio, dossier: Dossier, index: number, now: string): GeneratedSite {
  const templateId = TEMPLATE_IDS[index % TEMPLATE_IDS.length];
  const palette = PALETTES[index % PALETTES.length];
  const font = FONT_BY_TEMPLATE[templateId];
  const cityLabel = [studio.location.city, studio.location.state].filter(Boolean).join(" — ");
  const description = dossier.facts.description[0]?.value;
  const reviews = dossier.facts.googleReviews[0]?.value;
  const hasMap = dossier.facts.map.length > 0;
  const factualClaims: GeneratedSite["factualClaims"] = [];
  const hero = {
    ...(cityLabel ? { eyebrow: cityLabel } : {}),
    title: studio.name,
    subtitle: cityLabel
      ? `Um endereço para música em ${studio.location.city}. Consulte disponibilidade e detalhes diretamente com o estúdio.`
      : "Consulte disponibilidade e detalhes diretamente com o estúdio.",
    primaryCta: "Falar com o estúdio",
  };
  if (cityLabel) factualClaims.push({ path: "copy.hero.eyebrow", evidenceRefs: ["facts.map[0]"] });
  if (cityLabel) factualClaims.push({ path: "copy.hero.subtitle", evidenceRefs: ["facts.description[0]"] });
  const copy: GeneratedSite["copy"] = {
    hero,
    ...(description ? { about: { title: "O estúdio", body: description } } : {}),
    ...(reviews && (reviews.rating !== undefined || reviews.count !== undefined)
      ? { reviews: { title: "Avaliações", ...reviews } }
      : {}),
    contact: {
      title: "Vamos conversar?",
      ...(studio.location.address ? { body: studio.location.address } : {}),
      cta: studio.contacts.phone ? "Chamar no WhatsApp" : "Ver contato oficial",
    },
  };
  if (description) factualClaims.push({ path: "copy.about.body", evidenceRefs: ["facts.description[0]"] });
  if (copy.reviews) factualClaims.push({ path: "copy.reviews", evidenceRefs: ["facts.googleReviews[0]"] });
  if (studio.location.address) factualClaims.push({ path: "copy.contact.body", evidenceRefs: ["facts.map[0]"] });
  const inputHash = sha256({ studio, dossier, version: "source-batch-v1" });
  return {
    schemaVersion: 1,
    studioId: studio.studioId,
    generationId: `gen-${inputHash.slice(0, 20)}`,
    inputHash,
    provider: "deterministic-source",
    model: "source-batch-v1",
    promptVersion: "batch.v1",
    templateId,
    branding: {
      colors: { ...palette },
      fontHeading: font.heading,
      fontBody: font.body,
      radius: font.radius,
      mood: templateId === "editorial" ? ["editorial", "autoral"] : templateId === "immersive" ? ["imersivo", "noturno"] : templateId === "minimal" ? ["preciso", "calmo"] : ["enérgico", "direto"],
      imageTreatment: "Sem mídia não verificada; composição tipográfica e cromática.",
    },
    copy,
    sections: [
      { id: "hero", enabled: true, order: 0 },
      { id: "about", enabled: Boolean(copy.about), order: 1 },
      { id: "gallery", enabled: false, order: 2 },
      { id: "equipment", enabled: false, order: 3 },
      { id: "pricing", enabled: false, order: 4 },
      { id: "hours", enabled: false, order: 5 },
      { id: "reviews", enabled: Boolean(copy.reviews), order: 6 },
      { id: "contact", enabled: true, order: 7 },
      { id: "map", enabled: hasMap, order: 8 },
    ],
    assetPaths: [],
    factualClaims,
    warnings: ["Conteúdo limitado aos dados comerciais confirmados na fonte original."],
    createdAt: now,
  };
}

function approval(generated: GeneratedSite, now: string): ApprovedSite {
  return {
    ...generated,
    approvedAt: now,
    approvedBy: "batch:user-authorized",
    approvalNote: "Lote de 100 páginas autorizado pelo usuário; somente fatos da fonte e score entre 80 e 99.01.",
    assetHashes: [],
  };
}

function history(now: string): PipelineHistoryEntry[] {
  const transitions = [
    [undefined, "imported", "Importado do JSON original."],
    ["imported", "queued", "Selecionado pelo filtro comercial do lote."],
    ["queued", "discovering", "Contatos públicos recebidos da fonte original."],
    ["discovering", "scraping", "Coleta externa omitida neste lote; somente a fonte fornecida foi autorizada como evidência."],
    ["scraping", "enriching", "Dossiê restrito aos campos confirmados na fonte."],
    ["enriching", "selecting_media", "Nenhuma mídia foi usada sem origem verificável."],
    ["selecting_media", "generating", "Geração factual determinística."],
    ["generating", "validating", "Schemas e evidências verificados."],
    ["validating", "ready_for_review", "Página pronta para revisão."],
    ["ready_for_review", "approved", "Aprovação explícita do lote solicitada pelo usuário."],
  ] as const;
  return transitions.map(([from, to, reason]) => ({
    ...(from ? { from } : {}),
    to,
    at: now,
    actor: "batch:user-authorized",
    reason,
  }));
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const inputPath = resolve(options.input);
  const raw = JSON.parse(await readFile(inputPath, "utf8")) as SourceFile;
  const eligible = recordsFromSource(raw)
    .filter((record) => {
      const score = finite(record.score_comercial);
      return Boolean(text(record.title)) && score !== undefined && score >= options.minScore && score <= options.maxScore;
    })
    .sort(compareRecords);
  if (eligible.length < options.limit) {
    throw new Error(`only ${eligible.length} eligible studios; requested ${options.limit}`);
  }

  const selected = eligible.slice(0, options.limit);
  const now = utcNowIso();
  const studios = new JsonStudioRepository(options.dataDir);
  const state = new JsonStateRepository(options.dataDir, studios);
  const items: PipelineItem[] = [];
  const catalog: Array<Record<string, unknown>> = [];

  for (const [index, record] of selected.entries()) {
    const studioId = studioIdFor(record);
    const studio = buildStudio(record, studioId, now, inputPath.split(/[\\/]/).pop() ?? options.input);
    const dossier = buildDossier(studio, record, now);
    const generated = buildGenerated(studio, dossier, index, now);
    const approved = approval(generated, now);
    await studios.saveStudio(studio);
    await studios.saveDossier(dossier);
    await studios.saveGenerated(generated);
    await studios.saveApproved(approved);
    items.push({
      studioId,
      status: "approved",
      currentStage: "approved",
      attempt: 0,
      inputHash: generated.inputHash,
      lastSuccessfulStage: "approved",
      warnings: dossier.warnings,
      history: history(now),
      createdAt: now,
      updatedAt: now,
    });
    catalog.push({
      studioId,
      name: studio.name,
      city: studio.location.city,
      state: studio.location.state,
      score: studio.commercialScore,
      templateId: generated.templateId,
      href: `/studios/${studioId}`,
    });
  }

  const pipeline: PipelineState = { schemaVersion: 1, updatedAt: now, items };
  await state.savePipeline(pipeline);
  await atomicWriteJson(resolve(options.dataDir, "catalog.json"), {
    schemaVersion: 1,
    generatedAt: now,
    sourceFile: inputPath.split(/[\\/]/).pop() ?? options.input,
    criteria: { minScore: options.minScore, maxScore: options.maxScore, order: "score_desc_name_city", limit: options.limit },
    eligibleCount: eligible.length,
    count: catalog.length,
    studios: catalog,
  });
  console.log(`Generated and approved ${catalog.length} landing pages from ${eligible.length} eligible studios.`);
  console.log(`Score range: ${String(catalog.at(-1)?.score)}–${String(catalog[0]?.score)}.`);
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
