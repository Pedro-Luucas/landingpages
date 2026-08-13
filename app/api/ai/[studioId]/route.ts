import { NextResponse } from "next/server";
import { isDashboardRequestAuthorized } from "@/lib/auth";
import { generateStudioWithAi } from "@/lib/ai/generate-studio";
import { JsonStudioRepository } from "@/lib/repositories/studio-repository";
import { JsonStateRepository } from "@/lib/repositories/state-repository";
import { logger } from "@/lib/logger";

export async function POST(request: Request, { params }: { params: Promise<{ studioId: string }> }) {
  if (!isDashboardRequestAuthorized(request)) return NextResponse.json({ error: "UNAUTHORIZED" }, { status: 401 });
  const { studioId } = await params;
  const studios = new JsonStudioRepository();
  const [studio, dossier, current] = await Promise.all([studios.getStudio(studioId), studios.getDossier(studioId), studios.getGenerated(studioId)]);
  if (!studio || !dossier || !current) return NextResponse.json({ error: "INPUT_INVALID", message: "Studio, dossier, or generated snapshot missing." }, { status: 404 });
  try {
    const result = await generateStudioWithAi({ studio, dossier, current });
    await studios.saveGenerated(result.generated);
    const state = new JsonStateRepository(undefined, studios);
    const item = await state.getItem(studioId);
    if (item?.status === "approved") await state.transition(studioId, "ready_for_review", "dashboard", "AI regeneration invalidated previous approval.");
    return NextResponse.json({ studioId, generationId: result.generated.generationId, model: result.model, usage: result.usage });
  } catch (error) {
    logger.error("ai.generate.failed", { studioId, errorType: error instanceof Error ? error.name : "UnknownError" });
    return NextResponse.json({ error: "AI_PROVIDER_ERROR", message: "A geração falhou; tente novamente ou revise a configuração do provedor." }, { status: 502 });
  }
}
