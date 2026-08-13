import { createHash } from "node:crypto";
import { generateText, Output } from "ai";
import { z } from "zod";
import type { Dossier, GeneratedSite, Studio } from "@/lib/schemas";

const hex = z.string().regex(/^#[0-9a-fA-F]{6}$/);
const draftSchema = z.object({
  templateId: z.enum(["editorial", "immersive", "minimal", "bold"]),
  branding: z.object({
    colors: z.object({ background: hex, surface: hex, primary: hex, secondary: hex, text: hex, mutedText: hex }),
    fontHeading: z.enum(["Fraunces", "Newsreader", "Bebas_Neue", "Archivo_Black", "Literata"]),
    fontBody: z.enum(["Source_Sans_3", "Outfit", "IBM_Plex_Sans", "Newsreader"]),
    radius: z.enum(["none", "small", "medium", "large"]),
    mood: z.array(z.string().min(1)).min(1).max(5),
    imageTreatment: z.string().min(1).max(160).optional(),
  }),
  copy: z.object({
    hero: z.object({ primaryCta: z.string().min(1).max(60) }),
    contact: z.object({ title: z.string().min(1).max(80), cta: z.string().min(1).max(60) }),
  }),
});

function numbers(value: string): Set<string> {
  return new Set(value.match(/\d+(?:[.,]\d+)?/g) ?? []);
}

function ensureNoInventedNumbers(output: unknown, evidence: unknown) {
  const allowed = numbers(JSON.stringify(evidence));
  for (const token of numbers(JSON.stringify(output))) {
    if (!allowed.has(token)) throw new Error(`AI output introduced unsupported number ${token}`);
  }
}

export async function generateStudioWithAi(input: {
  studio: Studio;
  dossier: Dossier;
  current: GeneratedSite;
}): Promise<{ generated: GeneratedSite; model: string; usage: unknown }> {
  const model = process.env.AI_MODEL?.trim() || "openai/gpt-5.6-luna";
  const evidence = {
    name: input.studio.name,
    type: input.studio.type,
    location: input.studio.location,
    contacts: input.studio.contacts,
    description: input.dossier.facts.description,
    reviews: input.dossier.facts.googleReviews,
    socialBio: input.dossier.social.bio,
    highlights: input.dossier.social.highlights,
    captions: input.dossier.social.posts.slice(0, 30).map((post) => post.caption).filter(Boolean),
  };
  const result = await generateText({
    model,
    maxOutputTokens: 1_200,
    abortSignal: AbortSignal.timeout(30_000),
    output: Output.object({ schema: draftSchema, name: "StudioLandingDraft", description: "Branding and factual copy for one Brazilian music studio landing page." }),
    instructions: "Você é um diretor de criação brasileiro. Produza apenas direção visual e microcopy de botões/título de contato em português natural e conciso. Não reescreva fatos do negócio. Não invente serviços, clientes, equipamentos, preços, horários, avaliações, endereços ou números. A direção visual deve ser marcante e legível.",
    prompt: `Crie branding, template e microcopy não factual para este estúdio. As evidências servem somente de contexto; o texto factual existente será preservado pelo código. Evidências:\n${JSON.stringify(evidence)}`,
  });
  ensureNoInventedNumbers(result.output, evidence);
  const draft = result.output;
  const merged: GeneratedSite = {
    ...input.current,
    provider: "vercel-ai-gateway",
    model,
    promptVersion: "dashboard-ai.v1",
    templateId: draft.templateId,
    branding: draft.branding,
    copy: {
      ...input.current.copy,
      hero: { ...input.current.copy.hero, title: input.studio.name, primaryCta: draft.copy.hero.primaryCta },
      contact: { ...input.current.copy.contact, title: draft.copy.contact.title, cta: draft.copy.contact.cta },
    },
    warnings: [...input.current.warnings.filter((item) => !item.startsWith("AI:")), "AI: conteúdo regenerado e limitado às evidências do dossiê."],
    createdAt: new Date().toISOString(),
  };
  const inputHash = createHash("sha256").update(JSON.stringify({ evidence, draft, prompt: merged.promptVersion })).digest("hex");
  merged.inputHash = inputHash;
  merged.generationId = `gen-${inputHash.slice(0, 20)}`;
  return { generated: merged, model, usage: result.usage };
}
