import type { ApprovedSite, Deployment } from "@/lib/schemas";

export type VercelDeployInput = {
  studioId: string;
  generationId: string;
  approved: ApprovedSite;
  actor?: string;
};

type DeployHookResponse = {
  job?: { id?: string; state?: string; createdAt?: number };
  id?: string;
  url?: string;
};

function projectName(): string {
  return process.env.VERCEL_PROJECT_NAME?.trim() || "landingpages-estudios";
}

function publicUrl(): string {
  const configured = process.env.NEXT_PUBLIC_SITE_URL?.trim();
  if (configured) return configured.replace(/\/$/, "");
  return `https://${projectName()}.vercel.app`;
}

/**
 * Starts a production deployment through a Vercel Deploy Hook. The hook is a
 * server-only secret; only non-sensitive identifiers are returned/persisted.
 */
export async function deployStudio(
  input: VercelDeployInput,
): Promise<Deployment> {
  const hook = process.env.VERCEL_DEPLOY_HOOK_URL?.trim();
  if (!hook) {
    throw new Error("VERCEL_DEPLOY_HOOK_URL is required for dashboard deployments");
  }
  const hookUrl = new URL(hook);
  if (hookUrl.protocol !== "https:" || hookUrl.hostname !== "api.vercel.com") {
    throw new Error("VERCEL_DEPLOY_HOOK_URL must be an HTTPS hook hosted at api.vercel.com");
  }
  if (input.approved.generationId !== input.generationId) {
    throw new Error("Only the currently approved generation can be deployed");
  }

  const response = await fetch(hookUrl, {
    method: "POST",
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(30_000),
  });
  const body = (await response.json().catch(() => ({}))) as DeployHookResponse;
  if (!response.ok) {
    throw new Error(`Vercel deploy hook failed with HTTP ${response.status}`);
  }

  const now = new Date().toISOString();
  const deploymentId = body.job?.id || body.id || `hook-${Date.now()}`;
  return {
    schemaVersion: 1,
    deploymentId,
    generationId: input.generationId,
    projectId: process.env.VERCEL_PROJECT_ID?.trim() || projectName(),
    projectName: projectName(),
    url: body.url?.startsWith("http") ? body.url : `${publicUrl()}/studios/${input.studioId}`,
    gitRef: process.env.VERCEL_GIT_COMMIT_REF?.trim() || "deploy-hook",
    status: "queued",
    studioId: input.studioId,
    environment: "production",
    createdAt: now,
    history: [{ to: "queued", at: now, actor: input.actor || "dashboard", reason: "Vercel Deploy Hook accepted the production build." }],
  };
}
