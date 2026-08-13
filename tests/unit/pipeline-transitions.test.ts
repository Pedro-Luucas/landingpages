import { describe, expect, it } from "vitest";
import { assertCanTransition, isAllowedTransition } from "@/lib/pipeline-transitions";

describe("pipeline transitions", () => {
  it("allows imported → queued", () => {
    expect(isAllowedTransition("imported", "queued")).toBe(true);
    expect(() => assertCanTransition("imported", "queued", "dashboard")).not.toThrow();
  });

  it("forbids imported → deployed", () => {
    expect(isAllowedTransition("imported", "deployed")).toBe(false);
    expect(() => assertCanTransition("imported", "deployed", "dashboard")).toThrow(
      /illegal pipeline transition/,
    );
  });

  it("rejects pipeline actors for ready_for_review → approved", () => {
    expect(() => assertCanTransition("ready_for_review", "approved", "pipeline")).toThrow(
      /human actor/,
    );
    expect(() =>
      assertCanTransition("ready_for_review", "approved", "pipeline:orchestrator"),
    ).toThrow(/human actor/);
    expect(() => assertCanTransition("ready_for_review", "approved", "cli")).toThrow(/human actor/);
    expect(() => assertCanTransition("ready_for_review", "approved", "dashboard")).not.toThrow();
  });
});
