import { afterEach, describe, expect, it, vi } from "vitest";
import { logger } from "@/lib/logger";

describe("logger redaction", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("redacts apiKey before emit", () => {
    const spy = vi.spyOn(console, "info").mockImplementation(() => {});
    logger.info("test event", { apiKey: "sk-live-should-not-leak", studioId: "tmp-studio-a" });
    expect(spy).toHaveBeenCalledTimes(1);
    const payload = JSON.parse(String(spy.mock.calls[0]?.[0])) as Record<string, unknown>;
    expect(payload.apiKey).toBe("[REDACTED]");
    expect(payload.studioId).toBe("tmp-studio-a");
    expect(payload.message).toBe("test event");
  });
});
