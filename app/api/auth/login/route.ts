import { NextResponse } from "next/server";
import { DASHBOARD_COOKIE, dashboardSessionToken, isDashboardAuthorized } from "@/lib/auth";

const attempts = new Map<string, { count: number; resetsAt: number }>();
const WINDOW_MS = 15 * 60 * 1000;
const MAX_ATTEMPTS = 8;

function clientKey(request: Request): string {
  return request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "local";
}

function isRateLimited(key: string): { limited: boolean; retryAfter: number } {
  const now = Date.now();
  const entry = attempts.get(key);
  if (!entry || entry.resetsAt <= now) {
    attempts.set(key, { count: 0, resetsAt: now + WINDOW_MS });
    return { limited: false, retryAfter: 0 };
  }
  return { limited: entry.count >= MAX_ATTEMPTS, retryAfter: Math.max(1, Math.ceil((entry.resetsAt - now) / 1000)) };
}

export async function POST(request: Request) {
  const key = clientKey(request);
  const limit = isRateLimited(key);
  if (limit.limited) {
    return NextResponse.json({ error: "RATE_LIMITED" }, { status: 429, headers: { "Retry-After": String(limit.retryAfter) } });
  }
  const form = await request.formData();
  const secret = String(form.get("secret") ?? "").slice(0, 512);
  if (!isDashboardAuthorized(secret)) {
    const current = attempts.get(key)!;
    current.count += 1;
    return NextResponse.redirect(new URL("/dashboard-login?error=1", request.url), 303);
  }
  attempts.delete(key);
  const response = NextResponse.redirect(new URL("/dashboard", request.url), 303);
  response.cookies.set(DASHBOARD_COOKIE, dashboardSessionToken()!, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  return response;
}
