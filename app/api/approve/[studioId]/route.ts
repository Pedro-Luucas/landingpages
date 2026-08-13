import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { isAbsolute, join, relative, resolve } from "node:path";
import { NextResponse } from "next/server";
import { isDashboardRequestAuthorized } from "@/lib/auth";
import { JsonStateRepository } from "@/lib/repositories/state-repository";
import { JsonStudioRepository } from "@/lib/repositories/studio-repository";
import type { ApprovedSite } from "@/lib/schemas";

type RouteContext = { params: Promise<{ studioId: string }> };

async function hashAsset(path: string): Promise<{ path: string; sha256: string }> {
  const publicRoot = resolve(process.cwd(), "public");
  const normalized = path.replace(/^\/+/, "");
  const relativePath = normalized.startsWith("public/") ? normalized.slice("public/".length) : normalized;
  const absolute = isAbsolute(path) ? resolve(path) : join(process.cwd(), "public", relativePath);
  const distance = relative(publicRoot, absolute);
  if (distance.startsWith("..") || isAbsolute(distance)) throw new Error(`Asset is outside public/: ${path}`);
  const content = await readFile(absolute);
  return { path, sha256: createHash("sha256").update(content).digest("hex") };
}

export async function POST(request: Request, context: RouteContext) {
  if (!isDashboardRequestAuthorized(request)) return NextResponse.json({ error: "UNAUTHORIZED" }, { status: 401 });
  const { studioId } = await context.params;
  const body = (await request.json().catch(() => ({}))) as { approvedBy?: string; approvalNote?: string };
  const approvedBy = body.approvedBy?.trim().slice(0, 120) || "dashboard:human";
  const approvalNote = body.approvalNote?.trim().slice(0, 1_000);
  const studios = new JsonStudioRepository();
  const [generated, previous] = await Promise.all([studios.getGenerated(studioId), studios.getApproved(studioId)]);
  if (!generated) return NextResponse.json({ error: "NOT_FOUND" }, { status: 404 });
  if (previous?.generationId === generated.generationId) return NextResponse.json(previous);

  try {
    const assetHashes = await Promise.all(generated.assetPaths.map(hashAsset));
    const approved: ApprovedSite = {
      ...generated,
      approvedAt: new Date().toISOString(),
      approvedBy,
      ...(approvalNote ? { approvalNote } : {}),
      assetHashes,
    };
    const state = new JsonStateRepository(undefined, studios);
    const item = await state.getItem(studioId);
    if (item?.status !== "ready_for_review") {
      return NextResponse.json({ error: "STATE_CONFLICT", message: `Approval requires ready_for_review; found ${item?.status ?? "missing"}.` }, { status: 409 });
    }
    await studios.saveApproved(approved);
    await state.transition(studioId, "approved", approvedBy, approvalNote);
    return NextResponse.json(approved);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Approval failed";
    return NextResponse.json({ error: "APPROVAL_FAILED", message }, { status: 400 });
  }
}
