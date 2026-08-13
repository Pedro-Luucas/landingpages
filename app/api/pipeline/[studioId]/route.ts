import { NextResponse } from "next/server";
import { isDashboardRequestAuthorized } from "@/lib/auth";
import { JsonStateRepository } from "@/lib/repositories/state-repository";

type RouteContext = { params: Promise<{ studioId: string }> };

export async function GET(request: Request, context: RouteContext) {
  if (!isDashboardRequestAuthorized(request)) return NextResponse.json({ error: "UNAUTHORIZED" }, { status: 401 });
  const { studioId } = await context.params;
  const item = await new JsonStateRepository().getItem(studioId);
  return item
    ? NextResponse.json(item)
    : NextResponse.json({ error: "NOT_FOUND" }, { status: 404 });
}

export async function POST(request: Request, context: RouteContext) {
  if (!isDashboardRequestAuthorized(request)) return NextResponse.json({ error: "UNAUTHORIZED" }, { status: 401 });
  const { studioId } = await context.params;
  const state = new JsonStateRepository();
  const item = await state.getItem(studioId);
  if (!item) return NextResponse.json({ error: "NOT_FOUND" }, { status: 404 });
  if (!["imported", "failed", "rejected"].includes(item.status)) {
    return NextResponse.json({ error: "STATE_CONFLICT", message: `Cannot queue from ${item.status}.` }, { status: 409 });
  }
  const updated = await state.transition(studioId, "queued", "dashboard:human", "Queued from dashboard.");
  return NextResponse.json(updated);
}
