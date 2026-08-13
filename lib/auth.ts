import { createHash, timingSafeEqual } from "node:crypto";

export const DASHBOARD_COOKIE = "studio_dashboard_session";

export function getDashboardSecret(): string | undefined {
  const value = process.env.DASHBOARD_SECRET?.trim();
  return value || undefined;
}

function safeEqual(left: string, right: string): boolean {
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
}

export function isDashboardAuthorized(providedSecret?: string): boolean {
  const expected = getDashboardSecret();
  return Boolean(expected && providedSecret && safeEqual(expected, providedSecret));
}

export function dashboardSessionToken(secret = getDashboardSecret()): string | undefined {
  return secret ? createHash("sha256").update(`studio-dashboard:${secret}`).digest("hex") : undefined;
}

export function isDashboardSessionAuthorized(token?: string): boolean {
  const expected = dashboardSessionToken();
  return Boolean(expected && token && safeEqual(expected, token));
}

export function dashboardSecretFromRequest(request: Request): string | undefined {
  const authorization = request.headers.get("authorization");
  if (authorization?.toLowerCase().startsWith("bearer ")) return authorization.slice(7).trim();
  return request.headers.get("x-dashboard-secret")?.trim() || undefined;
}

export function isDashboardRequestAuthorized(request: Request): boolean {
  if (isDashboardAuthorized(dashboardSecretFromRequest(request))) return true;
  if (!["GET", "HEAD", "OPTIONS"].includes(request.method.toUpperCase())) {
    const site = request.headers.get("sec-fetch-site");
    if (site === "cross-site") return false;
    const origin = request.headers.get("origin");
    if (origin && origin !== new URL(request.url).origin) return false;
  }
  const cookie = request.headers.get("cookie") ?? "";
  const value = cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith(`${DASHBOARD_COOKIE}=`))?.slice(DASHBOARD_COOKIE.length + 1);
  return isDashboardSessionAuthorized(value ? decodeURIComponent(value) : undefined);
}
