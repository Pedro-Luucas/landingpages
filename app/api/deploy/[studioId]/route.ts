import { NextResponse } from "next/server";
import { isDashboardRequestAuthorized } from "@/lib/auth";
import { JsonStateRepository } from "@/lib/repositories/state-repository";
import { JsonStudioRepository } from "@/lib/repositories/studio-repository";
import { deployStudio } from "@/lib/vercel";

type RouteContext = { params: Promise<{ studioId: string }> };

export async function POST(request: Request, context: RouteContext) {
  if (!isDashboardRequestAuthorized(request)) return NextResponse.json({ error: "UNAUTHORIZED" }, { status: 401 });
  const { studioId } = await context.params;
  const studios = new JsonStudioRepository();
  const approved = await studios.getApproved(studioId);
  if (!approved) return NextResponse.json({ error: "APPROVAL_REQUIRED" }, { status: 409 });
  const state = new JsonStateRepository(undefined, studios);
  const item = await state.getItem(studioId);
  if (item?.status !== "approved") return NextResponse.json({ error: "STATE_CONFLICT", message: `Deploy requires approved; found ${item?.status ?? "missing"}.` }, { status: 409 });
  try {
    const deployment = await deployStudio({ studioId, generationId: approved.generationId, approved, actor: "dashboard:human" });
    await studios.saveDeployment(deployment);
    await state.transition(studioId, "deploying", "dashboard:human", "Production deploy requested through Vercel hook.");
    return NextResponse.json(deployment, { status: 202 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Deployment failed";
    return NextResponse.json({ error: "DEPLOY_FAILED", message }, { status: 502 });
  }
}
