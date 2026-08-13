import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DASHBOARD_COOKIE,
  dashboardSessionToken,
  isDashboardRequestAuthorized,
} from "@/lib/auth";

afterEach(() => vi.unstubAllEnvs());

describe("dashboard request authorization", () => {
  it("accepts a same-origin mutation with the httpOnly session token", () => {
    vi.stubEnv("DASHBOARD_SECRET", "a-long-local-secret");
    const token = dashboardSessionToken();
    const request = new Request("https://studios.example/api/approve/example", {
      method: "POST",
      headers: {
        origin: "https://studios.example",
        cookie: `${DASHBOARD_COOKIE}=${token}`,
      },
    });
    expect(isDashboardRequestAuthorized(request)).toBe(true);
  });

  it("rejects a cross-origin mutation even with a valid cookie", () => {
    vi.stubEnv("DASHBOARD_SECRET", "a-long-local-secret");
    const token = dashboardSessionToken();
    const request = new Request("https://studios.example/api/deploy/example", {
      method: "POST",
      headers: {
        origin: "https://attacker.example",
        "sec-fetch-site": "cross-site",
        cookie: `${DASHBOARD_COOKIE}=${token}`,
      },
    });
    expect(isDashboardRequestAuthorized(request)).toBe(false);
  });

  it("accepts an explicit bearer secret for operational clients", () => {
    vi.stubEnv("DASHBOARD_SECRET", "a-long-local-secret");
    const request = new Request("https://studios.example/api/pipeline/example", {
      method: "POST",
      headers: { authorization: "Bearer a-long-local-secret" },
    });
    expect(isDashboardRequestAuthorized(request)).toBe(true);
  });
});
