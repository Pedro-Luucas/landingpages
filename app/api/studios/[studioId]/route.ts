import { createHash } from "node:crypto";
import { NextResponse } from "next/server";
import { isDashboardRequestAuthorized } from "@/lib/auth";
import { JsonStateRepository } from "@/lib/repositories/state-repository";
import { JsonStudioRepository } from "@/lib/repositories/studio-repository";
import type { GeneratedSite, KnownTemplateId } from "@/lib/schemas";

type RouteContext = { params: Promise<{ studioId: string }> };
const templates = new Set<KnownTemplateId>(["editorial", "immersive", "minimal", "bold"]);

function unauthorized() {
  return NextResponse.json({ error: "UNAUTHORIZED" }, { status: 401 });
}

export async function GET(request: Request, context: RouteContext) {
  if (!isDashboardRequestAuthorized(request)) return unauthorized();
  const { studioId } = await context.params;
  const studios = new JsonStudioRepository();
  const state = new JsonStateRepository(undefined, studios);
  const [studio, dossier, generated, approved, deployment, pipeline] = await Promise.all([
    studios.getStudio(studioId),
    studios.getDossier(studioId),
    studios.getGenerated(studioId),
    studios.getApproved(studioId),
    studios.getDeployment(studioId),
    state.getItem(studioId),
  ]);
  if (!studio) return NextResponse.json({ error: "NOT_FOUND" }, { status: 404 });
  return NextResponse.json({ studio, dossier, generated, approved, deployment, pipeline });
}

export async function PATCH(request: Request, context: RouteContext) {
  if (!isDashboardRequestAuthorized(request)) return unauthorized();
  const { studioId } = await context.params;
  const studios = new JsonStudioRepository();
  const current = await studios.getGenerated(studioId);
  if (!current) return NextResponse.json({ error: "NOT_FOUND" }, { status: 404 });

  const body = (await request.json().catch(() => null)) as null | {
    templateId?: string;
  };
  if (!body || !body.templateId || !templates.has(body.templateId as KnownTemplateId)) {
    return NextResponse.json({ error: "INPUT_INVALID" }, { status: 400 });
  }

  const createdAt = new Date().toISOString();
  const digest = createHash("sha256")
    .update(JSON.stringify({ previous: current.generationId, body, createdAt }))
    .digest("hex");
  const generated: GeneratedSite = {
    ...current,
    templateId: body.templateId,
    provider: "dashboard-manual",
    model: "human-edit",
    promptVersion: "dashboard-manual.v1",
    generationId: `gen-${digest.slice(0, 20)}`,
    inputHash: digest,
    createdAt,
  };
  await studios.saveGenerated(generated);
  const state = new JsonStateRepository(undefined, studios);
  const item = await state.getItem(studioId);
  if (item?.status === "approved") {
    await state.transition(studioId, "ready_for_review", "dashboard:human", "Manual edit requires a new approval.");
  }
  return NextResponse.json({ generated });
}
